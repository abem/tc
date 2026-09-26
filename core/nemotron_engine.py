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

## 長音声チャンク処理(tc-ops #546/#548、2026-09-27)

Phase2設計report §5は「長音声チャンク処理: 要」と結論していたが、Phase2実装・
緊急是正のいずれにも未実装だった(査sa実測で判明)。査の線形外挿再計算により、
10分音声でも推定ピークVRAMが総量(16376MiB)を超過する可能性が高いと判明したため、
既存`Qwen3ASREngine._transcribe_long_audio`(`core/transcription_interface.py`
L693-826)と同じ`CHUNK_THRESHOLD_SEC=300`秒の閾値を踏襲し、超過時は音声を
チャンクへ分割する。既存エンジンはメモリ上の`np.ndarray`をそのままモデルへ渡せるが、
Nemotronはサブプロセス経由(ファイルパスを引数として渡す設計)のため、チャンクは
一時wavファイルへ実際に切り出す。

**単一モデルロード化(tc-ops #548是正)**: 当初はチャンクごとに`scripts/nemotron_infer.py`
を新規プロセスとして起動していたが、同スクリプトの`main()`が呼び出しごとにモデルを
再ロードするため、チャンク数に比例してロード時間が累積し重大な性能劣化を招いた
(実測: チャンク分割後62.5秒、分割前19.5秒)。本設計では、全チャンクのファイルパスを
`scripts/nemotron_infer.py`へ一度に渡し(`_invoke_subprocess()`は常に1回だけ呼ばれる)、
同スクリプト側で1回のモデルロードで全チャンクをループ処理する。
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
# 単一モデルロード化(tc-ops #548)により、1プロセスが全チャンクを処理するため、
# 「全チャンク合計の音声長」を基準に算出する(モデルロードは1回のみで済むため、
# チャンク数に応じてこの固定オーバーヘッドを増やす必要はない)。
_TIMEOUT_MULTIPLIER = 3.0
_TIMEOUT_FIXED_OVERHEAD_SEC = 30.0
_TIMEOUT_MIN_SEC = 60.0

# 長音声を分割する閾値(秒)。tc-ops #546「分割最終手段化」是正(2026-09-27)で
# 実機GPU実測に基づき確定した値。
#
# 当初はVRAM制約のみを前提に「5〜30分は原則分割しない」を目指したが、実測により
# Nemotron本体にVRAMとは無関係の**アーキテクチャ上のハード上限**が存在することが
# 判明した: `config.max_position_embeddings=5000`(サブサンプル後のエンコーダ
# フレーム数の上限)。実測で400秒の音声はエンコーダ系列長5001となり
# `ValueError: Sequence Length: 5001 has to be less or equal than
# config.max_position_embeddings 5000.`で確実に失敗する(600秒では系列長7501で
# 同様に失敗)。さらに380秒(RTF 0.043、正常)→399秒(RTF 0.25、6倍近い劣化だが
# 正常終了)という実測から、上限(400秒)に近づくほど推論が急激に不安定化する
# 傾向も確認した。VRAM自体は5分時点でpeak_vram_reserved約7.3GB(空き12GB弱に
# 対し余裕あり)であり、この劣化・失敗はVRAM不足によるものではない。
#
# 采決定(2026-09-27)により、380秒の劣化の兆候を踏まえた安全マージンを見て
# 350秒を新閾値とする(境界400秒から50秒の安全マージン)。「分割は最後の手段」
# という方針自体は維持するが、「5〜30分は原則無分割」という当初目標は撤回し、
# 350秒(約5.8分)を安全な無分割上限とする。
CHUNK_THRESHOLD_SEC = 350

# ストリーミング推論(chunked_limited方式)のlookahead設定(tc-ops #546 Phase2、
# 2026-09-27、采決定)。ストリーミング推論スパイクの実測で、対応値[0, 3, 6, 13]の
# うち最も文字数(精度の代理指標)・RTFともに良好だった値を採用する。
STREAMING_NUM_LOOKAHEAD_TOKENS = 13


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
    """音声長からチャンクの(開始秒, 終了秒)境界リストを計算する(均等分割方式)。

    `duration_sec <= chunk_threshold_sec` の場合は分割せず、全体を単一チャンク
    `[(0.0, duration_sec)]` として返す(通常の短音声はこちらを通る)。

    分割が必要な場合は、`ceil(duration_sec / chunk_threshold_sec)`本のチャンクに
    **均等分割**する(各チャンクの長さは`duration_sec / チャンク本数`で揃える)。

    ## 均等分割を採用した経緯(tc-ops #546是正、2026-09-27)

    当初は固定`chunk_threshold_sec`秒ごとの単純分割だった。実機検証(本番再現用
    音声、language=ja-JP・device=cuda)により、末尾に生じる短いチャンク(実測27.7秒)を
    前方文脈なしで単体推論すると、エラーにはならず正常終了のまま空文字列
    (`"transcription": ""`)を返すことを確認した(采指示の切り分け手順で再現・確定)。

    対策として一時的に「短い最終チャンクの開始位置を前方拡張してオーバーラップさせる」
    実装を行ったが、実測で20秒分の発話(通話では60〜100字程度)が結果にそのまま
    重複して現れることが判明し、利用者への害が大きいとして計・采判断により撤回した。

    代わりに本方式(均等分割)を採用する: 総長を`ceil(総長/chunk_threshold_sec)`本で
    割り、全チャンクを同じ長さにする。これにより「短い末尾チャンク」自体が原理的に
    生じなくなり、重複も生じない。チャンク最大長は`chunk_threshold_sec`秒以下のまま
    変わらない(例: 328秒→164秒×2、620秒→約206.67秒×3、299秒→分割なし1本のまま)。

    モデル推論・サブプロセスを一切呼び出さない純粋関数のため、GPU不要で
    単体テスト可能。
    """
    import math

    if duration_sec <= 0:
        return [(0.0, 0.0)]
    if duration_sec <= chunk_threshold_sec:
        return [(0.0, duration_sec)]

    num_chunks = math.ceil(duration_sec / chunk_threshold_sec)
    chunk_len = duration_sec / num_chunks

    boundaries: list[tuple[float, float]] = []
    start = 0.0
    for i in range(num_chunks):
        # 最終チャンクは浮動小数点の累積誤差を避けるため、必ずduration_secちょうどにする。
        end = duration_sec if i == num_chunks - 1 else start + chunk_len
        boundaries.append((start, end))
        start = end
    return boundaries


# 分割点の無音区間への寄せ(tc-ops #546是正、2026-09-27、采の具体的指示による実装)。
#
# 均等分割点がちょうど発話の途中に当たると、チャンク境界で語が途切れる可能性がある
# (tc-ops #546 D節で確認した「短い孤立チャンクの空応答」問題とは別種の、通常の
# チャンク境界での品質劣化リスク)。分割点そのものを、均等分割点の前後
# ±20秒(`SILENCE_SEARCH_RADIUS_SEC`)の範囲内で最も音量の小さい(＝発話が途切れて
# いる可能性が高い)位置へ寄せることで、境界が発話の真ん中に当たる確率を下げる。
SILENCE_SEARCH_RADIUS_SEC = 20.0
_SILENCE_RMS_FRAME_SEC = 0.2


def find_silence_boundary(
    audio: "np.ndarray",
    sr: int,
    target_sec: float,
    total_duration_sec: float,
    search_radius_sec: float = SILENCE_SEARCH_RADIUS_SEC,
) -> float:
    """`target_sec`の前後`search_radius_sec`秒以内で、最もRMS音量が小さい時刻を返す。

    探索窓が音声の範囲外にはみ出す場合はクランプする。探索窓の実効長が短すぎて
    RMSフレームを1つも作れない場合は、`target_sec`をそのまま返す(＝均等分割点への
    フォールバック。呼び出し元は本関数の戻り値をそのまま分割点として使えばよく、
    フォールバック時の分岐を別途持つ必要はない)。

    モデル推論・サブプロセスを一切呼び出さない純粋関数のため、GPU不要で
    単体テスト可能(`audio`にはダミーのnumpy配列を渡せばよい)。
    """
    import numpy as np

    search_start = max(0.0, target_sec - search_radius_sec)
    search_end = min(total_duration_sec, target_sec + search_radius_sec)
    if search_end <= search_start:
        return target_sec

    frame_length = max(1, int(_SILENCE_RMS_FRAME_SEC * sr))
    hop_length = max(1, frame_length // 2)

    start_sample = int(search_start * sr)
    end_sample = int(search_end * sr)
    segment = audio[start_sample:end_sample]
    if len(segment) < frame_length:
        return target_sec

    try:
        import librosa
        rms = librosa.feature.rms(y=segment, frame_length=frame_length, hop_length=hop_length)[0]
    except Exception:
        # librosa側の予期しない失敗時も、均等分割点へのフォールバックで処理を継続する。
        return target_sec

    if len(rms) == 0:
        return target_sec

    quietest_frame_idx = int(np.argmin(rms))
    quietest_sample_offset = quietest_frame_idx * hop_length
    return search_start + quietest_sample_offset / sr


def adjust_boundaries_to_silence(
    boundaries: list[tuple[float, float]],
    audio_path: str,
    search_radius_sec: float = SILENCE_SEARCH_RADIUS_SEC,
) -> list[tuple[float, float]]:
    """均等分割済みの`boundaries`の内部境界(先頭の0.0・末尾の全体長を除く、
    チャンク間の分割点)を、`find_silence_boundary()`で最寄りの無音区間へ調整する。

    `boundaries`が1件(分割不要)の場合はそのまま返す(音声ファイルを読み込まない)。
    無音区間が見つからない場合、`find_silence_boundary()`が均等分割点をそのまま
    返すため、本関数も自動的に既存の均等分割へフォールバックする。
    """
    if len(boundaries) <= 1:
        return boundaries

    import librosa

    audio, sr = librosa.load(str(audio_path), sr=16000, mono=True)
    total_duration_sec = len(audio) / sr

    adjusted_points = [boundaries[0][0]]  # 先頭は0.0で固定
    for i in range(len(boundaries) - 1):
        original_split = boundaries[i][1]
        new_split = find_silence_boundary(audio, sr, original_split, total_duration_sec, search_radius_sec)
        # 直前の調整済み分割点を下回らないようにクランプする(境界の逆転・消失防止)。
        new_split = max(new_split, adjusted_points[-1])
        adjusted_points.append(new_split)
    adjusted_points.append(boundaries[-1][1])  # 末尾は全体長で固定

    return [(adjusted_points[i], adjusted_points[i + 1]) for i in range(len(adjusted_points) - 1)]


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
        self,
        audio_paths: list[str],
        total_duration_sec: float,
        lang_code: str,
        device_arg: str,
        streaming: bool = False,
    ) -> dict:
        """`scripts/nemotron_infer.py`を1回起動し、パース済みJSON応答を返す。

        `audio_paths`は1件以上のファイルパスのリスト(2件以上の場合、同スクリプト側は
        モデルを1回だけロードして順次処理する。tc-ops #548是正: チャンクごとに
        新規プロセスを起動しモデルを再ロードしていたことによる性能劣化の是正)。
        `total_duration_sec`はタイムアウト算出のみに使う(全チャンク合計の音声長を
        渡すこと。1プロセスで全チャンクを処理するため)。異常終了・タイムアウト・
        JSON解析失敗はすべて`RuntimeError`に変換して送出する。

        `streaming=True`(tc-ops #546 Phase2、350秒超の音声向け)の場合、
        `--streaming --num-lookahead-tokens {STREAMING_NUM_LOOKAHEAD_TOKENS}`を
        付与する。この場合`audio_paths`は1件のみ対応(呼び出し元が保証すること、
        `scripts/nemotron_infer.py`側でも検証している)。
        """
        timeout_sec = max(
            _TIMEOUT_MIN_SEC, total_duration_sec * _TIMEOUT_MULTIPLIER + _TIMEOUT_FIXED_OVERHEAD_SEC
        )

        extra_args = []
        if streaming:
            extra_args = ["--streaming", "--num-lookahead-tokens", str(STREAMING_NUM_LOOKAHEAD_TOKENS)]

        try:
            proc = subprocess.run(
                [
                    str(VENV_PYTHON), str(INFER_SCRIPT), *[str(p) for p in audio_paths],
                    "--language", lang_code,
                    "--device", device_arg,
                    *extra_args,
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
    def _extract_chunk_text(chunk_data: dict) -> str:
        text = chunk_data.get("transcription", "")
        if isinstance(text, list):
            # processor.decode()の戻り値がリスト形状の場合に備えた後方互換(結合する)。
            text = "".join(text)
        return text

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Nemotron-3.5-ASR-Streaming で文字起こし(隔離venvサブプロセス経由)。

        音声長が`CHUNK_THRESHOLD_SEC`を超える場合は自動的にチャンク分割するが、
        サブプロセスの起動・モデルロードは常に1回のみ(tc-ops #548是正)。
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

        chunk_paths_to_cleanup: list[str] = []
        try:
            if duration_sec > CHUNK_THRESHOLD_SEC:
                # tc-ops #546 Phase2(2026-09-27、采決定): 350秒超の音声はまず
                # cache-aware streaming推論(1回のgenerate()で音声全体を一括処理、
                # チャンク分割による文脈喪失が構造的に生じない)を試みる。
                try:
                    self.logger.info(
                        f"Audio is {duration_sec:.0f}s (>{CHUNK_THRESHOLD_SEC}s), "
                        f"using cache-aware streaming inference "
                        f"(num_lookahead_tokens={STREAMING_NUM_LOOKAHEAD_TOKENS})"
                    )
                    data = self._invoke_subprocess(
                        [audio_path], duration_sec, lang_code, device_arg, streaming=True,
                    )
                    boundaries = [(0.0, duration_sec)]
                    chunked = False
                except Exception as e:
                    # ストリーミング推論の失敗はユーザーから見て失敗にせず、既存の
                    # 均等分割+無音区間調整方式へフォールバックする(采指示)。
                    self.logger.warning(f"Streaming推論が失敗、分割方式へフォールバック: {e}")
                    boundaries = compute_chunk_boundaries(duration_sec)
                    # 分割点を均等分割点の前後±20秒の範囲で最も静かな位置へ寄せる(采指示)。
                    # 無音区間が見つからない場合は自動的に均等分割点へフォールバックする。
                    boundaries = adjust_boundaries_to_silence(boundaries, audio_path)
                    self.logger.info(
                        f"Falling back to {len(boundaries)}-way silence-adjusted split "
                        "(single subprocess/model load)"
                    )
                    chunk_paths_to_cleanup = [
                        self._extract_chunk_wav(audio_path, s, e) for s, e in boundaries
                    ]
                    data = self._invoke_subprocess(chunk_paths_to_cleanup, duration_sec, lang_code, device_arg)
                    chunked = True
            else:
                # 短音声: 分割不要・ストリーミングも使わない(既存動作を変更しない)。
                boundaries = [(0.0, duration_sec)]
                chunked = False
                data = self._invoke_subprocess([audio_path], duration_sec, lang_code, device_arg)
        finally:
            for p in chunk_paths_to_cleanup:
                Path(p).unlink(missing_ok=True)

        processing_time = self.perf_logger.end_timing(op_name)

        chunk_results = data.get("chunks", [])
        texts: list[str] = []
        failed_chunks = 0
        empty_chunks = 0
        infer_elapsed_total = 0.0
        for i, chunk_data in enumerate(chunk_results):
            if "error" in chunk_data:
                failed_chunks += 1
                self.logger.warning(
                    f"Chunk {i + 1}/{len(chunk_results)} failed: {chunk_data['error']}, inserting placeholder"
                )
                # プレースホルダは前後で改行を強制(自然文ではないため)。
                # 既存Qwen3ASREngineと同じUXパターン(欠落箇所をユーザーが気づけるようにする)。
                texts.append(f"\n[チャンク{i + 1}失敗]\n")
            else:
                chunk_text = self._extract_chunk_text(chunk_data)
                if not chunk_text:
                    # モデルが例外を出さず正常終了したまま空文字列を返すケース
                    # (長い無音区間等、tc-ops #546是正で実機確認した事象)。
                    # failed_chunks(異常終了)とは別枠で記録する(計指示)。
                    # プレースホルダは挿入しない(空文字列を返すこと自体は正常応答の
                    # 一種であり、失敗とは断定できないため)。
                    empty_chunks += 1
                    self.logger.warning(
                        f"Chunk {i + 1}/{len(chunk_results)} returned an empty transcription "
                        "(possible long silence or isolated short segment)"
                    )
                texts.append(chunk_text)
                infer_elapsed_total += chunk_data.get("infer_elapsed_sec") or 0.0

        if failed_chunks > 0:
            self.logger.warning(
                f"Transcription completed with {failed_chunks}/{len(chunk_results)} failed chunks"
            )
        if empty_chunks > 0:
            self.logger.warning(
                f"Transcription completed with {empty_chunks}/{len(chunk_results)} chunks "
                "returning empty transcription"
            )

        # チャンク境界がちょうど単語直後で切れた場合の結合防止(既存Qwen3ASREngine
        # と同じ半角スペース区切り、L810台のbugfixパターンを踏襲)。単一チャンクの
        # 場合はtexts長が1のため実質的に結合の影響はない。
        text = " ".join(texts)

        segment = TranscriptionSegment(
            start=0.0,
            end=duration_sec,
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
            duration=duration_sec,
            processing_time=processing_time or (time.time() - start_time),
            model_name=self.config.model,
            has_speakers=False,
            metadata={
                "engine": "nemotron-subprocess",
                "infer_elapsed_sec": infer_elapsed_total,
                "load_elapsed_sec": data.get("load_elapsed_sec"),
                "chunked": chunked,
                "chunk_count": len(boundaries),
                "failed_chunks": failed_chunks,
                "empty_chunks": empty_chunks,
            },
        )
