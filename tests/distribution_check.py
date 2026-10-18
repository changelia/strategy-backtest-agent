"""Inspect this project's distributions without extracting or executing their contents.

Run with the temporary build/twine environment (which supplies packaging):
python tests/distribution_check.py --project . dist/task15/*.whl dist/task15/*.tar.gz
"""

import argparse
import configparser
import hashlib
import json
import stat
import tarfile
import tomllib
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

PACKAGE = "strategy_backtest_agent"
DIST = "strategy_backtest_agent-1.0.0.dist-info"
ROOT = "strategy_backtest_agent-1.0.0"
BLOCKED = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "tests",
    "scripts",
    "examples",
}
MAX_MEMBER = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    require(
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
        and ":" not in name,
        "unsafe archive path",
    )
    return path


def prohibited(path: PurePosixPath) -> bool:
    return any(
        part in BLOCKED
        or part.endswith(".egg-info")
        or part in (".env", ".envrc", ".pypirc", ".DS_Store")
        or (part.startswith(".env.") and part != ".env.example")
        or part.endswith((".pyc", ".pyo", ".whl", ".tar.gz"))
        for part in path.parts
    )


def read_archive(path: Path) -> dict[str, bytes]:
    """Reject links, duplicate names, traversal and oversized inputs before reading."""
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0

    def add(name: str, size: int) -> str:
        nonlocal total
        key = str(safe_path(name))
        require(key not in seen, "duplicate archive path")
        seen.add(key)
        total += size
        require(0 <= size <= MAX_MEMBER and total <= MAX_TOTAL, "archive exceeds size limits")
        return key

    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                key = add(member.filename, member.file_size)
                mode = member.external_attr >> 16
                require(
                    stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR),
                    "archive links/special files prohibited",
                )
                if not member.is_dir():
                    files[key] = archive.read(member)
    else:
        require(path.name.endswith(".tar.gz"), "expected wheel or gzip source distribution")
        with tarfile.open(path, "r:gz") as source_archive:
            for tar_member in source_archive.getmembers():
                key = add(tar_member.name, tar_member.size)
                require(
                    tar_member.isfile() or tar_member.isdir(),
                    "archive links/special files prohibited",
                )
                if tar_member.isfile():
                    stream = source_archive.extractfile(tar_member)
                    require(stream is not None, "unreadable archive tar_member")
                    assert stream is not None
                    files[key] = stream.read()
    return files


def normalized_requirements(values: list[str]) -> dict[str, SpecifierSet]:
    result: dict[str, SpecifierSet] = {}
    for value in values:
        requirement = Requirement(value)
        name = canonicalize_name(requirement.name)
        require(name not in result, "duplicate runtime dependency")
        require(
            not requirement.extras and requirement.marker is None and requirement.url is None,
            "unexpected conditional/URL runtime dependency",
        )
        result[name] = requirement.specifier
    return result


