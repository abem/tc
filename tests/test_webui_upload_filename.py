"""WebUIのアップロードファイル名の安全化(tc-ops #567 範囲外で見つけた問題の対応)。

Streamlitの`UploadedFile.name`はクライアントが送った文字列をそのまま返す(`../`や区切り文字を含み得る)。
`webui._resolve_input()`はこれを`output/uploads/`に連結して書き込むため、`output/uploads/`の外へ
書き込めてしまう余地があった。
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import webui
from core.utils import sanitize_upload_filename


class TestSanitizeUploadFilename:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("meeting.wav", "meeting.wav"),
            ("会議 録音.m4a", "会議 録音.m4a"),
            ("../../../tmp/evil.wav", "evil.wav"),
            ("..\\..\\windows\\evil.wav", "evil.wav"),
            ("/etc/passwd", "passwd"),
            ("a/b/c.mp3", "c.mp3"),
            ("dir/..", "upload"),
            ("..", "upload"),
            (".", "upload"),
            ("", "upload"),
            ("   ", "upload"),
            ("evil\x00.wav", "evil.wav"),
            ("line\nbreak.wav", "linebreak.wav"),
        ],
    )
    def test_sanitizes_to_a_plain_file_name(self, raw, expected):
        assert sanitize_upload_filename(raw) == expected

    def test_non_string_falls_back_to_default(self):
        assert sanitize_upload_filename(None) == "upload"

    def test_custom_default(self):
        assert sanitize_upload_filename("..", default="audio") == "audio"

    def test_long_name_is_shortened_but_keeps_extension(self):
        result = sanitize_upload_filename("a" * 500 + ".wav")

        assert len(result) <= 200
        assert result.endswith(".wav")

    def test_result_never_contains_a_path_separator(self):
        for raw in ["a/b", "a\\b", "../x", "..\\x", "x/..", "/", "\\"]:
            result = sanitize_upload_filename(raw)
            assert "/" not in result and "\\" not in result
            assert result not in {"", ".", ".."}


class TestResolveInputUpload:
    def _upload(self, name, data=b"RIFFdata"):
        return SimpleNamespace(name=name, getbuffer=lambda: data)

    @pytest.mark.parametrize(
        "evil_name", ["../../outside.wav", "..\\..\\outside.wav", "/tmp/should-not-be-here.wav"]
    )
    def test_malicious_name_is_written_only_inside_output_uploads(self, tmp_path, monkeypatch, evil_name):
        monkeypatch.chdir(tmp_path)
        form = {"source_url": "", "uploaded_file": self._upload(evil_name)}

        resolution = webui._resolve_input(form, tmp_path / "dl", on_status=lambda m: None)

        written = Path(resolution.local_audio_path).resolve()
        assert written.parent == (tmp_path / "output" / "uploads").resolve()
        assert written.read_bytes() == b"RIFFdata"
        outside = [p for p in tmp_path.rglob("*") if p.is_file() and (tmp_path / "output" / "uploads") not in p.parents]
        assert outside == []
        assert resolution.source_type == "local"
        assert resolution.is_temp_file is False

    def test_normal_name_is_kept(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        form = {"source_url": "", "uploaded_file": self._upload("meeting.wav")}

        resolution = webui._resolve_input(form, tmp_path / "dl", on_status=lambda m: None)

        assert Path(resolution.local_audio_path).name == "meeting.wav"
