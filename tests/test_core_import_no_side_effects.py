"""`import core` が副作用(ルートロガー付け替え・ログファイル作成)を持たないことの検査(Task 5.6)。

pytest自身のプロセスはconftest等の影響を受けるため、別プロセスで検査する。
"""
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

_PROBE = """
import logging, sys
sys.path.insert(0, {root!r})
before = list(logging.getLogger().handlers)
import core  # noqa: F401
import core.logging, core.config, core.utils  # noqa: F401
after = list(logging.getLogger().handlers)
print("HANDLERS_ADDED=%d" % (len(after) - len(before)))
"""


def _run(code: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code.format(root=str(PROJECT_ROOT))],
        cwd=cwd, capture_output=True, text=True, timeout=120,
    )


def test_import_core_creates_no_log_file(tmp_path):
    result = _run(_PROBE, tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "logs").exists()
    assert list(tmp_path.iterdir()) == []


def test_import_core_does_not_add_root_handlers(tmp_path):
    result = _run(_PROBE, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "HANDLERS_ADDED=0" in result.stdout


def test_get_logger_does_not_create_log_file_on_import(tmp_path):
    code = _PROBE + "\nfrom core.logging import get_logger\nget_logger('x').info('hi')\n"
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "logs").exists()


def test_setup_logging_creates_log_file_and_is_idempotent(tmp_path):
    code = """
import logging, sys
sys.path.insert(0, {root!r})
from core.logging import setup_logging, get_logger
setup_logging()
n1 = len(logging.getLogger().handlers)
setup_logging()
n2 = len(logging.getLogger().handlers)
get_logger("probe").info("hello-from-probe")
print("N=%d,%d" % (n1, n2))
"""
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "N=2,2" in result.stdout
    log = tmp_path / "logs" / "transcription.log"
    assert log.exists()
    assert "hello-from-probe" in log.read_text(encoding="utf-8")


def test_setup_logging_under_pytest_uses_test_log_file(tmp_path, monkeypatch):
    import logging
    from core.logging import UnifiedLogger, setup_logging
    import core.logging as core_logging

    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    saved_state = (UnifiedLogger._log_file, UnifiedLogger._configured, UnifiedLogger._log_level)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core_logging, "_setup_done", False, raising=False)
    try:
        setup_logging()
        assert UnifiedLogger._log_file == "logs/transcription_test.log"
        assert (tmp_path / "logs" / "transcription_test.log").exists()
        assert not (tmp_path / "logs" / "transcription.log").exists()
    finally:
        for h in list(root.handlers):
            if h not in saved_handlers:
                h.close()
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        UnifiedLogger._log_file, UnifiedLogger._configured, UnifiedLogger._log_level = saved_state
