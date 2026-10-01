"""transcribe.py(Rich UI の対話型 CLI)の入力種別ごとの起動確認。"""

import sys

import pytest

import transcribe


@pytest.fixture
def loader(monkeypatch):
    """設定読み込みと実処理を差し替えた TranscribeLoader。

    run() が入力種別を判定して process_with_progress() を呼ぶまでを対象にする
    (ダウンロードやモデルロードは行わない)。
    """
    monkeypatch.setattr(transcribe.UnifiedConfig, "load", lambda *args, **kwargs: None)
    loader = transcribe.TranscribeLoader()
    calls = []
    monkeypatch.setattr(
        loader,
        "process_with_progress",
        lambda input_info, settings, folder_id=None: calls.append(input_info),
    )
    loader.calls = calls
    return loader


@pytest.mark.parametrize(
    "source, expected_type",
    [
        ("https://www.youtube.com/watch?v=abc123", "youtube"),
        ("https://x.com/someone/status/1234567890/video/1", "twitter"),
        ("https://twitter.com/someone/status/1234567890", "twitter"),
        ("https://drive.google.com/file/d/FILEID/view", "gdrive"),
    ],
)
def test_run_starts_processing_for_each_supported_url_type(loader, monkeypatch, source, expected_type):
    monkeypatch.setattr(sys, "argv", ["transcribe.py", source])

    assert loader.run() == 0
    assert loader.calls == [{"type": expected_type, "source": source}]


def test_run_starts_processing_for_local_file(loader, monkeypatch, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"")
    monkeypatch.setattr(sys, "argv", ["transcribe.py", str(audio)])

    assert loader.run() == 0
    assert loader.calls == [{"type": "local", "source": str(audio)}]


def test_run_rejects_unrecognized_input(loader, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["transcribe.py", str(tmp_path / "missing.wav")])

    assert loader.run() == 1
    assert loader.calls == []
