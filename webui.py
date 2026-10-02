#!/usr/bin/env -S uv run streamlit run
"""
Transcribe Audio - WebUI (Streamlitプロトタイプ)

Phase2最小構成(URL入力→文字起こし→履歴表示)。設計書:
- 作から計への設計書_変換履歴DB設計_20260806.md
- 作から計への設計書_WebUIフレームワーク選定とプロトタイプ方針_20260806.md

`core/transcription_interface.py` / `core/cli_workflow.py` の既存関数(公開シグネチャ)は
変更せず、ここと `core/webui_workflow.py` から呼び出すだけに留める(設計書§6)。
"""

from __future__ import annotations

import tempfile
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import streamlit as st

# 警告抑制を統一設定(suppress_warnings.py は import 時に自動で全抑制を実行)
import suppress_warnings  # noqa: F401

from core.cli_common import detect_input_type, resolve_device
from core.cli_workflow import (
    DEFAULT_HISTORY_DB_PATH,
    InputResolution,
    cleanup_input_audio,
    finalize_transcription,
    resolve_input_audio,
)
from core.config import SystemConfig, TranscriptionConfig, UnifiedConfig
from core.history import (
    connect_history,
    count_history_before,
    delete_history_before,
    search_history,
)
from core.logging import get_logger, setup_logging
from core.nemotron_engine import is_nemotron_model
from core.transcription_interface import UnifiedTranscriber
from core.uploads import cleanup_old_uploads
from core.utils import sanitize_upload_filename
from core.webui_workflow import (
    QueueItem,
    QueueItemState,
    TranscriptionJob,
    TranscriptionJobQueue,
    apply_progress,
    drain_progress,
    estimate_remaining,
    format_elapsed,
    segments_to_srt,
    start_transcription_job,
)

st.set_page_config(page_title="Transcribe Audio WebUI", layout="wide")

logger = get_logger(__name__)

UPLOAD_DIR = Path("output/uploads")
UPLOAD_RETENTION_DAYS = 7  # アップロードの保持日数。これを過ぎた項目は新しい投入のたびに整理する(docs/spec D7)


def _load_config() -> None:
    if "config_loaded" not in st.session_state:
        try:
            UnifiedConfig.load("config/config.yaml")
        except Exception:
            pass
        st.session_state["config_loaded"] = True


@st.cache_resource
def _warmup_qwen_asr() -> bool:
    """WebUIプロセス起動時にqwen_asrパッケージのimportを一度だけ先行実行する
    (tc-ops #441関連の暫定緩和策)。モデル重み本体のロードは行わない(import文のみ)。
    st.cache_resourceによりプロセス単位でキャッシュされ、複数セッションから呼ばれても
    1回のみ実行される。importに失敗してもWebUI起動自体は継続する(警告ログのみ)。

    位置づけの注意: 本関数はStreamlitの最初のセッション接続(スクリプト初回exec)時に実行される。
    Streamlitの実行モデル上「HTTPリクエストを一切受けていない状態でコードを実行する」ことは
    できないため、「サーバー起動から完全に独立した事前実行」は担保しない。担保するのは
    「ページロード時点で実行され、ユーザーが実際に文字起こしを投入する操作より確実に先行する」
    ことである(tc-ops #441の根本原因調査(是正実装は別途)とは独立した対症療法)。
    """
    try:
        import qwen_asr  # noqa: F401
        logger.info("qwen_asrウォームアップ成功")
        return True
    except Exception as e:
        logger.warning("qwen_asrウォームアップ失敗(起動は継続): %s", e)
        return False


def _render_input_form() -> Dict[str, Any]:
    """入力フォーム(設計書§3-1)。"""
    st.subheader("入力")
    source_url = st.text_input("YouTube / Google Drive URL", value="", key="source_url")
    allowed_extensions = [ext.lstrip(".") for ext in SystemConfig().allowed_file_types]
    uploaded_file = st.file_uploader(
        "またはローカルファイルをアップロード",
        type=allowed_extensions,
        key="uploaded_file",
    )
    if source_url:
        detected = detect_input_type(source_url)
        st.caption(f"検出された入力タイプ: {detected['type']}")
    elif uploaded_file is not None:
        st.caption("検出された入力タイプ: local")
    return {"source_url": source_url, "uploaded_file": uploaded_file}


