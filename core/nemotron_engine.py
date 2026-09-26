"""Nemotron-3.5-ASR-Streaming サブプロセス実行エンジン。

生産用 `.venv` には Nemotron が要求する `transformers>=5.13.0` をインストールできない
(qwen-asr が `transformers<5` を要求するため、生産用`.venv`の`transformers==4.57.6`と
両立しない。tc-ops #546 予備調査で確認済み)。そのため Nemotron は隔離venv
(`venv-nemotron/`、`scripts/setup_nemotron_venv.sh` で構築)上のPythonを
サブプロセスとして起動し、標準出力のJSON経由で結果を受け取る方式を採る
(tc-ops #546 Phase2設計report §1)。

`transcribe()` の中身は既存2エンジン(`Qwen3ASREngine`/`WhisperTranscriptionEngine`)と
同じ `TranscriptionEngine` 抽象基底の契約を満たすため、`UnifiedTranscriber` からは
既存エンジンと区別なく呼び出せる。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from core.transcription_interface import (
    TranscriptionEngine,
    TranscriptionResult,
    TranscriptionSegment,
)

# リポジトリルート(このファイルの1階層上)。venv-nemotron/・scripts/はここを基準に置く。
_REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = _REPO_ROOT / "venv-nemotron" / "bin" / "python"
INFER_SCRIPT = _REPO_ROOT / "scripts" / "nemotron_infer.py"

# タイムアウト算出式(Phase2設計report §1): 実測RTF最大0.0401(Phase1)に十分な
# 安全マージンを持たせ、固定オーバーヘッド(モデルロード時間の吸収)を加える。
_TIMEOUT_MULTIPLIER = 3.0
_TIMEOUT_FIXED_OVERHEAD_SEC = 30.0
_TIMEOUT_MIN_SEC = 60.0


def is_nemotron_model(model_name: str) -> bool:
    """モデル名が Nemotron 系かどうかを判定する。

    `Qwen3ASREngine.is_qwen3_model` の判定文字列(`qwen3-asr`/`qwen3_asr`)とは
    互いに排他的な文字列であるため、`UnifiedTranscriber.__init__` での判定順序を
    どちらを先にしても既存モデル名の解決結果には影響しない
    (tc-ops #546 Phase2設計report §2)。
    """
    return "nemotron" in (model_name or "").lower()


class NemotronSubprocessEngine(TranscriptionEngine):
    """Nemotron-3.5-ASR-Streaming を隔離venvのサブプロセス経由で実行するエンジン。"""

    def get_engine_name(self) -> str:
        return f"nemotron-{self.config.model}"

    @staticmethod
    def _get_audio_duration_fallback() -> float:
        """音声長取得失敗時のフォールバック(既存エンジンと同一パターン)。"""
        return 600.0  # デフォルト10分

    def _get_audio_duration(self, audio_path: str) -> float:
        """音声ファイルの長さを取得(既存エンジンと同一パターン、soundfile優先)。"""
        import soundfile as sf
        try:
            info = sf.info(audio_path)
            return info.duration
        except Exception:
            return self._get_audio_duration_fallback()

    def _resolve_language(self) -> str:
        """TranscriptionConfig.language を Nemotron の言語コード(例: ja-JP)へ変換する。

        未知の値/Noneは"auto"(Nemotronのモデルカードに定義された自動言語検出)へ解決する。
        """
        mapping = {"ja": "ja-JP", "en": "en-US"}
        return mapping.get((self.config.language or "").lower(), "auto")

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Nemotron-3.5-ASR-Streaming で文字起こし(隔離venvサブプロセス経由)。"""
        self.validate_audio_file(audio_path)

        if not VENV_PYTHON.exists():
            raise RuntimeError(
                "Nemotron隔離venvが未構築です。"
                "scripts/setup_nemotron_venv.sh を実行してから再度お試しください。"
            )

        start_time = time.time()
        op_name = f"transcribe_{Path(audio_path).name}"
        self.perf_logger.start_timing(op_name)

        duration_sec = self._get_audio_duration(audio_path)
        timeout_sec = max(
            _TIMEOUT_MIN_SEC, duration_sec * _TIMEOUT_MULTIPLIER + _TIMEOUT_FIXED_OVERHEAD_SEC
        )
        lang_code = self._resolve_language()

        device_arg = self.config.device or "auto"

        try:
            proc = subprocess.run(
                [
                    str(VENV_PYTHON), str(INFER_SCRIPT), str(audio_path),
                    "--language", lang_code,
                    "--device", device_arg,
                ],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Nemotronサブプロセスがタイムアウトしました(timeout={timeout_sec:.0f}s): {e}"
            ) from e

        if proc.returncode != 0:
            raise RuntimeError(
                f"Nemotronサブプロセスが異常終了しました(code={proc.returncode}): "
                f"{proc.stderr[-2000:]}"
            )

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "Nemotronサブプロセスの出力をJSONとして解析できませんでした: "
                f"{e}\nstdout(先頭2000字): {proc.stdout[:2000]}"
            ) from e

        processing_time = self.perf_logger.end_timing(op_name)

        text = data.get("transcription", "")
        if isinstance(text, list):
            # processor.decode()の戻り値がリスト形状の場合に備えた後方互換(結合する)。
            text = "".join(text)

        result_duration = data.get("audio_duration_sec", duration_sec)

        segment = TranscriptionSegment(
            start=0.0,
            end=result_duration,
            text=text,
            speaker=None,
            confidence=None,
            language=self.config.language,
        )

        self.logger.info(f"Nemotron transcription completed: {len(text)} characters")

        return TranscriptionResult(
            text=text,
            segments=[segment],
            language=self.config.language or "ja",
            duration=result_duration,
            processing_time=processing_time or (time.time() - start_time),
            model_name=self.config.model,
            has_speakers=False,
            metadata={
                "engine": "nemotron-subprocess",
                "infer_elapsed_sec": data.get("infer_elapsed_sec"),
            },
        )
