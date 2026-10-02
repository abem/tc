"""
Tests for tc(CLIスクリプト、拡張子無し)の load_config / build_parser /
transcribe_audio / main の本処理(tc-ops #567 Task 2.6)。

目的: 後続のリファクタリング(TranscriptionConfig の未使用フィールド削除、
CLI と WebUI の後処理共通化)の前に、tc の現在の挙動を固定する特性化テスト。
期待値は「あるべき姿」ではなく「現在の実装の挙動」である。

- 実モデルのロード・GPU・実ネットワーク・実 Drive API は使わない
  (UnifiedTranscriber / アップロード / 履歴記録 / 入力解決は差し替える)。
- 出力先・履歴DB・設定ファイルは tmp_path に閉じる(実 output/ や config/config.yaml
  には依存しない)。
- _format_mmss / save_result は tests/test_tc_save_result.py、--dry-run のローカル
  wav 起動は tests/test_e2e_dry_run.py が担当するため、ここでは重複させない。
"""

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
import yaml

from core.cli_workflow import InputResolution
from core.config import TranscriptionConfig
from core.transcription_interface import TranscriptionResult, TranscriptionSegment

TC_PATH = Path(__file__).resolve().parents[1] / "tc"

# transcribe_audio が TranscriptionConfig(...) にキーワード引数で渡している全キー。
# いずれもエンジンが実際に読む項目。どのエンジンも読まない項目は TranscriptionConfig から
# 削除済み(tc-ops #567 Task 3.3)で、渡すキーを増やすとここで検出される。
PASSED_CONFIG_KEYS = {
    "model",
    "language",
    "device",
    "context",
    "include_timestamps",
}