def _render_settings_panel() -> Dict[str, Any]:
    """設定パネル(設計書§3-2)。"""
    st.subheader("設定")
    col1, col2, col3 = st.columns(3)
    with col1:
        model = st.selectbox(
            "モデル",
            options=[
                "Qwen/Qwen3-ASR-1.7B",
                "kotoba-tech/kotoba-whisper-v2.2",
                "openai/whisper-large-v3",
                "nvidia/nemotron-3.5-asr-streaming-0.6b",
            ],
            index=0,
        )
    with col2:
        device_choice = st.selectbox("デバイス", options=["auto", "cuda", "cpu"], index=0)
    with col3:
        language_choice = st.selectbox("言語", options=["自動判定", "ja", "en"], index=0)

    # Nemotronはオフラインバッチ推論が単一セグメントのみを返す設計のため、
    # タイムスタンプ(ForcedAligner/SRT出力)には現時点で非対応(tc-ops #546 Phase2)。
    nemotron_selected = is_nemotron_model(model)
    include_timestamps = st.checkbox(
        "タイムスタンプ付与(ForcedAligner使用、GPUメモリ約1.2GB追加)",
        value=False,
        disabled=nemotron_selected,
    )
    if nemotron_selected:
        st.caption("Nemotronは現時点でタイムスタンプ非対応です")
        # disabled=Trueはウィジェットの操作を防ぐだけで、直前のモデル(Qwen等)で
        # チェック済みだった値(True)はStreamlitのウィジェット状態として保持され続ける。
        # そのままだとitem.settings["include_timestamps"]がTrueで送信され、L409の
        # SRTプレビューが実行されて「実質1行の壊れた出力」が表示される(査sa是正指摘)。
        # disabledに加えて値自体をFalseへ強制上書きする。
        include_timestamps = False
    return {
        "model": model,
        "device": device_choice,
        "language": None if language_choice == "自動判定" else language_choice,
        "include_timestamps": include_timestamps,
    }


def _render_context_hints_panel() -> str:
    """`context_hints` 入力欄(設計書§4)。デフォルト非表示・警告常時表示・使用前同意必須。"""
    context_value = ""
    with st.expander("認識ヒント(固有名詞・専門用語) — 通常は不要", expanded=False):
        st.warning(
            "⚠️ 音声の無音・不明瞭区間で、ここに入力した語句が実際には発話されていない内容として"
            "出力に混入することがあります(実機検証済みの既知リスク)。出力結果は必ず目視確認してください。"
        )
        hint_text = st.text_area("ヒント語彙(1行1語彙)", value="", key="context_hints_input")
        if hint_text.strip():
            consent = st.checkbox("上記リスクを理解した上でヒントを使用する", key="context_hints_consent")
            if consent:
                context_value = " ".join(line.strip() for line in hint_text.splitlines() if line.strip())
            else:
                st.info("同意チェックが無いため、ヒントは使用されません。")
    return context_value


