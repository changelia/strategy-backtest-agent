"""Opt-in installed-artifact checks; never install dependencies during pytest.

Run with base Python: python tests/installed_smoke.py --venv /private/tmp/.../wheel-env
--work /private/tmp/.../wheel-work --checkout /absolute/checkout
The venv must already contain the distribution and work must be outside the checkout.
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


def clean_environment(venv: Path) -> dict[str, str]:
    """Do not inherit credentials, dotenv discovery, pip config, or Python overrides."""
    return {
        "PATH": f"{venv / 'bin'}{os.pathsep}{os.defpath}",
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYTHONUTF8": "1",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }


def check_demo(result: dict[str, Any]) -> None:
    for name, expected, tolerance in (
        ("initial_balance", 10000, 0),
        ("final_balance", 123.09, 0.01),
        ("total_return_percent", -98.77, 0.01),
        ("total_trades", 45, 0),
        ("winning_trades", 0, 0),
    ):
        assert math.isclose(result[name], expected, rel_tol=0, abs_tol=tolerance), name


def check_report(report: dict[str, Any], content: bytes) -> None:
    assert report["report_schema_version"] == "1.0"
    assert report["evidence"]["source"]["research_type"] == "backtest"
    assert (
        report["evidence"]["source"]["input_content_sha256"] == hashlib.sha256(content).hexdigest()
    )
    assert report["evidence"]["metrics"]
    assert len(report["evidence_sha256"]) == 64
    assert report["ai_interpretation"] is None


def check_source_metrics(report: dict[str, Any], source: dict[str, Any]) -> None:
    """Backtest evidence must retain source values, including undefined metrics."""
    for metric in report["evidence"]["metrics"]:
        if metric["id"].endswith(".net_pnl"):
            assert metric["value"] == source["final_balance"] - source["initial_balance"]
            continue
        value: Any = source
        for part in metric["source_path"].strip("/").split("/"):
            value = value[part]
        assert metric["value"] == value, metric["id"]


def project_version(checkout: Path) -> str:
    config = tomllib.loads((checkout / "pyproject.toml").read_text(encoding="utf-8"))
    return str(config["project"]["version"])


PROBE = r"""
import importlib.metadata as m, json, pathlib, site, sys
import strategy_backtest_agent
root = pathlib.Path(sys.prefix).resolve()
checkout = pathlib.Path(sys.argv[1]).resolve()
expected_version = sys.argv[2]
dist = m.distribution('strategy-backtest-agent')
origin = pathlib.Path(strategy_backtest_agent.__file__).resolve()
assert root in origin.parents and 'site-packages' in origin.parts
assert dist.version == expected_version
assert dist.metadata['Name'] == 'strategy-backtest-agent'
assert site.ENABLE_USER_SITE is False
assert 'include-system-site-packages = false' in (root/'pyvenv.cfg').read_text()
assert not any(p and pathlib.Path(p).resolve().is_relative_to(checkout) for p in sys.path)
entry = [e for e in dist.entry_points if e.name == 'strategy-backtest'][0]
assert entry.value == 'strategy_backtest_agent.cli:main'
assert entry.load().__module__ == 'strategy_backtest_agent.cli'
direct = json.loads(dist.read_text('direct_url.json'))
assert 'dir_info' not in direct and 'archive_info' in direct
for directory in site.getsitepackages():
    for pth in pathlib.Path(directory).glob('*.pth'):
        text = pth.read_text()
        assert str(checkout) not in text and '__editable__' not in text
print(json.dumps({'version':dist.version, 'import_path':str(origin),
 'prefix':str(root), 'python':sys.version, 'entry_point':entry.value,
 'direct_url':direct, 'sys_path':sys.path}))
"""

# Test instrumentation only: no installed application files are changed. Python's
# startup hook denies socket operations before application imports, without PYTHONPATH.
NETWORK_GUARD = """import os, sys

def _deny_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        with open(os.environ["SBA_NETWORK_AUDIT_LOG"], "a") as log:
            log.write(event + "\\n")
        raise RuntimeError("Network disabled for installed offline smoke tests")

