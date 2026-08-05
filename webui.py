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

import os
import sqlite3
import threading
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import streamlit as st

# 警告抑制を統一設定(suppress_warnings.py は import 時に自動で全抑制を実行)
import suppress_warnings  # noqa: F401

from core.cli_common import build_output_file, detect_input_type, resolve_device
from core.cli_workflow import (
    DEFAULT_HISTORY_DB_PATH,
    InputResolution,
    record_transcription_history,
    resolve_input_audio,
    upload_transcription_result,
)
from core.config import DiarizationConfig, SystemConfig, TranscriptionConfig, UnifiedConfig
from core.logging import get_logger
from core.transcription_interface import UnifiedTranscriber
from core.webui_workflow import (
    QueueItem,
    QueueItemState,
    TranscriptionJob,
    TranscriptionJobQueue,
    drain_progress,
    segments_to_srt,
    start_transcription_job,
)

st.set_page_config(page_title="Transcribe Audio WebUI", layout="wide")

logger = get_logger(__name__)


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
            options=["Qwen/Qwen3-ASR-1.7B", "kotoba-tech/kotoba-whisper-v2.2", "openai/whisper-large-v3"],
            index=0,
        )
    with col2:
        device_choice = st.selectbox("デバイス", options=["auto", "cuda", "cpu"], index=0)
    with col3:
        language_choice = st.selectbox("言語", options=["自動判定", "ja", "en"], index=0)

    diarization = st.checkbox("話者分離を有効化", value=False)
    include_timestamps = st.checkbox(
        "タイムスタンプ付与(ForcedAligner使用、GPUメモリ約1.2GB追加)",
        value=False,
    )
    return {
        "model": model,
        "device": device_choice,
        "language": None if language_choice == "自動判定" else language_choice,
        "diarization": diarization,
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
        upload_dir = Path("output/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        local_path = upload_dir / form_values["uploaded_file"].name
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
    diarization_config = DiarizationConfig(enable_diarization=True) if settings["diarization"] else None
    transcriber = UnifiedTranscriber(transcription_config, diarization_config)
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
    item = job_queue.enqueue_pending(label=label, settings=job_settings)
    logger.info("enqueue(pending)完了 token=%s item_id=%s", token, item.item_id)

    _start_resolution_job(job_queue, item, form_values, download_dir, token)


def _dispatch_next_job(job_queue: TranscriptionJobQueue) -> None:
    """処理中ジョブが無ければ、キュー先頭の待機項目を起動する(要件4-2-2の自動連続処理)。"""
    job_queue.dispatch_next(_start_job_from_item)


def _cleanup_temp_file(resolution: InputResolution) -> None:
    """ダウンロードした一時音声ファイルを削除する(成功・失敗いずれの経路でも呼び出す)。
    ローカルアップロードファイルは削除しない(tc/transcribe.pyの既存挙動と整合)。"""
    needs_cleanup = resolution.is_temp_file or resolution.source_type == "gdrive"
    if not needs_cleanup:
        return
    try:
        if os.path.exists(resolution.local_audio_path):
            if resolution.youtube_handler:
                resolution.youtube_handler.cleanup_temp_file(resolution.local_audio_path)
            else:
                os.remove(resolution.local_audio_path)
    except Exception as e:
        st.warning(f"一時ファイルの削除に失敗しました: {e}")


def _save_and_record(
    job: TranscriptionJob, resolution: InputResolution, settings_values: Dict[str, Any]
) -> tuple[str, Optional[str]]:
    """完了したジョブの結果を保存し、変換履歴を記録する(設計書§5-2の統合パターンをWebUI側でも踏襲)。

    戻り値は `(output_file, gdrive_url)`。呼び出し元(キュー項目単位)が結果の保持先を持つため、
    ここでは `st.session_state` の共有キーへは書き込まない(tc-ops #440: 複数ジョブが並行して
    キューに存在するため、単一の共有キーに書くと後続ジョブに上書きされる)。
    """
    result = job.result
    output_file = build_output_file(Path("output"), diarization_enabled=settings_values["diarization"])
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(result.text)

    gdrive_url: Optional[str] = None
    try:
        if resolution.source_type in {"youtube", "gdrive"}:
            gdrive_url = upload_transcription_result(
                source_type=resolution.source_type,
                original_source=resolution.original_source,
                output_file=output_file,
                metadata=resolution.metadata,
            )
    except Exception as e:
        st.warning(f"Google Driveアップロードに失敗しました: {e}")

    try:
        record_transcription_history(
            result=result,
            resolution=resolution,
            output_file=output_file,
            settings=settings_values,
            gdrive_url=gdrive_url,
        )
    except Exception as e:
        st.warning(f"変換履歴の記録に失敗しました: {e}")

    _cleanup_temp_file(resolution)

    return str(output_file), gdrive_url


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


@st.fragment(run_every="1s")
def _render_queue_and_result() -> None:
    """リアルタイム進捗表示・結果プレビュー・キュー状態表示(設計書§3-3・§3-4、非同期方式は§5、
    tc-ops #440: 複数ジョブの逐次自動処理・キュー状態可視化)。"""
    job_queue = _get_queue()

    current = job_queue.current
    if current is not None and current.job is not None:
        for message in drain_progress(current.job):
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
        st.info("処理中です...")

    finished = list(reversed(job_queue.finished))
    if finished:
        st.subheader("完了済み一覧")
        for item in finished:
            status_label = "完了" if item.state is QueueItemState.DONE else "失敗"
            with st.expander(f"[{status_label}] {item.label}"):
                if item.state is QueueItemState.DONE:
                    _render_result_detail(item)
                else:
                    st.error(f"文字起こしに失敗しました: {item.error_message}")


def _count_history_before(conn: sqlite3.Connection, cutoff_date: date) -> int:
    """`processed_at`が`cutoff_date`より前(境界日当日は含まない)の変換履歴件数を返す
    (WebUI履歴削除機能)。既存の日付絞り込み(`date(processed_at) >= date(?)`等)と同じ
    パターン(SQLiteの`date()`関数で日付部分のみ比較、値自体はPython側で計算)を踏襲する。"""
    row = conn.execute(
        "SELECT COUNT(*) FROM transcription_history WHERE date(processed_at) < date(?)",
        (cutoff_date.isoformat(),),
    ).fetchone()
    return row[0] if row else 0


def _delete_history_before(conn: sqlite3.Connection, cutoff_date: date) -> int:
    """`processed_at`が`cutoff_date`より前の変換履歴を削除し、実際の削除件数を返す。
    `output/`配下のファイル実体・Google Drive上のファイルは削除しない(要件どおり、DB行のみ)。"""
    cursor = conn.execute(
        "DELETE FROM transcription_history WHERE date(processed_at) < date(?)",
        (cutoff_date.isoformat(),),
    )
    conn.commit()
    return cursor.rowcount


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
            conn = sqlite3.connect(str(DEFAULT_HISTORY_DB_PATH))
            try:
                count = _count_history_before(conn, cutoff)
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
                    conn = sqlite3.connect(str(DEFAULT_HISTORY_DB_PATH))
                    try:
                        deleted = _delete_history_before(conn, confirm["cutoff_date"])
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

    _render_history_cleanup_section()

    conn = sqlite3.connect(str(DEFAULT_HISTORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM transcription_history"
        conditions = []
        params: list = []
        if date_from:
            conditions.append("date(processed_at) >= date(?)")
            params.append(date_from.isoformat())
        if date_to:
            conditions.append("date(processed_at) <= date(?)")
            params.append(date_to.isoformat())
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY processed_at DESC"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    if not rows:
        st.caption("該当する履歴がありません。")
        return

    for row in rows:
        title = row["source_title"] or row["source_original"]
        with st.expander(f"{row['processed_at']} - {title} ({row['model_name']})"):
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


def main() -> None:
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