def _resolve_input(
    form_values: Dict[str, Any], download_dir: Path, on_status: Callable[[str], None]
) -> Optional[InputResolution]:
    """`download_dir` は投入(enqueue)ごとに一意なディレクトリを渡すこと。YouTube/X経路は
    `resolve_input_audio()`の既存の`output_dir`引数をそのまま使ってダウンロード先を分離し、
    同一URLを複数回投入した際のファイルパス衝突(tc-ops #440是正・不具合2)を防ぐ
    (`core/cli_workflow.py`・`handlers/youtube.py`は無変更)。

    `on_status`はバックグラウンドスレッド(`_start_resolution_job()`、tc-ops #440是正3)から
    呼ばれるため、`st.write`を直接渡さないこと(`ScriptRunContext`が無いスレッドからの
    Streamlit UI呼び出しは安全でない)。呼び出し元は`QueueItem.log`への追記等、非UI手段を渡す。

    診断ログ(tc-ops #440是正2・査sa差し戻し対応): `resolve_input_audio()`が通常の`Exception`
    (yt-dlpのダウンロード失敗等、`handlers/youtube.py` L184-186で`raise`される)場合にtoken
    (`download_dir.name`)付きでログしてから re-raiseする。
    """
    if form_values["source_url"]:
        try:
            return resolve_input_audio(
                form_values["source_url"], download_dir, ensure_yt_dlp=True, on_status=on_status
            )
        except Exception as e:
            logger.error("resolve_input_audio失敗(通常のException) token=%s error=%s", download_dir.name, e)
            raise
    if form_values["uploaded_file"] is not None:
        upload_dir = UPLOAD_DIR
        upload_dir.mkdir(parents=True, exist_ok=True)
        # Streamlitの`UploadedFile.name`はクライアントが送った文字列のまま(`../`等を含み得る)なので、
        # 区切り文字を除いた単一のファイル名にしてから連結し、保存先が必ず`output/uploads/`直下になるようにする。
        safe_name = sanitize_upload_filename(form_values["uploaded_file"].name)
        # アップロードごとに専用の一意なサブディレクトリを作る。同名のファイルを続けてアップロードしても
        # 互いを上書きしない(キューに同名が複数あると、先のジョブが処理中のファイルが書き換わっていた)。
        # ファイル名はそのまま残る(履歴・表示の見え方を変えない)。
        # (mkdtemp は絶対パスを返すため、従来どおり相対パス(output/uploads/...)のままにする)
        local_path = upload_dir / Path(tempfile.mkdtemp(dir=upload_dir)).name / safe_name
        if local_path.resolve().parent.parent != upload_dir.resolve():
            raise ValueError(f"アップロード先が想定の場所の外になります: {form_values['uploaded_file'].name!r}")
        with open(local_path, "wb") as f:
            f.write(form_values["uploaded_file"].getbuffer())
        return InputResolution(
            source_type="local",
            original_source=str(local_path),
            local_audio_path=str(local_path),
            is_temp_file=False,
            metadata=None,
            youtube_handler=None,
        )
    return None


def _get_queue() -> TranscriptionJobQueue:
    if "job_queue" not in st.session_state:
        st.session_state["job_queue"] = TranscriptionJobQueue()
    return st.session_state["job_queue"]


def _start_job_from_item(item: QueueItem) -> TranscriptionJob:
    """`TranscriptionJobQueue.dispatch_next()` へ渡す起動関数(キュー項目からジョブを起動する)。"""
    settings = item.settings
    transcription_config = TranscriptionConfig(
        model=settings["model"],
        language=settings["language"],
        device=settings["device"],
        include_timestamps=settings["include_timestamps"],
        context=settings["context"],
    )
    transcriber = UnifiedTranscriber(transcription_config)
    return start_transcription_job(transcriber, item.resolution.local_audio_path)


def _start_resolution_job(
    job_queue: TranscriptionJobQueue, item: QueueItem, form_values: Dict[str, Any], download_dir: Path, token: str
) -> None:
    """`item`(`RESOLVING`状態)の入力解決(ダウンロード等)をバックグラウンドスレッドで実行する
    (tc-ops #440是正3)。完了時に`job_queue.resolve_success()`/`resolve_failed()`で状態遷移させる。

    `start_transcription_job()`(文字起こし本体の非同期実行)と同じパターン。バックグラウンド
    スレッドはメインスクリプトのRerunException(tc-ops #440是正2で確定した中断原因)の影響を
    受けないため、`_enqueue_job()`側で既にキューへ追加済みの`item`が消えることはない。
    """

    def _on_status(message: str) -> None:
        if not apply_progress(item, message):
            item.log.append(message)

    def _run() -> None:
        logger.info("_resolve_input開始(background) token=%s item_id=%s", token, item.item_id)
        t0 = time.time()
        try:
            resolution = _resolve_input(form_values, download_dir, _on_status)
        except BaseException as e:  # noqa: BLE001 - 失敗をFAILEDへ伝える(ジョブ実行スレッドと同一方針)
            logger.info(
                "_resolve_input失敗(background) token=%s item_id=%s elapsed=%.2fs",
                token, item.item_id, time.time() - t0,
            )
            job_queue.resolve_failed(item, e)
            return
        logger.info(
            "_resolve_input完了(background) token=%s item_id=%s elapsed=%.2fs", token, item.item_id, time.time() - t0
        )
        if resolution is None:
            job_queue.resolve_failed(item, RuntimeError("URLを入力するか、ファイルをアップロードしてください。"))
            return
        job_queue.resolve_success(item, resolution)

    threading.Thread(target=_run, daemon=True).start()


