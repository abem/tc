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

## 長音声チャンク処理(tc-ops #546、2026-09-27追加)

Phase2設計report §5は「長音声チャンク処理: 要」と結論していたが、Phase2実装・
緊急是正のいずれにも未実装だった(査sa実測で判明)。査の線形外挿再計算により、
10分音声でも推定ピークVRAMが総量(16376MiB)を超過する可能性が高いと判明したため、
既存`Qwen3ASREngine._transcribe_long_audio`(`core/transcription_interface.py`
L693-826)と同じ`CHUNK_THRESHOLD_SEC=300`秒の閾値を踏襲し、超過時は音声を
チャンクへ分割してサブプロセスを複数回呼び出す。既存エンジンはメモリ上の
`np.ndarray`をそのままモデルへ渡せるが、Nemotronはサブプロセス経由(ファイル
パスを引数として渡す設計)のため、チャンクは一時wavファイルへ実際に切り出す。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

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
# チャンク分割時は「対象区間の長さ」を基準に算出する(チャンク単位で1プロセス
# 起動→終了するため、全体長ではなくチャンク長に対する余裕があればよい)。
_TIMEOUT_MULTIPLIER = 3.0
_TIMEOUT_FIXED_OVERHEAD_SEC = 30.0
_TIMEOUT_MIN_SEC = 60.0

# 長音声を分割する閾値(秒)。既存Qwen3ASREngine(`core/transcription_interface.py`
# L596)の実績値(RTX 4080 SUPER + torch 2.11.0+cu130環境で15分超のCUBLASエラー
# 実例に基づく安全マージン)を暫定的に踏襲する(Phase2設計report §5)。
CHUNK_THRESHOLD_SEC = 300


def is_nemotron_model(model_name: str) -> bool:
    """モデル名が Nemotron 系かどうかを判定する。

    `Qwen3ASREngine.is_qwen3_model` の判定文字列(`qwen3-asr`/`qwen3_asr`)とは
    互いに排他的な文字列であるため、`UnifiedTranscriber.__init__` での判定順序を
    どちらを先にしても既存モデル名の解決結果には影響しない
    (tc-ops #546 Phase2設計report §2)。
    """
    return "nemotron" in (model_name or "").lower()