sys.addaudithook(_deny_network)
"""

PUBLIC_API_PROBE = r"""
import hashlib, json
from strategy_backtest_agent import BacktestClient
client = BacktestClient()
config = client.template('backtest')
result = client.run(config=config, days=3, demo=True)
json_report = client.report(result, format='json')
markdown = client.report(result, format='markdown')
repeat = client.report(result, format='json')
assert json_report == repeat
report = json.loads(json_report)
assert report['evidence']['source']['research_type'] == 'backtest'
assert report['evidence']['source']['input_content_sha256']
assert report['evidence_sha256']
assert markdown and markdown.startswith('# Historical Strategy Research Report')
diagnostics = client.doctor()
assert diagnostics.offline_ready and not diagnostics.api_key_present
print(json.dumps({
  'result': result.model_dump(mode='json'),
  'evidence_sha256': report['evidence_sha256'],
  'input_content_sha256': report['evidence']['source']['input_content_sha256'],
  'markdown_sha256': hashlib.sha256(markdown.encode()).hexdigest(),
  'api_key_present': diagnostics.api_key_present,
  'offline_ready': diagnostics.offline_ready,
}))
"""


def smoke(venv: Path, work: Path, checkout: Path) -> dict[str, Any]:
    venv, work, checkout = venv.resolve(), work.resolve(), checkout.resolve()
    assert not work.is_relative_to(checkout) and not venv.is_relative_to(checkout)
    assert work.is_dir() and not list(work.iterdir()), "Use a fresh working directory"
    python, cli = venv / "bin/python", venv / "bin/strategy-backtest"
    assert cli.is_file() and str(venv / "bin/python") in cli.read_text().splitlines()[0]
    env = clean_environment(venv)

    def run(args: list[str], *, success: bool = True) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            args, cwd=work, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=120
        )
        if success:
            assert result.returncode == 0, result.stderr.decode()
        return result

    version = project_version(checkout)
    probe = json.loads(run([str(python), "-I", "-c", PROBE, str(checkout), version]).stdout)
    pip_check = run([str(python), "-m", "pip", "check"]).stdout.decode().strip()
    versions = json.loads(run([str(python), "-m", "pip", "list", "--format=json"]).stdout)
    pip_version = run([str(python), "-m", "pip", "--version"]).stdout.decode().strip()
    guard = Path(probe["import_path"]).parent.parent / "sitecustomize.py"
    assert not guard.exists(), "Refuse to overwrite existing startup customization"
    guard.write_text(NETWORK_GUARD)
    audit = work / "network-audit.log"
    env["SBA_NETWORK_AUDIT_LOG"] = str(audit)
    run(
        [str(python), "-I", "-c", "import sys; sys.audit('socket.connect', None, None)"],
        success=False,
    )
    assert audit.read_text() == "socket.connect\n", "Network guard was not loaded"
    audit.write_text("")
    try:
        for name, args in (
            ("help", ["--help"]),
            ("demo", ["--demo"]),
            ("report-help", ["report", "--help"]),
        ):
            (work / f"{name}.txt").write_bytes(run([str(cli), *args]).stdout)
        doctor_result = run([str(cli), "doctor"])
        assert b"Offline checks: available" in doctor_result.stdout
        assert b"OpenAI key: absent or empty" in doctor_result.stdout
        assert b"Dotenv: disabled" in doctor_result.stdout
        assert f"Installed package version: {version}".encode() in doctor_result.stdout
        assert not doctor_result.stderr
        (work / "doctor.txt").write_bytes(doctor_result.stdout)
        content = run([str(cli), "--demo", "--json"]).stdout
        (work / "demo.json").write_bytes(content)
        check_demo(json.loads(content))
        outputs: dict[str, str] = {}
        failures: dict[str, list[dict[str, Any]]] = {}
        for format_name in ("json", "markdown"):
            for suffix in ("first", "repeat"):
                output = work / f"report-{suffix}.{format_name}"
                result = run(
                    [
                        str(cli),
                        "report",
                        "--input",
                        str(work / "demo.json"),
                        "--format",
                        format_name,
                        "--output",
                        str(output),
                    ],
                    success=False,
                )
                if result.returncode:
                    assert not result.stdout and not output.exists()
                    assert b"Traceback" not in result.stderr
                    failures.setdefault(format_name, []).append(
                        {"exit": result.returncode, "stderr": result.stderr.decode().strip()}
                    )
                    continue
                assert not result.stdout
            if format_name in failures:
                continue
            first = (work / f"report-first.{format_name}").read_bytes()
            assert first == (work / f"report-repeat.{format_name}").read_bytes()
            assert first.strip()
            outputs[format_name] = hashlib.sha256(first).hexdigest()
        report = json.loads((work / "report-first.json").read_bytes())
        check_report(report, content)
        check_source_metrics(report, json.loads(content))
        # Also check JSON-only stdout, not just files.
        stdout = run(
            [str(cli), "report", "--input", str(work / "demo.json"), "--format", "json"]
        ).stdout
        assert json.loads(stdout) == report
        (work / "malformed.json").write_text('{"secret": "DO_NOT_ECHO_SYNTHETIC"')
        bad = run(
            [str(cli), "report", "--input", str(work / "malformed.json"), "--format", "json"],
            success=False,
        )
        assert bad.returncode == 2 and not bad.stdout
        assert b"Error:" in bad.stderr and b"Traceback" not in bad.stderr
        assert b"DO_NOT_ECHO_SYNTHETIC" not in bad.stderr
        doctor_bad = run(
            [str(cli), "doctor", "--type", "backtest", "--config", str(work / "malformed.json")],
            success=False,
        )
        assert doctor_bad.returncode == 1
        assert b"ERROR research config invalid/unreadable" in doctor_bad.stdout
        assert b"DO_NOT_ECHO_SYNTHETIC" not in doctor_bad.stdout + doctor_bad.stderr
        api_receipt = json.loads(run([str(python), "-I", "-c", PUBLIC_API_PROBE]).stdout)
        assert api_receipt["offline_ready"] and not api_receipt["api_key_present"]
        (work / "public-api.json").write_text(json.dumps(api_receipt, allow_nan=False))
        init_templates = {}
        for kind in ("backtest", "compare", "validate", "walk-forward"):
            config = work / f"init-{kind}.json"
            args = [str(cli), "init", "--type", kind, "--output", str(config)]
            run(args)
            original = config.read_bytes()
            if kind == "backtest":
                doctor_config = run([str(cli), "doctor", "--type", kind, "--config", str(config)])
                assert b"Research config: valid backtest model" in doctor_config.stdout
            duplicate = run(args, success=False)
            assert duplicate.returncode == 2 and b"Error:" in duplicate.stderr
            assert config.read_bytes() == original
            command = [str(cli)] + ([] if kind == "backtest" else [kind])
            result_content = run([*command, "--config", str(config), "--demo", "--json"]).stdout
            generated = json.loads(result_content)
            source = generated.get("data_source") or generated["shared_data"]["source"]
            assert source == "synthetic_demo"
            init_templates[kind] = {
                "config_sha256": hashlib.sha256(original).hexdigest(),
                "result_sha256": hashlib.sha256(result_content).hexdigest(),
                "overwrite_exit": duplicate.returncode,
            }
        assert not audit.read_text(), "Application attempted network access"
        return {
            "status": "BLOCKED" if failures else "READY",
            "report_failures": failures,
            "installation": probe,
            "pip_check": pip_check,
            "pip_version": pip_version,
            "dependencies": versions,
            "cli": str(cli),
            "demo": json.loads(content),
            "report_sha256": outputs,
            "evidence_sha256": report["evidence_sha256"],
            "negative_exit": bad.returncode,
            "negative_error": bad.stderr.decode().strip(),
            "network_attempts": 0,
            "init_templates": init_templates,
            "doctor": {
                "exit": doctor_result.returncode,
                "invalid_config_exit": doctor_bad.returncode,
            },
            "public_api": {
                "evidence_sha256": api_receipt["evidence_sha256"],
                "input_content_sha256": api_receipt["input_content_sha256"],
                "markdown_sha256": api_receipt["markdown_sha256"],
                "final_balance": api_receipt["result"]["final_balance"],
            },
        }
    finally:
        guard.unlink()  # Only this helper's own temporary instrumentation.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args()
    receipt = smoke(args.venv, args.work, args.checkout)
    print(json.dumps(receipt, indent=2, allow_nan=False))
    sys.exit(1 if receipt["status"] == "BLOCKED" else 0)


if __name__ == "__main__":
    main()
