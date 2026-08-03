"""
Tests for tc(CLIスクリプト、拡張子無し)の save_result()/_format_mmss()。

tcは拡張子無しスクリプトのため通常のimportができず、importlib経由で
モジュールとして動的ロードする。GPU/ネットワークは一切使用しない。
"""

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

TC_PATH = Path(__file__).resolve().parents[1] / "tc"


def _load_tc_module():
    # tcは拡張子無しのため、spec_from_file_locationに拡張子から推測させず
    # SourceFileLoaderを明示指定する。
    loader = SourceFileLoader("tc_cli_under_test", str(TC_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tc_module():
    return _load_tc_module()


def _make_result(tc_module, segments, text, timestamps_included):
    from core.transcription_interface import TranscriptionResult

    return TranscriptionResult(
        text=text,
        segments=segments,
        language="ja",
        duration=10.0,
        processing_time=1.0,
        model_name="Qwen/Qwen3-ASR-1.7B",
        has_speakers=False,
        metadata={"timestamps_included": timestamps_included},
    )


class TestFormatMMSS:
    def test_zero(self, tc_module):
        assert tc_module._format_mmss(0) == "00:00"

    def test_under_a_minute(self, tc_module):
        assert tc_module._format_mmss(45) == "00:45"

    def test_over_a_minute(self, tc_module):
        assert tc_module._format_mmss(125) == "02:05"

    def test_negative_clamped_to_zero(self, tc_module):
        assert tc_module._format_mmss(-5) == "00:00"


class TestSaveResult:
    def test_without_timestamps_writes_plain_text(self, tc_module, tmp_path):
        from core.transcription_interface import TranscriptionSegment

        text = "これはテストです。"
        segments = [TranscriptionSegment(start=0.0, end=10.0, text=text, language="ja")]
        result = _make_result(tc_module, segments, text, timestamps_included=False)

        output_path = tc_module.save_result(result, output_dir=str(tmp_path))
        content = Path(output_path).read_text(encoding="utf-8")

        assert content == text
        assert "[00:00]" not in content

    def test_with_timestamps_prefixes_each_segment(self, tc_module, tmp_path):
        from core.transcription_interface import TranscriptionSegment

        segments = [
            TranscriptionSegment(start=0.0, end=1.3, text="これは、", language="ja"),
            TranscriptionSegment(start=65.0, end=68.0, text="テストです。", language="ja"),
        ]
        result = _make_result(tc_module, segments, "これは、\nテストです。", timestamps_included=True)

        output_path = tc_module.save_result(result, output_dir=str(tmp_path))
        content = Path(output_path).read_text(encoding="utf-8")

        lines = content.split("\n")
        assert lines[0] == "[00:00] これは、"
        assert lines[1] == "[01:05] テストです。"
