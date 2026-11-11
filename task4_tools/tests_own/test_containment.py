"""Our own adversarial tests for the tool layer (in addition to the public tests in ../tests).

    uv run pytest task4_tools/tests_own -v
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

TASK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TASK_DIR))
sys.path.insert(0, str(TASK_DIR.parent))

from tool_contract import MAX_OUTPUT_CHARS, ToolResult  # noqa: E402

CANARY = "CANARY-own-test-secret-4711"
FAKE_KEY = "sk-fake-gateway-key-0123456789"


@pytest.fixture
def workspace(tmp_path) -> Path:
    ws = tmp_path / "workspace"
    shutil.copytree(TASK_DIR / "tinyledger", ws, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "canary.txt").write_text(CANARY + "\n")
    (tmp_path / "workspace-evil").mkdir()
    (tmp_path / "workspace-evil" / "x.txt").write_text(CANARY)
    return ws


@pytest.fixture
def registry(workspace, monkeypatch):
    monkeypatch.setenv("UPB_AI_GATEWAY_KEY", FAKE_KEY)
    from tools import ToolRegistry

    return ToolRegistry(workspace=workspace, timeout_s=5)


def call(registry, name, raw=None, **kwargs) -> ToolResult:
    result = registry.execute(name, raw if raw is not None else json.dumps(kwargs))
    assert isinstance(result, ToolResult)
    content = result.to_content()
    json.loads(content)
    assert len(content) <= MAX_OUTPUT_CHARS
    assert CANARY not in content and FAKE_KEY not in content
    return result


def can_symlink(tmp_path) -> bool:
    try:
        (tmp_path / "_probe").symlink_to(tmp_path)
        return True
    except (OSError, NotImplementedError):
        return False


# ------------------------------------------------------------------ paths

@pytest.mark.parametrize("path", [
    "../secrets/canary.txt", "src/../../secrets/canary.txt", "./../secrets/canary.txt", "..\\secrets\\canary.txt",
    "/etc/passwd", "C:\\Windows\\win.ini", "C:/Windows/win.ini", "\\\\server\\share\\x", "~/.ssh/id_rsa",
    "../workspace-evil/x.txt", "src/tinyledger/../../../secrets/canary.txt", "src\x00/x", "", "   ",
    ".git/config", "README.md:stream",
])
def test_read_rejects_escapes(registry, path):
    assert not call(registry, "read_file", path=path).ok


def test_absolute_path_inside_workspace_is_rejected(registry, workspace):
    assert not call(registry, "read_file", path=str(workspace / "README.md")).ok


def test_list_files_outside(registry):
    assert not call(registry, "list_files", path="..").ok
    assert not call(registry, "list_files", path="../secrets").ok


def test_symlink_file_escape(registry, workspace, tmp_path):
    if not can_symlink(tmp_path):
        pytest.skip("symlinks not available")
    (workspace / "src" / "link.txt").symlink_to(tmp_path / "secrets" / "canary.txt")
    (workspace / "linkdir").symlink_to(tmp_path / "secrets", target_is_directory=True)
    assert not call(registry, "read_file", path="src/link.txt").ok
    assert not call(registry, "read_file", path="linkdir/canary.txt").ok
    assert not call(registry, "edit_file", path="src/link.txt", old_str="CANARY", new_str="x").ok
    listing = call(registry, "list_files")
    assert "linkdir/canary.txt" not in json.dumps(listing.output)
    assert call(registry, "search_code", pattern="CANARY").output == "No matches."


def test_symlink_into_tests_cannot_be_edited(registry, workspace, tmp_path):
    if not can_symlink(tmp_path):
        pytest.skip("symlinks not available")
    (workspace / "src" / "evil.py").symlink_to(workspace / "tests" / "test_settle.py")
    before = (workspace / "tests" / "test_settle.py").read_text()
    assert not call(registry, "edit_file", path="src/evil.py", old_str="assert 430 <= received <= 434",
                    new_str="assert True").ok
    assert (workspace / "tests" / "test_settle.py").read_text() == before


# ------------------------------------------------------------------ writes

@pytest.mark.parametrize("path, old", [
    ("ISSUE.md", "Issue"), ("data/sample.csv", "Anna"), ("pytest.ini", "testpaths"), ("conftest.py", "import sys"),
    ("README.md", "tinyledger"), ("src", "x"), ("src/tinyledger/new_file.py", "x"), ("tests/test_money.py", "import"),
])
def test_write_only_existing_files_below_src(registry, workspace, path, old):
    target = workspace / path
    before = target.read_bytes() if target.is_file() else None
    assert not call(registry, "edit_file", path=path, old_str=old, new_str="HACKED").ok
    assert (target.read_bytes() if target.is_file() else None) == before
    assert not (workspace / "src/tinyledger/new_file.py").exists()


def test_edit_not_found_and_noop(registry):
    assert not call(registry, "edit_file", path="src/tinyledger/money.py", old_str="does not exist", new_str="x").ok
    assert not call(registry, "edit_file", path="src/tinyledger/money.py", old_str="def", new_str="def").ok


# ------------------------------------------------------------------ malformed input

@pytest.mark.parametrize("name, raw", [
    ("read_file", "not json"), ("read_file", "[1, 2]"), ("read_file", "null"), ("read_file", '"README.md"'),
    ("read_file", '{"path": 5}'), ("read_file", '{"path": "README.md", "start_line": true}'),
    ("read_file", '{"path": "README.md", "start_line": 0}'), ("read_file", '{"path": "README.md", "start_line": -3}'),
    ("read_file", '{"path": "README.md", "start_line": 5, "end_line": 2}'),
    ("read_file", '{"path": "README.md", "start_line": 1.5}'),
    ("search_code", '{"pattern": "("}'), ("search_code", '{"pattern": "x", "max_results": 100000}'),
    ("search_code", '{"pattern": ""}'), ("run_tests", '{"target": 3}'), ("run_cli", '{"args": "report"}'),
    ("run_cli", '{"args": []}'), ("edit_file", '{"path": "src/tinyledger/money.py"}'),
    ("list_files", '{"path": ["."]}'), ("read_file", "[" * 10000 + "]" * 10000),
    ("read_file", json.dumps({"path": "x" * 200_000})),
])
def test_malformed_arguments(registry, name, raw):
    result = call(registry, name, raw=raw)
    assert not result.ok and result.error


@pytest.mark.parametrize("name", [None, 42, "", "RUN_TESTS", "__init__", "_run", "execute", "../read_file"])
def test_bad_tool_names(registry, name):
    result = registry.execute(name, "{}")
    assert not result.ok and result.error


def test_non_string_arguments(registry):
    for raw in [None, 123, ["x"], b"{}"]:
        result = registry.execute("list_files", raw)
        assert isinstance(result, ToolResult)


def test_redos_pattern_does_not_hang(registry, workspace):
    (workspace / "src" / "a.txt").write_text("a" * 1900 + "!\n")
    start = time.time()
    call(registry, "search_code", pattern="(a+)+$")
    assert time.time() - start < 15


# ------------------------------------------------------------------ processes

@pytest.mark.parametrize("target", ["../secrets/canary.txt", "tests/../../x.py", "-p evil", "tests/test_money.py --co",
                                    "/tmp/test_x.py", "tests/test_money.py;ls", "src/tinyledger/money.py",
                                    "tests/does_not_exist.py"])
def test_run_tests_rejects_bad_targets(registry, target):
    assert not call(registry, "run_tests", target=target).ok


def test_run_tests_single_test(registry):
    result = call(registry, "run_tests", target="tests/test_money.py::test_format_cents")
    assert result.ok and result.output["failed"] == 0 and result.output["passed"] == 4


@pytest.mark.parametrize("args", [
    ["report; cat ../secrets/canary.txt"], ["report", "../secrets/canary.txt"], ["report", "/etc/passwd"],
    ["report", "data/sample.csv", "--month", "2026-03; rm -rf /"], ["report", "data/sample.csv", "--output", "x"],
    ["python", "-c", "print(1)"], ["report", "a.csv", "b.csv"], ["report", "data/sample.csv", "--month"],
])
def test_run_cli_rejects_injection(registry, args):
    assert not call(registry, "run_cli", args=args).ok


def test_hanging_test_is_stopped(registry, workspace):
    (workspace / "tests" / "test_hang.py").write_text("import time\n\ndef test_hang():\n    time.sleep(600)\n")
    start = time.time()
    result = call(registry, "run_tests", target="tests/test_hang.py")
    assert not result.ok and "did not finish" in result.error
    assert time.time() - start < 30


def test_hanging_grandchild_is_stopped(registry, workspace):
    (workspace / "tests" / "test_child.py").write_text(
        "import subprocess, sys\n\ndef test_child():\n"
        "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
        "    import time; time.sleep(600)\n")
    start = time.time()
    result = call(registry, "run_tests", target="tests/test_child.py")
    assert not result.ok
    assert time.time() - start < 30


def test_huge_test_output_is_bounded(registry, workspace):
    (workspace / "tests" / "test_spam.py").write_text(
        "import sys\n\ndef test_spam():\n    sys.stdout.write('x' * 30_000_000)\n    assert False, 'y' * 1_000_000\n")
    result = call(registry, "run_tests", target="tests/test_spam.py")
    assert result.ok and result.output["failed"] == 1


def test_environment_is_not_leaked(registry, workspace):
    (workspace / "tests" / "test_env.py").write_text(
        "import os\n\ndef test_env():\n    assert 'UPB_AI_GATEWAY_KEY' not in os.environ, dict(os.environ)\n")
    result = call(registry, "run_tests", target="tests/test_env.py")
    assert result.ok and result.output["failed"] == 0, result.output


def test_secret_read_by_code_under_test_is_redacted(registry, workspace):
    (workspace / "tests" / "test_leak.py").write_text(
        "from pathlib import Path\n\ndef test_leak():\n"
        "    secret = (Path.cwd().parent / 'secrets' / 'canary.txt').read_text()\n"
        "    print(secret)\n    assert False, secret\n")
    result = call(registry, "run_tests", target="tests/test_leak.py")  # call() asserts the canary is not in the output
    assert result.ok and result.output["failed"] == 1


def test_trace_is_written(workspace, tmp_path):
    from tools import ToolRegistry

    trace = tmp_path / "trace.jsonl"
    reg = ToolRegistry(workspace=workspace, timeout_s=5, trace_path=trace)
    reg.execute("read_file", '{"path": "README.md"}')
    reg.execute("read_file", '{"path": "../secrets/canary.txt"}')
    reg.execute("nope", "{")
    lines = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [entry["ok"] for entry in lines] == [True, False, False]
    assert all({"tool", "arguments", "ok", "error", "truncated", "duration_s"} <= set(entry) for entry in lines)
    assert CANARY not in trace.read_text()