def _sweep_old_uploads(job_queue: TranscriptionJobQueue) -> None:
    """保持期間を過ぎたアップロードを整理する。処理待ち・処理中のジョブが使うファイルは消さない。
    整理の失敗で投入を止めない。"""
    try:
        in_use = [
            item.resolution.local_audio_path
            for item in job_queue.items
            if item.state in (QueueItemState.QUEUED, QueueItemState.PROCESSING)
            and item.resolution is not None
            and item.resolution.source_type == "local"
        ]
        cleanup_old_uploads(UPLOAD_DIR, UPLOAD_RETENTION_DAYS, protected_paths=in_use)
    except Exception as e:  # noqa: BLE001 - 整理は付随処理。投入そのものは続ける
        logger.warning("アップロードの整理に失敗しました(投入は続行): %s", e)


def _enqueue_job(form_values: Dict[str, Any], settings_values: Dict[str, Any], context_value: str) -> None:
    """キューへ即座に追加してから入力解決(ダウンロード等)をバックグラウンドで開始する
    (現行ジョブが処理中でも追加投入できる。要件4-2-1)。

    tc-ops #440是正3: 本関数は`st.foo`呼び出し(Streamlitの暗黙のyieldポイント)を一切含まない
    ため、他の操作(2件目のボタンクリック等)によるRerunExceptionで中断されることが原理的にない
    (tc-ops #440是正2で確定した原因への根本対応)。ダウンロード自体は`_start_resolution_job()`
    がバックグラウンドスレッドで行う。キューに`RESOLVING`状態で即座に反映されることが、
    「クリック直後に状態変化が見える」という不具合1是正の要件も引き続き満たす。
    """
    if not form_values["source_url"] and form_values["uploaded_file"] is None:
        st.error("URLを入力するか、ファイルをアップロードしてください。")
        return

    token = uuid.uuid4().hex[:8]
    logger.info(
        "enqueue試行開始 token=%s source_url=%s uploaded_file=%s",
        token,
        form_values.get("source_url") or "(none)",
        form_values["uploaded_file"].name if form_values.get("uploaded_file") is not None else "(none)",
    )
    download_dir = Path("output") / "queue_downloads" / token

    # 解決済みdevice・context_valueをjob_settingsへ書き戻す(record_transcription_history()に
    # 渡る際、未解決の"auto"のままcontext_hints_used=0固定で記録されるのを防ぐため。査sa指摘是正)。
    job_settings = dict(settings_values)
    job_settings["device"] = resolve_device(settings_values["device"])
    job_settings["context"] = context_value

    label = form_values["source_url"] or form_values["uploaded_file"].name

    job_queue = _get_queue()
    _sweep_old_uploads(job_queue)
    item = job_queue.enqueue_pending(label=label, settings=job_settings)
    logger.info("enqueue(pending)完了 token=%s item_id=%s", token, item.item_id)

    _start_resolution_job(job_queue, item, form_values, download_dir, token)


def _dispatch_next_job(job_queue: TranscriptionJobQueue) -> None:
    """処理中ジョブが無ければ、キュー先頭の待機項目を起動する(要件4-2-2の自動連続処理)。"""
    job_queue.dispatch_next(_start_job_from_item)


def _cleanup_temp_file(resolution: InputResolution) -> None:
    """ダウンロードした一時音声ファイルを削除する(文字起こし失敗時の経路用。D5)。
    削除対象の判定・削除は `core.cli_workflow.cleanup_input_audio`、ここでは警告表示だけを行う。"""
    warning = cleanup_input_audio(resolution)
    if warning:
        st.warning(warning)


