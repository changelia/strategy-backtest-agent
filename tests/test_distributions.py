"""Offline archive mutation tests; actual isolated builds are recorded in the build report."""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from distribution_check import DIST, ROOT, read_archive, validate

REQUIREMENTS = [
    "pandas (>=2.2,<3.0)",
    "httpx (>=0.28,<0.29)",
    "pydantic (>=2.10,<3.0)",
    "openai (>=3.24.0,<4.0.0)",
    "python-dotenv (>=1.2.4,<2.0.0)",
]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src/strategy_backtest_agent/resources").mkdir(parents=True)
    for name, content in {
        "README.md": "# Example\n\nOffline research — not a prediction.\n",
        "LICENSE": "MIT fixture legal text\n",
        ".env.example": "OPENAI_API_KEY=your_openai_api_key_here\n",
        "pyproject.toml": '[project]\nversion = "1.0.0"\n',
        "src/strategy_backtest_agent/__init__.py": '"""Example package."""\n',
        "src/strategy_backtest_agent/cli.py": "def main():\n    pass\n",
        "src/strategy_backtest_agent/resources/example.json": '{"example": true}\n',
        "src/strategy_backtest_agent/resources/notes.md": "# Legitimate resource\n",
    }.items():
        (tmp_path / name).write_text(content)
    return tmp_path


def contents(project: Path, wheel: bool) -> dict[str, bytes]:
    result = {}
    for path in (project / "src").rglob("*"):
        if path.is_file():
            name = path.relative_to(project / "src" if wheel else project).as_posix()
            result[name] = path.read_bytes()
    metadata = (
        "Metadata-Version: 2.4\nName: strategy-backtest-agent\nVersion: 1.0.0\n"
        "Requires-Python: >=3.12,<4.0\nLicense: MIT\nLicense-File: LICENSE\n"
        "Description-Content-Type: text/markdown\n"
        + "".join(f"Requires-Dist: {r}\n" for r in REQUIREMENTS)
        + "\n"
        + (project / "README.md").read_text()
    ).encode()
    if wheel:
        result[DIST + "/METADATA"] = metadata
        result[DIST + "/licenses/LICENSE"] = (project / "LICENSE").read_bytes()
        result[DIST + "/entry_points.txt"] = (
            b"[console_scripts]\nstrategy-backtest=strategy_backtest_agent.cli:main\n"
        )
        result[DIST + "/WHEEL"] = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        result[DIST + "/RECORD"] = b""
    else:
        result["PKG-INFO"] = metadata
        for name in ("README.md", "LICENSE", "pyproject.toml", ".env.example"):
            result[name] = (project / name).read_bytes()
    return result


def write_archive(tmp_path: Path, files: dict[str, bytes], wheel: bool) -> Path:
    archive = tmp_path / ("fixture.whl" if wheel else "fixture.tar.gz")
    if wheel:
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, value in files.items():
                zipped.writestr(name, value)
    else:
        with tarfile.open(archive, "w:gz") as source:
            for name, value in files.items():
                entry = tarfile.TarInfo(ROOT + "/" + name)
                entry.size = len(value)
                source.addfile(entry, io.BytesIO(value))
    return archive


@pytest.mark.parametrize("wheel", [True, False])
def test_valid_archive_keeps_resources_and_has_source_matched_metadata(
    project: Path, wheel: bool
) -> None:
    archive = write_archive(project, contents(project, wheel), wheel)
    result = validate(archive, project)
    assert set(result["runtime_sha256"]) == {
        "__init__.py",
        "cli.py",
        "resources/example.json",
        "resources/notes.md",
    }
    assert result["metadata"]["Version"] == ["1.0.0"]
    assert len(result["sha256"]) == 64


@pytest.mark.parametrize("wheel", [True, False])
@pytest.mark.parametrize(
    "mutation", ["missing_runtime", "changed_runtime", "missing_license", "metadata"]
)
def test_missing_required_files_and_changed_source_are_rejected(
    project: Path, wheel: bool, mutation: str
) -> None:
    files = contents(project, wheel)
    prefix = "" if wheel else "src/"
    if mutation == "missing_runtime":
        files.pop(prefix + "strategy_backtest_agent/cli.py")
    elif mutation == "changed_runtime":
        files[prefix + "strategy_backtest_agent/cli.py"] = b"unreviewed contents"
    elif mutation == "missing_license":
        files.pop(DIST + "/licenses/LICENSE" if wheel else "LICENSE")
    else:
        files.pop(DIST + "/METADATA" if wheel else "PKG-INFO")
    with pytest.raises(ValueError):
        validate(write_archive(project, files, wheel), project)


