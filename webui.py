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
from pathlib import Path
from typing import Any, Dict, Optional

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


def _load_config() -> None:
    if "config_loaded" not in st.session_state:
        try:
            UnifiedConfig.load("config/config.yaml")
        except Exception:
            pass
        st.session_state["config_loaded"] = True


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


def _resolve_input(form_values: Dict[str, Any]) -> Optional[InputResolution]:
    if form_values["source_url"]:
        return resolve_input_audio(
            form_values["source_url"], Path("output"), ensure_yt_dlp=True, on_status=st.write
        )
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


def _enqueue_job(form_values: Dict[str, Any], settings_values: Dict[str, Any], context_value: str) -> None:
    """入力を解決しキューへ追加する(現行ジョブが処理中でも追加投入できる。要件4-2-1)。"""
    resolution = _resolve_input(form_values)
    if resolution is None:
        st.error("URLを入力するか、ファイルをアップロードしてください。")
        return

    # 解決済みdevice・context_valueをjob_settingsへ書き戻す(record_transcription_history()に
    # 渡る際、未解決の"auto"のままcontext_hints_used=0固定で記録されるのを防ぐため。査sa指摘是正)。
    job_settings = dict(settings_values)
    job_settings["device"] = resolve_device(settings_values["device"])
    job_settings["context"] = context_value

    label = form_values["source_url"] or (
        form_values["uploaded_file"].name if form_values["uploaded_file"] is not None else resolution.original_source
    )
    _get_queue().enqueue(label=label, resolution=resolution, settings=job_settings)


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
    st.title("Transcribe Audio WebUI (プロトタイプ)")

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