def _save_and_record(
    job: TranscriptionJob, resolution: InputResolution, settings_values: Dict[str, Any]
) -> tuple[str, Optional[str]]:
    """完了したジョブの結果を保存し、変換履歴を記録する(設計書§5-2の統合パターンをWebUI側でも踏襲)。

    保存・アップロード・履歴記録・一時ファイル削除は `core.cli_workflow.finalize_transcription`
    (tc / transcribe.py と共通)で行い、ここでは結果を `st.warning` で表示するだけにする。

    戻り値は `(output_file, gdrive_url)`。呼び出し元(キュー項目単位)が結果の保持先を持つため、
    ここでは `st.session_state` の共有キーへは書き込まない(tc-ops #440: 複数ジョブが並行して
    キューに存在するため、単一の共有キーに書くと後続ジョブに上書きされる)。
    """
    outcome = finalize_transcription(
        result=job.result,
        resolution=resolution,
        output_dir=Path("output"),
        settings=settings_values,
    )
    if outcome.upload_error is not None:
        st.warning(f"Google Driveアップロードに失敗しました: {outcome.upload_error}")
    if outcome.history_error is not None:
        st.warning(f"変換履歴の記録に失敗しました: {outcome.history_error}")
    if outcome.cleanup_warning:
        st.warning(outcome.cleanup_warning)

    return str(outcome.output_file), outcome.gdrive_url


def _format_time(epoch: Optional[float]) -> str:
    """UNIXタイムスタンプを`HH:MM:SS`形式の文字列に変換する(未設定時は`-`)。"""
    if epoch is None:
        return "-"
    return datetime.fromtimestamp(epoch).strftime("%H:%M:%S")


def _format_finished_item_label(item: QueueItem) -> str:
    """完了済み一覧の見出し文言を組み立てる(WebUIキュー表示順・識別性改善)。

    `item_id`(投入順の連番)と確定時刻を見出しに含めることで、同一ラベル(同一URL等)の複数項目が
    画面上で区別できない問題(識別不能問題)と、なぜこの並び順なのかが読み取れない問題
    (表示順問題)の両方を改善する。"""
    status_label = "完了" if item.state == QueueItemState.DONE else "失敗"
    return f"[{status_label}] #{item.item_id} {item.label} (確定 {_format_time(item.finished_at)})"


def _sorted_finished_items(job_queue: TranscriptionJobQueue) -> List[QueueItem]:
    """完了済み一覧を確定時刻(`finished_at`)の降順(真の新しい順)でソートする
    (WebUIキュー表示順改善)。

    是正前は投入`item_id`の降順(`list(reversed(job_queue.finished))`)で表示しており、
    「投入は後だが確定は先」の項目と「投入は先だが確定は後」の項目が混在すると、実際に
    最後に確定した結果が一番上に来るとは限らなかった(tc-ops #440是正3以降の網羅調査で確認)。
    """
    return sorted(job_queue.finished, key=lambda item: item.finished_at or 0, reverse=True)


def _render_result_detail(item: QueueItem) -> None:
    """完了項目1件分の結果プレビュー(旧`_render_progress_and_result`の結果表示部分を踏襲)。"""
    result = item.job.result if item.job is not None else None
    if result is None:
        return

    st.success(f"文字起こし完了(保存先: {item.output_file})")
    if item.gdrive_url:
        st.write(f"Google Drive URL: {item.gdrive_url}")

    metadata = result.metadata or {}
    failed = metadata.get("failed_chunks", 0)
    repeated = metadata.get("repeated_chunks", 0)
    if failed:
        st.warning(f"{failed}個のチャンクが失敗し、該当区間に[チャンクN失敗]プレースホルダが挿入されました")
    if repeated:
        st.warning(f"{repeated}個のチャンクで反復ループを検出しました")

    st.text_area("文字起こし結果", value=result.text, height=300, key=f"result_text_area_{item.item_id}")

    if item.settings.get("include_timestamps"):
        srt_text = segments_to_srt(result.segments)
        if srt_text:
            st.text_area("SRTプレビュー", value=srt_text, height=200, key=f"result_srt_area_{item.item_id}")
        else:
            st.caption("SRTを生成できるタイムスタンプ情報がありません。")
    else:
        st.caption("SRTプレビューを表示するには、設定パネルでタイムスタンプ付与を有効にしてください。")