@pytest.mark.parametrize("wheel", [True, False])
@pytest.mark.parametrize(
    "member",
    [
        ".env",
        ".env.production",
        ".pypirc",
        "research-report.json",
        "local-result.md",
        "tests/development.py",
        "strategy_backtest_agent/__pycache__/cli.pyc",
        "strategy_backtest_agent/.venv/config",
        "strategy_backtest_agent/build/old.txt",
        "strategy_backtest_agent/dist/nested.whl",
        "strategy_backtest_agent/.env",
    ],
)
def test_prohibited_and_unrelated_archive_contents_rejected(
    project: Path, wheel: bool, member: str
) -> None:
    files = contents(project, wheel)
    files[member] = b"synthetic dummy; never a real credential"
    with pytest.raises(ValueError):
        validate(write_archive(project, files, wheel), project)


@pytest.mark.parametrize("wheel", [True, False])
@pytest.mark.parametrize(
    "old,new",
    [
        ("Name: strategy-backtest-agent", "Name: other-name"),
        ("Name: strategy-backtest-agent", "Name: strategy-backtest-agent\nName: unexpected"),
        ("Version: 1.0.0", "Version: 9.9.9"),
        ("Requires-Python: >=3.12,<4.0", "Requires-Python: >=3.8"),
        ("Description-Content-Type: text/markdown", "Description-Content-Type: text/plain"),
        ("License: MIT", "License: different"),
        ("License-File: LICENSE", "License-File: missing.txt"),
        ("Requires-Dist: pandas (>=2.2,<3.0)", "Requires-Dist: pytest (>=8)"),
        ("Requires-Dist: pandas (>=2.2,<3.0)", "Requires-Dist: pandas (>=1.0)"),
        ("Offline research", "fabricated README"),
    ],
)
def test_wrong_metadata_is_rejected(project: Path, wheel: bool, old: str, new: str) -> None:
    files = contents(project, wheel)
    name = DIST + "/METADATA" if wheel else "PKG-INFO"
    files[name] = files[name].replace(old.encode(), new.encode())
    with pytest.raises(ValueError):
        validate(write_archive(project, files, wheel), project)


@pytest.mark.parametrize("missing", ["README.md", "pyproject.toml", ".env.example"])
def test_sdist_requires_project_and_description_files(project: Path, missing: str) -> None:
    files = contents(project, False)
    files.pop(missing)
    with pytest.raises(ValueError):
        validate(write_archive(project, files, False), project)


@pytest.mark.parametrize("kind", ["entry", "entry_syntax", "wheel", "license_contents"])
def test_wheel_entry_point_layout_and_legal_contents(project: Path, kind: str) -> None:
    files = contents(project, True)
    if kind == "entry":
        files[DIST + "/entry_points.txt"] = b"[console_scripts]\nstrategy-backtest=wrong:main\n"
    elif kind == "entry_syntax":
        files[DIST + "/entry_points.txt"] = b"not a valid entry point file"
    elif kind == "wheel":
        files[DIST + "/WHEEL"] = files[DIST + "/WHEEL"].replace(b"true", b"false")
    else:
        files[DIST + "/licenses/LICENSE"] = b"wrong legal text"
    with pytest.raises(ValueError):
        validate(write_archive(project, files, True), project)


@pytest.mark.parametrize("kind", ["traversal", "absolute", "symlink", "duplicate", "special"])
@pytest.mark.parametrize("wheel", [True, False])
def test_unsafe_archive_members_rejected(tmp_path: Path, kind: str, wheel: bool) -> None:
    path = tmp_path / ("bad.whl" if wheel else "bad.tar.gz")
    name = "../escape" if kind == "traversal" else "/absolute" if kind == "absolute" else "member"
    if wheel:
        with zipfile.ZipFile(path, "w") as archive:
            entry = zipfile.ZipInfo(name)
            if kind in ("symlink", "special"):
                entry.external_attr = (0o120777 if kind == "symlink" else 0o010644) << 16
            archive.writestr(entry, b"dummy")
            if kind == "duplicate":
                with pytest.warns(UserWarning, match="Duplicate"):
                    archive.writestr(name, b"dummy")
    else:
        with tarfile.open(path, "w:gz") as archive:
            tar_entry = tarfile.TarInfo(name)
            if kind in ("symlink", "special"):
                tar_entry.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.FIFOTYPE
                tar_entry.linkname = "outside"
            archive.addfile(tar_entry)
            if kind == "duplicate":
                archive.addfile(tar_entry)
    with pytest.raises(ValueError):
        read_archive(path)


@pytest.mark.parametrize("wheel", [True, False])
def test_equivalent_dependency_and_python_specifiers_are_accepted(
    project: Path, wheel: bool
) -> None:
    files = contents(project, wheel)
    key = DIST + "/METADATA" if wheel else "PKG-INFO"
    files[key] = (
        files[key]
        .replace(b">=2.2,<3.0", b"<3.0.0,>=2.2.0")
        .replace(b">=3.12,<4.0", b"<4.0.0,>=3.12.0")
    )
    validate(write_archive(project, files, wheel), project)
