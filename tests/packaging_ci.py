"""Opt-in CI packaging orchestration; never runs during ordinary pytest collection.

Requires build, twine and packaging in this Python environment. All generated
files, clean installs and application working directories stay in --work outside
the checkout. Build/install may use PyPI; installed application checks deny sockets.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from distribution_check import validate
from installed_smoke import clean_environment, smoke


def compare_receipts(wheel: dict[str, Any], sdist: dict[str, Any]) -> None:
    for receipt in (wheel, sdist):
        if receipt["status"] != "READY" or receipt["report_failures"]:
            raise ValueError("Installed smoke receipt is BLOCKED")
        if receipt["network_attempts"] != 0:
            raise ValueError("Installed application attempted network access")
        if set(receipt["report_sha256"]) != {"json", "markdown"}:
            raise ValueError("Missing installed report format")
    for key in ("demo", "report_sha256", "evidence_sha256", "init_templates"):
        if wheel[key] != sdist[key]:
            raise ValueError(f"Wheel/sdist outputs differ: {key}")


def verify_archive_origin(receipt: dict[str, Any], artifact: Path) -> None:
    direct = receipt["installation"]["direct_url"]
    if direct["url"] != artifact.as_uri() or "dir_info" in direct:
        raise ValueError("Installed provenance does not identify the supplied archive")
    actual = direct["archive_info"]["hashes"]["sha256"]
    if actual != hashlib.sha256(artifact.read_bytes()).hexdigest():
        raise ValueError("Installed archive hash does not match the fresh artifact")


def prepare_work(checkout: Path, work: Path) -> None:
    if work.is_relative_to(checkout):
        raise ValueError("Packaging workspace must be outside the checkout")
    work.mkdir(parents=True, exist_ok=True)
    if list(work.iterdir()):
        raise ValueError("Packaging workspace must be fresh and empty")


def run(checkout: Path, work: Path) -> None:
    checkout, work = checkout.resolve(), work.resolve()
    prepare_work(checkout, work)
    python = str(Path(sys.executable).absolute())
    env = clean_environment(Path(sys.prefix))

    def command(args: list[str], log_name: str, cwd: Path = work) -> None:
        print(f"Packaging step: {log_name}", flush=True)
        with (work / f"{log_name}.log").open("wb") as log:
            subprocess.run(
                args,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=900,
            )

    artifacts = work / "artifacts"
    command(
        [
            python,
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "--verbose",
            "--outdir",
            str(artifacts),
            str(checkout),
        ],
        "build",
    )
    wheels, sdists = list(artifacts.glob("*.whl")), list(artifacts.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Expected exactly one fresh wheel and one sdist")
    wheel, sdist = wheels[0], sdists[0]
    command([python, "-m", "twine", "check", "--strict", str(wheel), str(sdist)], "metadata")
    inventories = [validate(artifact, checkout) for artifact in (wheel, sdist)]
    (work / "archive-inspection.json").write_text(json.dumps(inventories, indent=2))
    receipts = []
    for kind, artifact in (("wheel", wheel), ("sdist", sdist)):
        venv, cwd = work / f"{kind}-env", work / f"{kind}-work"
        cwd.mkdir()
        command([python, "-m", "venv", str(venv)], f"{kind}-venv")
        installed_python = str(venv / "bin/python")
        command(
            [
                installed_python,
                "-I",
                "-c",
                "import importlib.util; assert importlib.util.find_spec('strategy_backtest_agent')"
                " is None",
            ],
            f"{kind}-empty",
        )
        command(
            [
                installed_python,
                "-m",
                "pip",
                "install",
                "--index-url",
                "https://pypi.org/simple",
                "--no-cache-dir",
                "--use-pep517",
                "--verbose",
                "--report",
                str(work / f"{kind}-install.json"),
                str(artifact),
            ],
            f"{kind}-install",
        )
        receipt = smoke(venv, cwd, checkout)
        (work / f"{kind}-receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False))
        verify_archive_origin(receipt, artifact)
        receipts.append(receipt)
    compare_receipts(*receipts)
    for filename in ("demo.json", "report-first.json", "report-first.markdown"):
        if (work / "wheel-work" / filename).read_bytes() != (
            work / "sdist-work" / filename
        ).read_bytes():
            raise ValueError(f"Wheel/sdist output bytes differ: {filename}")
    print("Packaging validation READY: both isolated installs and offline reports match.")
    print(f"Logs, archives and receipts: {work}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    run(args.checkout, args.work)


if __name__ == "__main__":
    main()