def _render_item_progress(item: QueueItem, *, since: float, idle_text: str) -> None:
    """進捗バー(進捗率が分かる間)または経過時間つきの処理中表示。1秒ごとの再描画で経過時間が動くため、
    進捗率が取れない処理(短い音声・Nemotron等)でも画面が止まって見えない。"""
    elapsed = time.time() - since
    if item.progress is not None:
        remaining = estimate_remaining(elapsed, item.progress)
        text = f"{item.progress_text}  経過 {format_elapsed(elapsed)}"
        if remaining is not None:
            text += f" / 残り約 {format_elapsed(remaining)}"
        st.progress(item.progress, text=text)
    else:
        st.info(f"{item.progress_text or idle_text}  経過 {format_elapsed(elapsed)}")


@st.fragment(run_every="1s")
def _render_queue_and_result() -> None:
    """リアルタイム進捗表示・結果プレビュー・キュー状態表示(設計書§3-3・§3-4、非同期方式は§5、
    tc-ops #440: 複数ジョブの逐次自動処理・キュー状態可視化)。"""
    job_queue = _get_queue()

    current = job_queue.current
    if current is not None and current.job is not None:
        for message in drain_progress(current.job):
            if not apply_progress(current, message):
                current.log.append(message)

        if current.job.done:
            if current.job.error is not None:
                st.error(f"文字起こしに失敗しました: {current.job.error}")
                _cleanup_temp_file(current.resolution)
                job_queue.mark_failed(current, error_message=str(current.job.error))
            else:
                output_file, gdrive_url = _save_and_record(current.job, current.resolution, current.settings)
                job_queue.mark_done(current, output_file=output_file, gdrive_url=gdrive_url)

    _dispatch_next_job(job_queue)

    st.subheader("キュー状態")

    resolving = job_queue.resolving
    if resolving:
        for item in resolving:
            st.write(f"解決中(ダウンロード等): {item.label}")
            _render_item_progress(item, since=item.submitted_at, idle_text="取得の準備中です...")
            if item.log:
                st.text("\n".join(item.log[-5:]))

    st.caption(f"待機件数: {len(job_queue.queued)}件")

    current = job_queue.current
    if current is None:
        st.caption("処理中のジョブはありません。入力・設定後に「キューに追加」を押してください。")
    else:
        st.write(f"処理中: {current.label}")
        if current.log:
            st.text("\n".join(current.log[-10:]))
        _render_item_progress(
            current, since=current.started_at or current.submitted_at, idle_text="処理中です..."
        )

    finished = _sorted_finished_items(job_queue)
    if finished:
        st.subheader("完了済み一覧")
        for item in finished:
            with st.expander(_format_finished_item_label(item)):
                st.caption(
                    f"投入順: {item.item_id}件目 / 投入時刻: {_format_time(item.submitted_at)} / "
                    f"確定時刻: {_format_time(item.finished_at)}"
                )
                if item.state == QueueItemState.DONE:
                    _render_result_detail(item)
                else:
                    st.error(f"文字起こしに失敗しました: {item.error_message}")


# 履歴DB操作は core.history へ移設済み。既存テスト(tests/test_webui_history_cleanup.py)が
# webui._count_history_before / _delete_history_before を参照するため同名エイリアスを残す。
_count_history_before = count_history_before
_delete_history_before = delete_history_before


