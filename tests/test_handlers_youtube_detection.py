"""
yt-dlp の検出を 1 つの方法に揃える(D6。tc-ops #567 Task 5.3)。

- 検出は handlers.youtube.find_yt_dlp() の 1 本。YouTubeClient.yt_dlp_path と
  check_yt_dlp_installed() は同じ結果を使う(食い違わない)。
- 自動 pip install はしない。見つからなければ uv sync を案内するエラーで止める。
"""

import stat
import sys

import pytest

from handlers import youtube
from handlers.youtube import YouTubeClient, YtDlpNotFoundError, check_yt_dlp_installed, find_yt_dlp


def _make_exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """PATH・現在の Python・cwd のどれにも yt-dlp が無い状態。"""
    monkeypatch.setattr(youtube.shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pybin" / "python"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return tmp_path


def test_returns_none_when_not_found(isolated):
    assert find_yt_dlp() is None
    assert check_yt_dlp_installed() is False


def test_which_has_priority(isolated, monkeypatch):
    exe = _make_exe(isolated / "sys" / "yt-dlp")
    _make_exe(isolated / "pybin" / "yt-dlp")
    monkeypatch.setattr(youtube.shutil, "which", lambda name: str(exe))

    assert find_yt_dlp() == str(exe)


def test_finds_yt_dlp_next_to_current_python(isolated):
    exe = _make_exe(isolated / "pybin" / "yt-dlp")

    assert find_yt_dlp() == str(exe)
    assert check_yt_dlp_installed() is True


def test_finds_cwd_venv_as_last_resort(isolated):
    _make_exe(isolated / "work" / ".venv" / "bin" / "yt-dlp")

    assert find_yt_dlp() == ".venv/bin/yt-dlp"


def test_non_executable_file_is_ignored(isolated):
    (isolated / "pybin").mkdir()
    (isolated / "pybin" / "yt-dlp").write_text("not executable")

    assert find_yt_dlp() is None


def test_client_path_and_check_agree(isolated):
    exe = _make_exe(isolated / "pybin" / "yt-dlp")

    assert YouTubeClient().yt_dlp_path == str(exe)
    assert check_yt_dlp_installed() is True


def test_client_falls_back_to_bare_command_name_when_not_found(isolated):
    assert YouTubeClient().yt_dlp_path == "yt-dlp"


def test_check_does_not_spawn_processes(isolated, monkeypatch):
    monkeypatch.setattr(youtube.subprocess, "run", lambda *a, **k: pytest.fail("subprocess は使わない"))

    check_yt_dlp_installed()
    YouTubeClient()


def test_no_auto_install_function_remains():
    assert not hasattr(youtube, "install_yt_dlp")


def test_resolve_input_audio_stops_with_uv_sync_hint(isolated, monkeypatch, tmp_path):
    from core.cli_workflow import resolve_input_audio

    created = []
    monkeypatch.setattr(youtube, "YouTubeClient", lambda *a, **k: created.append(1))
    monkeypatch.setattr(youtube.subprocess, "run", lambda *a, **k: pytest.fail("pip install 等を実行しない"))

    with pytest.raises(YtDlpNotFoundError) as excinfo:
        resolve_input_audio("https://www.youtube.com/watch?v=abc123", tmp_path, ensure_yt_dlp=True)

    assert "uv sync" in str(excinfo.value)
    assert "pip" not in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)  # tc は ValueError を exit 1 で処理する
    assert created == []


def test_resolve_input_audio_without_ensure_does_not_check(isolated, monkeypatch, tmp_path):
    from core.cli_workflow import resolve_input_audio

    class Boom(Exception):
        pass

    def fake_client(*a, **k):
        raise Boom()

    monkeypatch.setattr(youtube, "YouTubeClient", fake_client)

    with pytest.raises(Boom):  # 検出エラーではなくクライアント生成まで進む
        resolve_input_audio("https://www.youtube.com/watch?v=abc123", tmp_path, ensure_yt_dlp=False)