def validate(path: Path, project: Path) -> dict[str, Any]:
    files = read_archive(path)
    wheel = path.suffix == ".whl"
    if not wheel:
        require(all(name.startswith(ROOT + "/") for name in files), "incorrect sdist root")
        files = {name[len(ROOT) + 1 :]: value for name, value in files.items()}
    for name in files:
        require(not prohibited(PurePosixPath(name)), "prohibited distribution member: " + name)
    prefix = PACKAGE + "/" if wheel else "src/" + PACKAGE + "/"
    runtime = {
        name.removeprefix(prefix): value for name, value in files.items() if name.startswith(prefix)
    }
    expected = {
        p.relative_to(project / "src" / PACKAGE).as_posix(): p.read_bytes()
        for p in (project / "src" / PACKAGE).rglob("*")
        if p.is_file() and not prohibited(PurePosixPath(p.relative_to(project).as_posix()))
    }
    require(bool(expected) and runtime == expected, "missing, extra or changed runtime files")
    if wheel:
        allowed = {DIST + "/" + n for n in ("METADATA", "WHEEL", "RECORD", "entry_points.txt")}
        legal = {DIST + "/LICENSE", DIST + "/licenses/LICENSE"}
        require(
            set(files) - {prefix + p for p in runtime} <= allowed | legal, "unrelated wheel files"
        )
        require(len(set(files) & legal) == 1, "wheel must contain one license file")
        license_path = next(iter(set(files) & legal))
        required = {
            DIST + "/METADATA",
            DIST + "/WHEEL",
            DIST + "/RECORD",
            DIST + "/entry_points.txt",
        }
        require(required <= files.keys(), "missing wheel metadata")
        entry = configparser.ConfigParser()
        try:
            entry.read_string(files[DIST + "/entry_points.txt"].decode())
        except configparser.Error:
            raise ValueError("malformed console entry metadata") from None
        require(
            dict(entry["console_scripts"])
            == {"strategy-backtest": "strategy_backtest_agent.cli:main"},
            "incorrect console entry point",
        )
        wheel_info = BytesParser(policy=policy.default).parsebytes(files[DIST + "/WHEEL"])
        require(
            wheel_info["Wheel-Version"] == "1.0"
            and wheel_info["Root-Is-Purelib"] == "true"
            and wheel_info.get_all("Tag") == ["py3-none-any"],
            "incorrect wheel layout/tags",
        )
        metadata_path = DIST + "/METADATA"
    else:
        required = {"README.md", "LICENSE", "pyproject.toml", "PKG-INFO", ".env.example"}
        require(required <= files.keys(), "missing required sdist files")
        require(set(files) - {prefix + p for p in runtime} == required, "unrelated sdist files")
        for name in ("README.md", "pyproject.toml", ".env.example"):
            require(files[name] == (project / name).read_bytes(), "incorrect sdist " + name)
        # Only this tracked harmless template is permitted outside the runtime package.
        require(
            b"OPENAI_API_KEY=your_openai_api_key_here" in files[".env.example"],
            "unexpected dotenv template",
        )
        license_path = "LICENSE"
        metadata_path = "PKG-INFO"
    require(files[license_path] == (project / "LICENSE").read_bytes(), "incorrect license file")
    metadata = BytesParser(policy=policy.default).parsebytes(files[metadata_path])
    require(not metadata.defects, "malformed distribution metadata")
    for header in (
        "Metadata-Version",
        "Name",
        "Version",
        "Requires-Python",
        "Description-Content-Type",
        "License",
    ):
        require(len(metadata.get_all(header, [])) == 1, "missing/duplicate metadata header")
    require(canonicalize_name(str(metadata["Name"])) == "strategy-backtest-agent", "incorrect name")
    require(metadata["Version"] == "1.0.0", "incorrect version")
    require(
        SpecifierSet(str(metadata["Requires-Python"])) == SpecifierSet(">=3.12,<4.0"),
        "incorrect Python requirement",
    )
    require(
        metadata["Description-Content-Type"] == "text/markdown", "incorrect README content type"
    )
    description = metadata.get_payload(decode=True)
    if not isinstance(description, bytes):
        raise ValueError("malformed README metadata")
    require(
        description.decode("utf-8").strip()
        == (project / "README.md").read_text(encoding="utf-8").strip(),
        "incorrect README metadata",
    )
    require(
        metadata["License"] == "MIT" and metadata.get_all("License-File") == ["LICENSE"],
        "incorrect license metadata",
    )
    expected_requirements = {
        "pandas": ">=2.2,<3.0",
        "httpx": ">=0.28,<0.29",
        "pydantic": ">=2.10,<3.0",
        "openai": ">=3.24.0,<4.0.0",
        "python-dotenv": ">=1.2.4,<2.0.0",
    }
    actual = normalized_requirements(metadata.get_all("Requires-Dist", []))
    require(
        actual == {n: SpecifierSet(s) for n, s in expected_requirements.items()},
        "incorrect runtime dependencies (including unexpected development tools)",
    )
    config = tomllib.loads((project / "pyproject.toml").read_text())
    require(config["project"]["version"] == "1.0.0", "validator targets version 1.0.0")
    return {
        "artifact": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "files": sorted(files),
        "runtime_sha256": {
            name: hashlib.sha256(value).hexdigest() for name, value in sorted(runtime.items())
        },
        "metadata": {
            key: metadata.get_all(key, [])
            for key in (
                "Metadata-Version",
                "Name",
                "Version",
                "Requires-Python",
                "Requires-Dist",
                "Description-Content-Type",
                "License",
                "License-File",
            )
        },
        "license_path": license_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps([validate(p, args.project) for p in args.artifacts], indent=2))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        parser.exit(2, f"Distribution validation failed: {exc}\n")


if __name__ == "__main__":
    main()