def _render_history_cleanup_section() -> None:
    """変換履歴の一括削除(古い履歴、DB行のみ)。即座に無警告で削除しない、
    「①対象件数を確認」→「②件数付きで削除実行」の2段階UX(誤操作防止)。

    `st.session_state["history_cleanup_confirm"]`に確認時のN日・cutoff_date・件数を保持し、
    削除実行時も同じcutoff_dateを使う(確認件数と削除件数のズレ防止)。Nの値を確認後に変更した
    場合は確認状態を無効化する(古いNのまま削除されるのを防ぐ)。
    """
    with st.expander("古い履歴の一括削除", expanded=False):
        n_days = st.number_input(
            "N日より前の履歴を削除", min_value=1, value=30, step=1, key="history_cleanup_n_days"
        )
        if st.button("① 対象件数を確認", key="history_cleanup_check"):
            cutoff = date.today() - timedelta(days=int(n_days))
            conn = connect_history(DEFAULT_HISTORY_DB_PATH)
            try:
                count = count_history_before(conn, cutoff)
            finally:
                conn.close()
            st.session_state["history_cleanup_confirm"] = {
                "cutoff_date": cutoff,
                "n_days": int(n_days),
                "count": count,
            }

        confirm = st.session_state.get("history_cleanup_confirm")
        if confirm is not None and confirm["n_days"] == int(n_days):
            if confirm["count"] > 0:
                st.write(
                    f"{confirm['cutoff_date'].isoformat()} より前の履歴が{confirm['count']}件あります"
                    "(削除対象はデータベースの記録のみで、output/配下のファイルやGoogle Drive上の"
                    "ファイルは削除されません)。"
                )
                if st.button(f"② {confirm['count']}件を削除する", key="history_cleanup_execute"):
                    conn = connect_history(DEFAULT_HISTORY_DB_PATH)
                    try:
                        deleted = delete_history_before(conn, confirm["cutoff_date"])
                    finally:
                        conn.close()
                    st.session_state.pop("history_cleanup_confirm", None)
                    st.success(f"{deleted}件の履歴を削除しました。")
            else:
                st.caption("削除対象の履歴はありません。")


def _render_history_tab() -> None:
    """履歴一覧画面(設計書§3-5)。"""
    st.subheader("変換履歴")
    if not DEFAULT_HISTORY_DB_PATH.exists():
        st.caption("履歴はまだありません。")
        return

    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("開始日", value=None, key="history_date_from")
    with col2:
        date_to = st.date_input("終了日", value=None, key="history_date_to")
    search_keyword = st.text_input("キーワード検索", value="", key="history_keyword")
    st.caption("3文字以上で検索できます(2文字以下は検索結果が得られません)")

    _render_history_cleanup_section()

    conn = connect_history(DEFAULT_HISTORY_DB_PATH)
    try:
        rows = search_history(conn, date_from=date_from, date_to=date_to, keyword=search_keyword)
    finally:
        conn.close()

    if not rows:
        st.caption("該当する履歴がありません。")
        return

    for row in rows:
        title = row["source_title"] or row["source_original"]
        with st.expander(f"{row['processed_at']} - {title} ({row['model_name']})"):
            st.checkbox("出力対象に含める", key=f"history_select_{row['id']}")
            st.write(f"音源種別: {row['source_type']}")
            st.write(f"文字数: {row['char_count']} / 処理時間: {row['processing_time_sec']:.1f}秒")
            if row["gdrive_url"]:
                st.write(f"Google Drive: {row['gdrive_url']}")
            st.text_area(
                "結果テキスト",
                value=row["result_text"],
                height=200,
                key=f"history_text_{row['id']}",
            )

    selected_rows = [row for row in rows if st.session_state.get(f"history_select_{row['id']}", False)]
    if selected_rows:
        summary_parts = []
        for row in selected_rows:
            title = row["source_title"] or row["source_original"]
            summary_parts.append(
                f"## {row['processed_at']} - {title}（{row['model_name']}）\n\n{row['result_text']}\n\n---"
            )
        summary_markdown = "\n\n".join(summary_parts)
        st.download_button(
            "選択履歴をまとめ出力",
            data=summary_markdown,
            file_name=f"history_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            key="history_summary_download",
        )


def main() -> None:
    setup_logging()
    _load_config()
    _warmup_qwen_asr()
    st.title("Transcribe Audio WebUI")

    tab_transcribe, tab_history = st.tabs(["文字起こし", "履歴"])

    with tab_transcribe:
        form_values = _render_input_form()
        settings_values = _render_settings_panel()
        context_value = _render_context_hints_panel()

        if st.button("キューに追加", type="primary"):
            _enqueue_job(form_values, settings_values, context_value)

        _render_queue_and_result()

    with tab_history:
        _render_history_tab()


if __name__ == "__main__":
    main()