def _load_tc_module():
    # test_tc_save_result.py と同じ方法: 拡張子無しのため SourceFileLoader を明示する。
    loader = SourceFileLoader("tc_cli_main_flow_under_test", str(TC_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tc_module():
    return _load_tc_module()


def _make_result(text="こんにちは", metadata=None, segments=None):
    return TranscriptionResult(
        text=text,
        segments=segments if segments is not None else [TranscriptionSegment(start=0.0, end=1.0, text=text)],
        language="ja",
        duration=10.0,
        processing_time=1.0,
        model_name="fake-model",
        has_speakers=False,
        metadata=metadata,
    )


class FakeTranscriber:
    """UnifiedTranscriber の代替。実モデルをロードしない。"""

    instances = []
    result = None
    error = None

    def __init__(self, config):
        self.config = config
        self.calls = []
        FakeTranscriber.instances.append(self)

    def transcribe(self, audio_path, progress_callback=None):
        self.calls.append(audio_path)
        if progress_callback is not None:
            progress_callback("fake-progress-message")
        if FakeTranscriber.error is not None:
            raise FakeTranscriber.error
        return FakeTranscriber.result


@pytest.fixture
def fake_transcriber(tc_module, monkeypatch):
    FakeTranscriber.instances = []
    FakeTranscriber.result = _make_result()
    FakeTranscriber.error = None
    monkeypatch.setattr(tc_module, "UnifiedTranscriber", FakeTranscriber)
    return FakeTranscriber


@pytest.fixture
def config_capture(tc_module, monkeypatch):
    """TranscriptionConfig へ渡された引数(位置引数・キーワード引数)を記録する。"""
    captured = {"args": None, "kwargs": None}

    def recording(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = dict(kwargs)
        return TranscriptionConfig(*args, **kwargs)

    monkeypatch.setattr(tc_module, "TranscriptionConfig", recording)
    return captured


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    @pytest.fixture
    def project_root(self, tc_module, tmp_path, monkeypatch):
        monkeypatch.setattr(tc_module, "PROJECT_ROOT", tmp_path)
        (tmp_path / "config").mkdir()
        return tmp_path

    def test_reads_all_keys_from_yaml(self, tc_module, project_root):
        data = {
            "gdrive": {"url": "https://drive.google.com/file/d/abc/view", "upload_folder_id": "folder1"},
            "whisper": {"model": "m", "language": None, "device": "cpu", "include_timestamps": True},
            "extra": [1, 2],
        }
        (project_root / "config" / "config.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
        )

        assert tc_module.load_config() == data

    def test_reads_utf8_japanese_values(self, tc_module, project_root):
        (project_root / "config" / "config.yaml").write_text(
            "whisper:\n  context_file: 'config/固有名詞.txt'\n", encoding="utf-8"
        )

        assert tc_module.load_config()["whisper"]["context_file"] == "config/固有名詞.txt"

    def test_yaml_null_value_is_returned_as_none_not_dropped(self, tc_module, project_root):
        (project_root / "config" / "config.yaml").write_text("whisper:\n  language: null\n", encoding="utf-8")

        config = tc_module.load_config()

        assert "language" in config["whisper"]
        assert config["whisper"]["language"] is None

    def test_missing_file_exits_with_code_1(self, tc_module, project_root):
        with pytest.raises(SystemExit) as exc_info:
            tc_module.load_config()

        assert exc_info.value.code == 1

    def test_missing_config_directory_exits_with_code_1(self, tc_module, tmp_path, monkeypatch):
        monkeypatch.setattr(tc_module, "PROJECT_ROOT", tmp_path / "no_such_root")

        with pytest.raises(SystemExit) as exc_info:
            tc_module.load_config()

        assert exc_info.value.code == 1

    def test_empty_file_returns_none(self, tc_module, project_root):
        # 現状の挙動: yaml.safe_load("") が None を返し、そのまま返却される(辞書への補正なし)。
        (project_root / "config" / "config.yaml").write_text("", encoding="utf-8")

        assert tc_module.load_config() is None

    def test_comment_only_file_returns_none(self, tc_module, project_root):
        (project_root / "config" / "config.yaml").write_text("# only a comment\n", encoding="utf-8")

        assert tc_module.load_config() is None

    def test_invalid_yaml_propagates_yaml_error(self, tc_module, project_root):
        # 現状の挙動: 不正なYAMLは捕捉されず yaml.YAMLError が呼び出し元へ伝播する。
        (project_root / "config" / "config.yaml").write_text("whisper: [unclosed\n  - x: {\n", encoding="utf-8")

        with pytest.raises(yaml.YAMLError):
            tc_module.load_config()


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defines_exactly_the_expected_options(self, tc_module):
        parser = tc_module.build_parser()

        dests = {action.dest for action in parser._actions if action.dest != "help"}
        assert dests == {
            "input",
            "output_dir",
            "no_upload",
            "model",
            "language",
            "device",
            "folder_id",
            "dry_run",
        }

    def test_defaults_when_no_arguments(self, tc_module):
        args = tc_module.build_parser().parse_args([])

        assert args.input is None
        assert args.output_dir == "output"
        assert args.no_upload is False
        assert args.model is None
        assert args.language is None
        assert args.device is None
        assert args.folder_id is None
        assert args.dry_run is False

    def test_specified_values(self, tc_module):
        args = tc_module.build_parser().parse_args(
            [
                "https://youtu.be/xxxx",
                "--output-dir",
                "out_dir",
                "--no-upload",
                "--model",
                "openai/whisper-large-v3",
                "--language",
                "en",
                "--device",
                "cpu",
                "--folder-id",
                "FOLDER123",
                "--dry-run",
            ]
        )

        assert args.input == "https://youtu.be/xxxx"
        assert args.output_dir == "out_dir"
        assert args.no_upload is True
        assert args.model == "openai/whisper-large-v3"
        assert args.language == "en"
        assert args.device == "cpu"
        assert args.folder_id == "FOLDER123"
        assert args.dry_run is True

    @pytest.mark.parametrize("device", ["cuda", "cpu", "auto"])
    def test_device_accepts_choices(self, tc_module, device):
        assert tc_module.build_parser().parse_args(["--device", device]).device == device

    def test_device_rejects_unknown_value(self, tc_module, capsys):
        with pytest.raises(SystemExit) as exc_info:
            tc_module.build_parser().parse_args(["--device", "tpu"])

        assert exc_info.value.code == 2
        assert "invalid choice" in capsys.readouterr().err

    def test_there_is_no_timestamp_option_on_the_command_line(self, tc_module, capsys):
        # タイムスタンプ付与は config.yaml の whisper.include_timestamps のみで制御される。
        with pytest.raises(SystemExit) as exc_info:
            tc_module.build_parser().parse_args(["--timestamps"])

        assert exc_info.value.code == 2

    def test_input_is_optional_positional(self, tc_module):
        assert tc_module.build_parser().parse_args(["audio.wav"]).input == "audio.wav"


# ---------------------------------------------------------------------------
# transcribe_audio
# ---------------------------------------------------------------------------


class TestTranscribeAudioConfigPassing:
    @pytest.fixture(autouse=True)
    def _isolate_cwd(self, tmp_path, monkeypatch):
        # context_file の既定値 "config/context_hints.txt" は cwd 相対。実リポジトリの
        # config/ を読まないよう cwd を tmp_path にする(monkeypatch が元に戻す)。
        monkeypatch.chdir(tmp_path)

    def test_keys_passed_to_transcription_config_are_exactly_the_known_set(
        self, tc_module, fake_transcriber, config_capture
    ):
        tc_module.transcribe_audio("a.wav", {"whisper": {}})

        assert config_capture["args"] == ()
        assert set(config_capture["kwargs"]) == PASSED_CONFIG_KEYS

    def test_defaults_when_config_has_no_whisper_section(self, tc_module, fake_transcriber, config_capture):
        tc_module.transcribe_audio("a.wav", {})

        assert config_capture["kwargs"] == {
            "model": "kotoba-tech/kotoba-whisper-v2.2",
            "language": "ja",
            "device": "cuda",
            "context": "",
            "include_timestamps": False,
        }

    def test_values_come_from_whisper_section(self, tc_module, fake_transcriber, config_capture, tmp_path):
        hints = tmp_path / "hints.txt"
        hints.write_text("# comment\nFoo\n\nBar\n", encoding="utf-8")
        config = {
            "whisper": {
                "model": "Qwen/Qwen3-ASR-1.7B",
                "language": "en",
                "device": "cpu",
                "context_file": str(hints),
                "include_timestamps": True,
            }
        }

        tc_module.transcribe_audio("a.wav", config)

        assert config_capture["kwargs"] == {
            "model": "Qwen/Qwen3-ASR-1.7B",
            "language": "en",
            "device": "cpu",
            "context": "Foo, Bar",
            "include_timestamps": True,
        }

    def test_explicit_null_language_is_passed_as_none_not_default_ja(
        self, tc_module, fake_transcriber, config_capture
    ):
        # config.yaml の language: null(自動判定)は dict.get の既定値 "ja" に置き換わらず None になる。
        tc_module.transcribe_audio("a.wav", {"whisper": {"language": None}})

        assert config_capture["kwargs"]["language"] is None

    def test_keys_outside_the_passed_set_are_not_forwarded(self, tc_module, fake_transcriber, config_capture):
        # config.yaml の whisper.chunk_size 等は TranscriptionConfig へ渡らない。
        # これらのフィールドは TranscriptionConfig 自体から削除済みで、存在しないことも確認する。
        removed_fields = ("chunk_size", "compute_type", "beam_size", "best_of", "temperature")
        tc_module.transcribe_audio(
            "a.wav",
            {"whisper": {"chunk_size": 100, "compute_type": "int8", "beam_size": 9, "best_of": 4, "temperature": 0.3}},
        )

        assert set(config_capture["kwargs"]) == PASSED_CONFIG_KEYS
        passed_config = fake_transcriber.instances[0].config
        for name in removed_fields:
            assert not hasattr(passed_config, name)
            assert name not in TranscriptionConfig.__dataclass_fields__
            with pytest.raises(TypeError):
                TranscriptionConfig(**{name: 1})

    def test_auto_device_is_resolved_before_building_config(
        self, tc_module, fake_transcriber, config_capture, monkeypatch
    ):
        seen = []

        def fake_resolve(device):
            seen.append(device)
            return "cpu"

        monkeypatch.setattr(tc_module, "resolve_device", fake_resolve)

        tc_module.transcribe_audio("a.wav", {"whisper": {"device": "auto"}})

        assert seen == ["auto"]
        assert config_capture["kwargs"]["device"] == "cpu"

    def test_default_device_requested_from_resolver_is_cuda(
        self, tc_module, fake_transcriber, config_capture, monkeypatch
    ):
        seen = []
        monkeypatch.setattr(tc_module, "resolve_device", lambda d: seen.append(d) or d)

        tc_module.transcribe_audio("a.wav", {})

        assert seen == ["cuda"]

    def test_default_context_file_is_read_relative_to_cwd(
        self, tc_module, fake_transcriber, config_capture, tmp_path
    ):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "context_hints.txt").write_text("Alpha\nBeta\n", encoding="utf-8")

        tc_module.transcribe_audio("a.wav", {"whisper": {}})

        assert config_capture["kwargs"]["context"] == "Alpha, Beta"

    def test_missing_context_file_gives_empty_context(self, tc_module, fake_transcriber, config_capture, tmp_path):
        tc_module.transcribe_audio("a.wav", {"whisper": {"context_file": str(tmp_path / "nope.txt")}})

        assert config_capture["kwargs"]["context"] == ""


class TestTranscribeAudioResultHandling:
    @pytest.fixture(autouse=True)
    def _isolate_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_returns_transcriber_result_and_passes_audio_path(self, tc_module, fake_transcriber):
        expected = _make_result(text="結果テキスト")
        fake_transcriber.result = expected

        result = tc_module.transcribe_audio("/some/audio.wav", {})

        assert result is expected
        assert fake_transcriber.instances[0].calls == ["/some/audio.wav"]

    def test_transcriber_receives_built_config_instance(self, tc_module, fake_transcriber):
        tc_module.transcribe_audio("a.wav", {"whisper": {"model": "m1", "device": "cpu"}})

        passed = fake_transcriber.instances[0].config
        assert isinstance(passed, TranscriptionConfig)
        assert passed.model == "m1"
        assert passed.device == "cpu"

    def test_progress_messages_are_printed(self, tc_module, fake_transcriber, capsys):
        tc_module.transcribe_audio("a.wav", {})

        assert "fake-progress-message" in capsys.readouterr().out

    def test_no_warning_when_metadata_is_none(self, tc_module, fake_transcriber, capsys):
        fake_transcriber.result = _make_result(metadata=None)

        tc_module.transcribe_audio("a.wav", {})

        assert "警告" not in capsys.readouterr().out

    def test_no_warning_when_counts_are_zero(self, tc_module, fake_transcriber, capsys):
        fake_transcriber.result = _make_result(metadata={"failed_chunks": 0, "repeated_chunks": 0})

        tc_module.transcribe_audio("a.wav", {})

        assert "警告" not in capsys.readouterr().out

    def test_failed_chunks_warning(self, tc_module, fake_transcriber, capsys):
        fake_transcriber.result = _make_result(metadata={"failed_chunks": 2})

        tc_module.transcribe_audio("a.wav", {})

        out = capsys.readouterr().out
        assert "警告: 2個のチャンクが失敗し" in out
        assert "反復ループ" not in out

    def test_repeated_chunks_warning(self, tc_module, fake_transcriber, capsys):
        fake_transcriber.result = _make_result(metadata={"repeated_chunks": 3})

        tc_module.transcribe_audio("a.wav", {})

        out = capsys.readouterr().out
        assert "警告: 3個のチャンクで反復ループを検出しました" in out
        assert "チャンクが失敗し" not in out

    def test_both_warnings_are_printed_failed_first(self, tc_module, fake_transcriber, capsys):
        fake_transcriber.result = _make_result(metadata={"failed_chunks": 1, "repeated_chunks": 1})

        tc_module.transcribe_audio("a.wav", {})

        out = capsys.readouterr().out
        assert out.index("チャンクが失敗し") < out.index("反復ループを検出")

    def test_transcriber_exception_propagates(self, tc_module, fake_transcriber):
        fake_transcriber.error = RuntimeError("CUDA error")

        with pytest.raises(RuntimeError, match="CUDA error"):
            tc_module.transcribe_audio("a.wav", {})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class MainEnv:
    """main() を差し替えだけで動かすためのテスト環境。"""

    def __init__(self, tc_module, tmp_path, monkeypatch, fake_transcriber):
        self.tc = tc_module
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.transcriber = fake_transcriber
        self.output_dir = tmp_path / "output"
        self.audio = tmp_path / "input_audio.wav"
        self.audio.write_bytes(b"RIFF-fake")
        self.config = {"whisper": {"model": "cfg-model", "language": "ja", "device": "cpu"}}
        self.resolution = InputResolution(
            source_type="local",
            original_source=str(self.audio),
            local_audio_path=str(self.audio),
            is_temp_file=False,
            metadata=None,
            youtube_handler=None,
        )
        self.resolve_calls = []
        self.resolve_error = None
        self.upload_calls = []
        self.upload_return = "https://drive.example/uploaded"
        self.history_calls = []
        self.history_error = None
        self.events = []

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(tc_module, "load_config", lambda: self.config)
        monkeypatch.setattr(tc_module, "resolve_input_audio", self._resolve)
        monkeypatch.setattr(tc_module, "upload_transcription_result", self._upload)
        monkeypatch.setattr(tc_module, "record_transcription_history", self._history)

    def _resolve(self, source, output_dir, **kwargs):
        self.resolve_calls.append((source, output_dir, kwargs))
        self.events.append("resolve")
        if self.resolve_error is not None:
            raise self.resolve_error
        return self.resolution

    def _upload(self, **kwargs):
        self.upload_calls.append(kwargs)
        self.events.append("upload")
        return self.upload_return

    def _history(self, **kwargs):
        self.history_calls.append(kwargs)
        self.events.append("history")
        if self.history_error is not None:
            raise self.history_error

    def use_real_local_resolution(self):
        """ネットワーク不要な実の resolve_input_audio(ローカルファイル経路)に戻す。"""
        from core.cli_workflow import resolve_input_audio

        def real(source, output_dir, **kwargs):
            self.resolve_calls.append((source, output_dir, kwargs))
            self.events.append("resolve")
            return resolve_input_audio(source, output_dir, **kwargs)

        self.monkeypatch.setattr(self.tc, "resolve_input_audio", real)

    def make_temp_resolution(self, source_type, handler=None, is_temp_file=True, metadata=None):
        temp = self.tmp_path / f"temp_{source_type}.m4a"
        temp.write_bytes(b"temp-audio")
        self.resolution = InputResolution(
            source_type=source_type,
            original_source=(
                "https://drive.google.com/file/d/FILEID123/view"
                if source_type == "gdrive"
                else "https://youtu.be/abc"
            ),
            local_audio_path=str(temp),
            is_temp_file=is_temp_file,
            metadata=metadata,
            youtube_handler=handler,
        )
        return temp

    def run(self, *argv):
        self.monkeypatch.setattr("sys.argv", ["tc", *argv])
        self.tc.main()

    def output_files(self):
        if not self.output_dir.exists():
            return []
        return sorted(self.output_dir.glob("*_transcription.txt"))


@pytest.fixture
def env(tc_module, tmp_path, monkeypatch, fake_transcriber):
    return MainEnv(tc_module, tmp_path, monkeypatch, fake_transcriber)


class FakeYouTubeHandler:
    def __init__(self):
        self.cleaned = []

    def cleanup_temp_file(self, path):
        self.cleaned.append(path)


class TestMainLocalFileFlow:
    def test_full_flow_order_and_outputs(self, env, capsys):
        env.transcriber.result = _make_result(text="ローカル文字起こし")

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        files = env.output_files()
        assert len(files) == 1
        assert files[0].read_text(encoding="utf-8") == "ローカル文字起こし"
        assert env.events == ["resolve", "history"]
        out = capsys.readouterr().out
        assert f"文字起こし完了: {files[0]}" in out
        assert "文字起こし結果（最初の500文字）:" in out
        assert "ローカル文字起こし" in out

    def test_resolve_is_called_with_input_output_dir_and_yt_dlp_flag(self, env):
        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        source, output_dir, kwargs = env.resolve_calls[0]
        assert source == str(env.audio)
        assert output_dir == env.output_dir
        assert kwargs["ensure_yt_dlp"] is True
        assert callable(kwargs["on_status"])

    def test_transcriber_receives_resolved_audio_path(self, env):
        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        assert env.transcriber.instances[0].calls == [str(env.audio)]

    def test_local_input_file_is_not_deleted_and_not_uploaded(self, env):
        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        assert env.audio.exists()
        assert env.upload_calls == []

    def test_real_local_resolution_keeps_input_file(self, env):
        env.use_real_local_resolution()

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        assert env.audio.exists()
        assert len(env.output_files()) == 1
        assert env.history_calls[0]["resolution"].source_type == "local"

    def test_history_is_recorded_with_expected_arguments(self, env):
        env.config["whisper"]["include_timestamps"] = True
        env.config["whisper"]["context_file"] = str(env.tmp_path / "hints.txt")
        (env.tmp_path / "hints.txt").write_text("Foo\nBar\n", encoding="utf-8")
        expected_result = _make_result(text="履歴対象")
        env.transcriber.result = expected_result

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        call = env.history_calls[0]
        assert set(call) == {"result", "resolution", "output_file", "settings", "gdrive_url"}
        assert call["result"] is expected_result
        assert call["resolution"] is env.resolution
        assert call["output_file"] == env.output_files()[0]
        assert call["gdrive_url"] is None
        assert call["settings"] == {
            "device": "cpu",
            "context": "Foo, Bar",
            "diarization": False,
            "include_timestamps": True,
        }

    def test_history_failure_is_reported_but_does_not_fail_the_run(self, env, capsys):
        env.history_error = RuntimeError("db locked")

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        out = capsys.readouterr().out
        assert "変換履歴の記録に失敗しました: db locked" in out
        # 履歴失敗後も結果プレビューまで進む
        assert "文字起こし結果（最初の500文字）:" in out
        assert len(env.output_files()) == 1

    def test_preview_is_not_truncated_at_exactly_500_chars(self, env, capsys):
        env.transcriber.result = _make_result(text="あ" * 500)

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        out = capsys.readouterr().out
        assert "あ" * 500 in out
        assert "全500文字" not in out

    def test_preview_is_truncated_to_500_chars_with_total_count(self, env, capsys):
        env.transcriber.result = _make_result(text="い" * 501)

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        out = capsys.readouterr().out
        assert "い" * 500 in out
        assert "い" * 501 not in out
        assert "... (全501文字)" in out
        # 保存ファイルは切り詰められない
        assert env.output_files()[0].read_text(encoding="utf-8") == "い" * 501

    def test_default_output_dir_is_relative_output_under_cwd(self, env):
        env.run(str(env.audio))

        assert len(list((env.tmp_path / "output").glob("*_transcription.txt"))) == 1


class TestMainCliOverridesConfig:
    def test_cli_model_language_device_override_config_values(self, env, config_capture):
        env.config["whisper"].update({"model": "cfg-model", "language": "ja", "device": "cpu"})

        env.run(
            str(env.audio),
            "--output-dir",
            str(env.output_dir),
            "--model",
            "cli-model",
            "--language",
            "en",
            "--device",
            "cuda",
        )

        kwargs = config_capture["kwargs"]
        assert kwargs["model"] == "cli-model"
        assert kwargs["language"] == "en"
        assert kwargs["device"] == "cuda"

    def test_config_values_are_used_when_cli_options_are_omitted(self, env, config_capture):
        env.config["whisper"].update(
            {"model": "cfg-model", "language": "fr", "device": "cpu"}
        )

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        kwargs = config_capture["kwargs"]
        assert kwargs["model"] == "cfg-model"
        assert kwargs["language"] == "fr"
        assert kwargs["device"] == "cpu"

    def test_partial_cli_override_only_replaces_given_keys(self, env, config_capture):
        env.config["whisper"].update({"model": "cfg-model", "language": "ja", "device": "cpu"})

        env.run(str(env.audio), "--output-dir", str(env.output_dir), "--language", "en")

        kwargs = config_capture["kwargs"]
        assert kwargs["model"] == "cfg-model"
        assert kwargs["language"] == "en"
        assert kwargs["device"] == "cpu"

    def test_cli_override_does_not_mutate_loaded_config_dict(self, env):
        env.run(str(env.audio), "--output-dir", str(env.output_dir), "--model", "cli-model")

        assert env.config["whisper"]["model"] == "cfg-model"

    def test_cli_device_is_used_for_history_settings(self, env):
        env.run(str(env.audio), "--output-dir", str(env.output_dir), "--device", "cuda")

        assert env.history_calls[0]["settings"]["device"] == "cuda"


class TestMainInputResolutionFailures:
    def test_unresolvable_input_exits_1_without_transcribing(self, env, capsys):
        env.resolve_error = ValueError("入力を認識できません: nope")

        with pytest.raises(SystemExit) as exc_info:
            env.run("nope", "--output-dir", str(env.output_dir))

        assert exc_info.value.code == 1
        assert env.transcriber.instances == []
        assert env.output_files() == []
        assert env.history_calls == []
        assert env.upload_calls == []

    def test_real_resolver_rejects_nonexistent_path_with_exit_1(self, env):
        env.use_real_local_resolution()

        with pytest.raises(SystemExit) as exc_info:
            env.run(str(env.tmp_path / "does_not_exist.wav"), "--output-dir", str(env.output_dir))

        assert exc_info.value.code == 1
        assert env.transcriber.instances == []

    def test_non_value_error_from_resolver_propagates(self, env):
        # ValueError 以外(ダウンロード失敗など)は捕捉されず、そのまま呼び出し元へ伝播する。
        env.resolve_error = RuntimeError("download failed")

        with pytest.raises(RuntimeError, match="download failed"):
            env.run("https://youtu.be/abc", "--output-dir", str(env.output_dir))

        assert env.transcriber.instances == []

    def test_no_input_and_no_config_url_exits_1_before_resolving(self, env, capsys):
        env.config.pop("gdrive", None)

        with pytest.raises(SystemExit) as exc_info:
            env.run("--output-dir", str(env.output_dir))

        assert exc_info.value.code == 1
        assert env.resolve_calls == []
        assert "config.yamlにGDriveのURLが設定されていません" in capsys.readouterr().out

    def test_no_input_with_null_config_url_exits_1(self, env):
        env.config["gdrive"] = {"url": None}

        with pytest.raises(SystemExit) as exc_info:
            env.run("--output-dir", str(env.output_dir))

        assert exc_info.value.code == 1
        assert env.resolve_calls == []

    def test_no_input_falls_back_to_config_gdrive_url(self, env):
        url = "https://drive.google.com/file/d/CFG123/view"
        env.config["gdrive"] = {"url": url}

        env.run("--output-dir", str(env.output_dir))

        assert env.resolve_calls[0][0] == url

    def test_cli_input_takes_precedence_over_config_gdrive_url(self, env):
        env.config["gdrive"] = {"url": "https://drive.google.com/file/d/CFG123/view"}

        env.run(str(env.audio), "--output-dir", str(env.output_dir))

        assert env.resolve_calls[0][0] == str(env.audio)


class TestMainTranscriptionFailure:
    def test_transcription_exception_propagates_without_exit_code_handling(self, env):
        # 現状の挙動: main は文字起こしの例外を捕捉・sys.exit 変換しない
        # (try/finally のみ)。例外はそのまま伝播し、スクリプト実行時は
        # Python 既定のトレースバック終了(終了コード 1)になる。
        env.transcriber.error = RuntimeError("CUDA out of memory")

        with pytest.raises(RuntimeError, match="CUDA out of memory"):
            env.run(str(env.audio), "--output-dir", str(env.output_dir))

        assert env.output_files() == []
        assert env.history_calls == []
        assert env.upload_calls == []

    def test_local_input_file_survives_transcription_failure(self, env):
        env.transcriber.error = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            env.run(str(env.audio), "--output-dir", str(env.output_dir))

        assert env.audio.exists()

    def test_gdrive_temp_file_is_removed_even_when_transcription_fails(self, env):
        temp = env.make_temp_resolution("gdrive", is_temp_file=False)
        env.transcriber.error = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            env.run("https://drive.google.com/file/d/FILEID123/view", "--output-dir", str(env.output_dir))

        assert not temp.exists()

    def test_youtube_temp_file_is_cleaned_via_handler_when_transcription_fails(self, env):
        handler = FakeYouTubeHandler()
        temp = env.make_temp_resolution("youtube", handler=handler, metadata={"title": "t"})
        env.transcriber.error = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            env.run("https://youtu.be/abc", "--output-dir", str(env.output_dir))

        assert handler.cleaned == [str(temp)]
        # 後始末はハンドラ経由のみ(os.remove は呼ばない)。偽ハンドラは削除しないので残る。
        assert temp.exists()

    def test_upload_exception_propagates_and_temp_file_is_still_removed(self, env):
        temp = env.make_temp_resolution("gdrive", is_temp_file=False)

        def failing_upload(**kwargs):
            raise OSError("drive down")

        env.monkeypatch.setattr(env.tc, "upload_transcription_result", failing_upload)

        with pytest.raises(OSError, match="drive down"):
            env.run("https://drive.google.com/file/d/FILEID123/view", "--output-dir", str(env.output_dir))

        assert not temp.exists()
        # 結果ファイルは保存済みだが、履歴は記録されない
        assert len(env.output_files()) == 1
        assert env.history_calls == []


class TestMainTempFileCleanupAndUpload:
    def test_gdrive_temp_file_is_deleted_after_success(self, env):
        temp = env.make_temp_resolution("gdrive", is_temp_file=False)

        env.run("https://drive.google.com/file/d/FILEID123/view", "--output-dir", str(env.output_dir))

        assert not temp.exists()

    def test_gdrive_flow_order_resolve_upload_history(self, env, capsys):
        env.make_temp_resolution("gdrive", is_temp_file=False)

        env.run("https://drive.google.com/file/d/FILEID123/view", "--output-dir", str(env.output_dir))

        assert env.events == ["resolve", "upload", "history"]
        out = capsys.readouterr().out
        assert "アップロード完了: https://drive.example/uploaded" in out
        assert env.history_calls[0]["gdrive_url"] == "https://drive.example/uploaded"

    def test_gdrive_upload_arguments(self, env):
        env.make_temp_resolution("gdrive", is_temp_file=False)
        original = env.resolution.original_source

        env.run(original, "--output-dir", str(env.output_dir))

        call = env.upload_calls[0]
        assert call == {
            "source_type": "gdrive",
            "original_source": original,
            "output_file": env.output_files()[0],
            "metadata": None,
            "folder_id": None,
        }

    def test_folder_id_cli_beats_config_beats_none(self, env):
        env.make_temp_resolution("gdrive", is_temp_file=False)
        env.config["gdrive"] = {"upload_folder_id": "CFG_FOLDER"}

        env.run(env.resolution.original_source, "--output-dir", str(env.output_dir), "--folder-id", "CLI_FOLDER")
        assert env.upload_calls[-1]["folder_id"] == "CLI_FOLDER"

        env.make_temp_resolution("gdrive", is_temp_file=False)
        env.run(env.resolution.original_source, "--output-dir", str(env.output_dir))
        assert env.upload_calls[-1]["folder_id"] == "CFG_FOLDER"

        env.make_temp_resolution("gdrive", is_temp_file=False)
        env.config["gdrive"] = {}
        env.run(env.resolution.original_source, "--output-dir", str(env.output_dir))
        assert env.upload_calls[-1]["folder_id"] is None

    def test_no_upload_skips_upload_but_still_cleans_up_and_records_history(self, env):
        temp = env.make_temp_resolution("gdrive", is_temp_file=False)

        env.run(env.resolution.original_source, "--output-dir", str(env.output_dir), "--no-upload")

        assert env.upload_calls == []
        assert not temp.exists()
        assert env.history_calls[0]["gdrive_url"] is None

    def test_failed_upload_prints_failure_and_history_gets_no_url(self, env, capsys):
        env.make_temp_resolution("gdrive", is_temp_file=False)
        env.upload_return = None

        env.run(env.resolution.original_source, "--output-dir", str(env.output_dir))

        out = capsys.readouterr().out
        assert "アップロードに失敗しました" in out
        assert "アップロード完了" not in out
        assert env.history_calls[0]["gdrive_url"] is None

    def test_youtube_uploads_with_metadata_and_cleans_via_handler(self, env):
        handler = FakeYouTubeHandler()
        metadata = {"title": "動画タイトル", "video_id": "abc"}
        temp = env.make_temp_resolution("youtube", handler=handler, metadata=metadata)

        env.run("https://youtu.be/abc", "--output-dir", str(env.output_dir))

        call = env.upload_calls[0]
        assert call["source_type"] == "youtube"
        assert call["metadata"] == metadata
        assert handler.cleaned == [str(temp)]

    def test_youtube_temp_file_without_handler_is_removed_directly(self, env):
        temp = env.make_temp_resolution("youtube", handler=None)

        env.run("https://youtu.be/abc", "--output-dir", str(env.output_dir))

        assert not temp.exists()

    def test_twitter_source_is_cleaned_up_but_never_uploaded(self, env):
        handler = FakeYouTubeHandler()
        temp = env.make_temp_resolution("twitter", handler=handler)

        env.run("https://x.com/user/status/123", "--output-dir", str(env.output_dir))

        assert env.upload_calls == []
        assert handler.cleaned == [str(temp)]

    def test_already_missing_temp_file_is_not_an_error(self, env):
        temp = env.make_temp_resolution("gdrive", is_temp_file=False)
        temp.unlink()

        env.run(env.resolution.original_source, "--output-dir", str(env.output_dir))

        assert not temp.exists()

    def test_is_temp_file_flag_alone_triggers_cleanup_for_non_gdrive(self, env):
        temp = env.make_temp_resolution("local", is_temp_file=True)

        env.run(str(temp), "--output-dir", str(env.output_dir))

        assert not temp.exists()


class TestMainDryRunCleanup:
    def test_dry_run_does_not_transcribe_but_removes_gdrive_temp_file(self, env, capsys):
        temp = env.make_temp_resolution("gdrive", is_temp_file=False)

        env.run(env.resolution.original_source, "--output-dir", str(env.output_dir), "--dry-run")

        assert env.transcriber.instances == []
        assert env.output_files() == []
        assert env.history_calls == []
        assert env.upload_calls == []
        assert not temp.exists()
        assert f"ドライラン: 起動確認OK (input={temp})" in capsys.readouterr().out

    def test_dry_run_cleans_youtube_temp_via_handler(self, env):
        handler = FakeYouTubeHandler()
        temp = env.make_temp_resolution("youtube", handler=handler)

        env.run("https://youtu.be/abc", "--output-dir", str(env.output_dir), "--dry-run")

        assert handler.cleaned == [str(temp)]
        assert env.transcriber.instances == []
