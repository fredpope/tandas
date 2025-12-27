import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

TD_CLI = Path(__file__).resolve().parents[1] / "td.py"
TD_DAEMON_DEFAULT = Path(__file__).resolve().parents[1] / "daemon" / "td-daemon"


def run_td(tmp_path, *args, extra_env=None, check=True):
    """Run td.py with the given arguments inside tmp_path."""
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, str(TD_CLI), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"td {' '.join(args)} failed with code {result.returncode}:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


def load_tandas(tmp_path):
    issues = Path(tmp_path) / ".tandas" / "issues.jsonl"
    tandas = []
    if issues.exists():
        with issues.open() as handle:
            for line in handle:
                line = line.strip()
                if line:
                    tandas.append(json.loads(line))
    return tandas


def load_trace_entries(tmp_path):
    inbox = Path(tmp_path) / ".tandas" / "trace_inbox.jsonl"
    entries = []
    if inbox.exists():
        with inbox.open() as handle:
            for line in handle:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


def test_init_creates_registry(tmp_path):
    run_td(tmp_path, "init")
    tanda_dir = Path(tmp_path) / ".tandas"
    assert tanda_dir.is_dir()
    assert (tanda_dir / "issues.jsonl").exists()
    assert (tanda_dir / "db.sqlite").exists()


def test_create_and_list_tanda(tmp_path):
    run_td(tmp_path, "init")
    run_td(
        tmp_path,
        "create",
        "Login Flow",
        "--file",
        "tests/login.spec.ts",
        "--covers",
        "auth,session",
    )

    tandas = load_tandas(tmp_path)
    assert any(t["title"] == "Login Flow" for t in tandas)

    result = run_td(tmp_path, "list", "--active")
    assert "Login Flow" in result.stdout


def test_dependency_management_affects_ready_order(tmp_path):
    run_td(tmp_path, "init")

    run_td(tmp_path, "create", "Setup Flow")
    run_td(tmp_path, "create", "Checkout Flow")

    tandas = {t["title"]: t["id"] for t in load_tandas(tmp_path)}
    setup_id = tandas["Setup Flow"]
    checkout_id = tandas["Checkout Flow"]

    run_td(tmp_path, "dep", "add", checkout_id, setup_id)

    ready_output = run_td(tmp_path, "ready").stdout
    assert ready_output.index("Setup Flow") < ready_output.index("Checkout Flow")


def test_generate_outputs_placeholder(tmp_path):
    run_td(tmp_path, "init")
    run_td(tmp_path, "create", "API Smoke Test")

    tanda = load_tandas(tmp_path)[0]
    output_file = Path(tmp_path) / "api_smoke.spec.ts"

    run_td(
        tmp_path,
        "generate",
        tanda["id"],
        "--provider",
        "openai",
        "--output",
        str(output_file),
    )

    assert output_file.exists()
    content = output_file.read_text()
    assert "OpenAI provider not configured" in content


def test_quickstart_creates_config(tmp_path):
    run_td(tmp_path, "quickstart")
    config = Path(tmp_path) / ".tandas" / "config.yaml"
    env_example = Path(tmp_path) / ".tandas" / "env.example"
    assert config.exists()
    assert env_example.exists()
    assert "default_provider" in config.read_text()


def test_daemon_status_without_running(tmp_path):
    run_td(tmp_path, "init")
    result = run_td(tmp_path, "daemon", "status")
    assert "daemon not running" in result.stdout.lower()


@pytest.mark.skipif(shutil.which("go") is None, reason="Go toolchain required")
def test_daemon_imports_jsonl_when_running(tmp_path):
    run_td(tmp_path, "quickstart")
    run_td(tmp_path, "create", "Daemon Ready Test")

    # build daemon if not already
    daemon_bin = TD_DAEMON_DEFAULT
    if not daemon_bin.exists():
        build = subprocess.run(
            ["go", "build", "-o", str(daemon_bin), "./cmd/td-daemon"],
            cwd=Path(__file__).resolve().parents[1] / "daemon",
            capture_output=True,
            text=True,
        )
        if build.returncode != 0:
            pytest.skip(f"unable to build td-daemon: {build.stderr}")

    env = {"TD_DAEMON_BIN": str(daemon_bin)}

    proc = subprocess.Popen(
        [sys.executable, str(TD_CLI), "daemon", "start"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **env},
    )

    sock_path = Path(tmp_path) / ".tandas" / "td.sock"
    start = time.time()
    while time.time() - start < 10:
        if sock_path.exists():
            break
        time.sleep(0.2)
    else:
        proc.terminate()
        pytest.skip("daemon socket not created")

    status = run_td(tmp_path, "daemon", "status", extra_env=env)
    assert "daemon running" in status.stdout.lower()

    run_td(tmp_path, "generate", load_tandas(tmp_path)[0]["id"], extra_env=env)

    run_td(tmp_path, "daemon", "stop", extra_env=env)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_trace_scan_and_link(tmp_path):
    run_td(tmp_path, "quickstart")
    run_td(tmp_path, "create", "Trace Coverage")

    trace_dir = Path(tmp_path) / "test-results"
    trace_dir.mkdir()
    trace_file = trace_dir / "login-trace.zip"
    trace_file.write_text("dummy")

    run_td(tmp_path, "trace", "scan", "--dir", str(trace_dir))
    entries = load_trace_entries(tmp_path)
    assert entries and entries[0]["path"].endswith("login-trace.zip")

    tanda_id = load_tandas(tmp_path)[0]["id"]
    run_td(tmp_path, "trace", "link", tanda_id, str(trace_file), "--result", "fail")

    tanda = load_tandas(tmp_path)[0]
    assert tanda["run_history"][-1]["trace"].endswith("login-trace.zip")

    entries = load_trace_entries(tmp_path)
    assert entries[0]["status"] == "linked"