def compute_chunk_boundaries(
    duration_sec: float, chunk_threshold_sec: float = CHUNK_THRESHOLD_SEC
) -> list[tuple[float, float]]:
    """音声長からチャンクの(開始秒, 終了秒)境界リストを計算する。

    `duration_sec <= chunk_threshold_sec` の場合は分割せず、全体を単一チャンク
    `[(0.0, duration_sec)]` として返す(通常の短音声はこちらを通る)。
    モデル推論・サブプロセスを一切呼び出さない純粋関数のため、GPU不要で
    単体テスト可能。
    """
    if duration_sec <= 0:
        return [(0.0, 0.0)]
    if duration_sec <= chunk_threshold_sec:
        return [(0.0, duration_sec)]

    boundaries: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_sec:
        end = min(start + chunk_threshold_sec, duration_sec)
        boundaries.append((start, end))
        start = end
    return boundaries


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

    @staticmethod
    def _extract_chunk_wav(audio_path: str, start_sec: float, end_sec: float) -> str:
        """audio_pathの[start_sec, end_sec)区間を16kHzモノラルwavとして一時ファイルへ
        切り出し、そのパスを返す(呼び出し元が使用後に削除する責任を持つ)。

        既存Qwen3ASREngine(`_transcribe_long_audio`)はメモリ上の`np.ndarray`を
        そのままモデルへ渡せるが、Nemotronはサブプロセス経由(ファイルパスを
        引数として渡す設計)のため、実ファイルとして書き出す必要がある。
        """
        import librosa
        import soundfile as sf

        audio, sr = librosa.load(
            str(audio_path), sr=16000, mono=True, offset=start_sec, duration=end_sec - start_sec
        )
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        sf.write(tmp_path, audio, 16000)
        return tmp_path

    def _invoke_subprocess(
        self, audio_path_for_subprocess: str, chunk_duration_sec: float, lang_code: str, device_arg: str
    ) -> dict:
        """`scripts/nemotron_infer.py`を1回起動し、パース済みJSON応答を返す。

        `chunk_duration_sec`はタイムアウト算出のみに使う(全体長ではなく、この
        呼び出しで処理する区間の長さを渡すこと)。異常終了・タイムアウト・
        JSON解析失敗はすべて`RuntimeError`に変換して送出する(呼び出し元が
        チャンク単位でこれを捕捉しプレースホルダに置き換えるか、単一チャンクの
        場合はそのまま`transcribe()`の外へ伝播させるかを選べる設計)。
        """
        timeout_sec = max(
            _TIMEOUT_MIN_SEC, chunk_duration_sec * _TIMEOUT_MULTIPLIER + _TIMEOUT_FIXED_OVERHEAD_SEC
        )

        try:
            proc = subprocess.run(
                [
                    str(VENV_PYTHON), str(INFER_SCRIPT), str(audio_path_for_subprocess),
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
            return json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "Nemotronサブプロセスの出力をJSONとして解析できませんでした: "
                f"{e}\nstdout(先頭2000字): {proc.stdout[:2000]}"
            ) from e

    @staticmethod
    def _extract_text(data: dict) -> str:
        text = data.get("transcription", "")
        if isinstance(text, list):
            # processor.decode()の戻り値がリスト形状の場合に備えた後方互換(結合する)。
            text = "".join(text)
        return text

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Nemotron-3.5-ASR-Streaming で文字起こし(隔離venvサブプロセス経由)。

        音声長が`CHUNK_THRESHOLD_SEC`を超える場合は自動的に分割して処理する。
        """
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
        lang_code = self._resolve_language()
        device_arg = self.config.device or "auto"

        boundaries = compute_chunk_boundaries(duration_sec)

        if len(boundaries) == 1:
            # 短音声: 分割せずそのまま処理(既存の単一チャンク時と完全に同じ挙動・
            # 同じsubprocess呼び出し引数を保つ。異常時は直接RuntimeErrorを伝播する)。
            data = self._invoke_subprocess(audio_path, duration_sec, lang_code, device_arg)
            text = self._extract_text(data)
            result_duration = data.get("audio_duration_sec", duration_sec)
            infer_elapsed_sec: Optional[float] = data.get("infer_elapsed_sec")
        else:
            self.logger.info(
                f"Audio is {duration_sec:.0f}s (>{CHUNK_THRESHOLD_SEC}s), "
                f"splitting into {len(boundaries)} chunks for Nemotron subprocess processing"
            )
            texts: list[str] = []
            failed_chunks = 0
            infer_elapsed_total = 0.0
            for i, (chunk_start, chunk_end) in enumerate(boundaries):
                chunk_path = self._extract_chunk_wav(audio_path, chunk_start, chunk_end)
                try:
                    data = self._invoke_subprocess(
                        chunk_path, chunk_end - chunk_start, lang_code, device_arg
                    )
                    chunk_text = self._extract_text(data)
                    texts.append(chunk_text)
                    infer_elapsed_total += data.get("infer_elapsed_sec") or 0.0
                    self.logger.info(f"Chunk {i + 1}/{len(boundaries)} done")
                except RuntimeError as e:
                    failed_chunks += 1
                    self.logger.warning(f"Chunk {i + 1}/{len(boundaries)} failed: {e}, inserting placeholder")
                    # プレースホルダは前後で改行を強制(自然文ではないため)。
                    # 既存Qwen3ASREngineと同じUXパターン(欠落箇所をユーザーが気づけるようにする)。
                    texts.append(f"\n[チャンク{i + 1}失敗]\n")
                finally:
                    Path(chunk_path).unlink(missing_ok=True)

            if failed_chunks > 0:
                self.logger.warning(
                    f"Long audio transcription completed with {failed_chunks}/{len(boundaries)} failed chunks"
                )

            # チャンク境界がちょうど単語直後で切れた場合の結合防止(既存Qwen3ASREngine
            # と同じ半角スペース区切り、L810台のbugfixパターンを踏襲)。
            text = " ".join(texts)
            result_duration = duration_sec
            infer_elapsed_sec = infer_elapsed_total

        processing_time = self.perf_logger.end_timing(op_name)

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
                "infer_elapsed_sec": infer_elapsed_sec,
                "chunked": len(boundaries) > 1,
                "chunk_count": len(boundaries),
            },
        )
