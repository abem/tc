"""
Shared workflow helpers for CLI entry points.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from core.cli_common import build_output_file, detect_input_type, upload_text_to_gdrive_sibling

if TYPE_CHECKING:
    from core.transcription_interface import TranscriptionResult

StatusCallback = Callable[[str], None]

logger = logging.getLogger(__name__)


@dataclass
class InputResolution:
    source_type: str
    original_source: str
    local_audio_path: str
    is_temp_file: bool
    metadata: Optional[Dict[str, Any]]
    youtube_handler: Optional[Any]  # YouTubeClient

    @property
    def needs_cleanup(self) -> bool:
        """処理終了時に `local_audio_path` を削除すべきか(D5)。

        yt-dlp が作った音声(youtube/twitter)と Google Drive からダウンロードした音声は
        一時ファイルなので削除対象。`GDriveClient.download()` は常に
        `NamedTemporaryFile(delete=False)` へ保存するが、`resolve_input_audio` は
        gdrive で `is_temp_file=False` を返すため、source_type でも判定する。
        ローカルファイル入力は削除しない。
        """
        return self.is_temp_file or self.source_type == "gdrive"


def cleanup_input_audio(resolution: "InputResolution") -> Optional[str]:
    """`resolution.needs_cleanup` のとき一時音声ファイルを削除する(D5)。

    成功・失敗・中断いずれの経路でも呼べる。削除に失敗しても例外は出さず、
    警告メッセージを返す(呼び出し側が表示する。core に UI は持ち込まない)。
    正常に削除した場合・対象外・既に無い場合は None。
    """
    if not resolution.needs_cleanup:
        return None
    path = resolution.local_audio_path
    try:
        if not os.path.exists(path):
            return None
        if resolution.youtube_handler:
            resolution.youtube_handler.cleanup_temp_file(path)
        else:
            os.remove(path)
            logger.info("一時ファイルを削除: %s", path)
    except Exception as e:
        message = f"一時ファイルの削除に失敗しました: {e}"
        logger.warning(message)
        return message
    return None


def format_mmss(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def format_transcript_text(result: "TranscriptionResult") -> str:
    """保存用テキストを作る(D4)。

    `result.metadata["timestamps_included"]` が真で `result.segments` があるときだけ、
    各セグメント先頭に `[MM:SS] ` を付けて 1 行 1 セグメントにする。それ以外は
    `result.text` をそのまま返す。
    """
    timestamps_included = bool((result.metadata or {}).get("timestamps_included", False))
    if timestamps_included and result.segments:
        return "\n".join(f"[{format_mmss(seg.start)}] {seg.text}" for seg in result.segments)
    return result.text


def save_transcription_text(result: "TranscriptionResult", output_dir: Path) -> Path:
    """文字起こし結果をタイムスタンプ付きファイル名で保存し、パスを返す(D4)。"""
    output_path = build_output_file(Path(output_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(format_transcript_text(result), encoding="utf-8")
    logger.info("結果を保存: %s", output_path)
    return output_path


def resolve_input_audio(
    source: str,
    output_dir: Path,
    *,
    ensure_yt_dlp: bool = False,
    on_status: Optional[StatusCallback] = None,
) -> InputResolution:
    """Resolve input source to a local audio path."""
    detected = detect_input_type(source)
    source_type = detected["type"]

    def status(message: str) -> None:
        if on_status:
            on_status(message)

    if source_type in ("youtube", "twitter"):
        status("YouTube URLを検出" if source_type == "youtube" else "X(Twitter)動画URLを検出")
        from handlers.youtube import YouTubeClient, check_yt_dlp_installed, install_yt_dlp

        if ensure_yt_dlp and not check_yt_dlp_installed():
            status("yt-dlpがインストールされていないためインストールを試行します")
            install_yt_dlp()

        youtube_handler = YouTubeClient(output_dir=str(output_dir))
        if on_status:
            local_audio_path, metadata = youtube_handler.download_audio(source, progress_callback=on_status)
        else:
            local_audio_path, metadata = youtube_handler.download_audio(source)
        return InputResolution(
            source_type=source_type,
            original_source=source,
            local_audio_path=local_audio_path,
            is_temp_file=True,
            metadata=metadata,
            youtube_handler=youtube_handler,
        )

    if source_type == "gdrive":
        status("Google Drive URLを検出、ダウンロードを開始")
        from handlers.gdrive import GDriveClient

        client = GDriveClient()
        local_audio_path = str(client.download(source))
        return InputResolution(
            source_type="gdrive",
            original_source=source,
            local_audio_path=local_audio_path,
            is_temp_file=False,
            metadata=None,
            youtube_handler=None,
        )

    if source_type == "local":
        return InputResolution(
            source_type="local",
            original_source=source,
            local_audio_path=detected["source"],
            is_temp_file=False,
            metadata=None,
            youtube_handler=None,
        )

    raise ValueError(f"入力を認識できません: {source}")


def upload_transcription_result(
    *,
    source_type: str,
    original_source: str,
    output_file: Path,
    metadata: Optional[Dict[str, Any]] = None,
    folder_id: Optional[str] = None,
) -> Optional[str]:
    """Upload transcription result based on source type and return URL if available.

    Args:
        source_type: Type of source (youtube, gdrive, local)
        original_source: Original source URL or path
        output_file: Path to output file
        metadata: YouTube metadata (required for YouTube sources)
        folder_id: Override folder ID for upload destination

    Returns:
        File URL if successful, None otherwise
    """
    if source_type == "youtube":
        if not metadata:
            return None
        from handlers.gdrive import GDriveClient

        gdrive_client = GDriveClient()
        upload_result = gdrive_client.upload_youtube_transcription(str(output_file), metadata)
        if upload_result:
            return upload_result.get("file_url")
        return None

    if source_type == "gdrive":
        return upload_text_to_gdrive_sibling(output_file, original_source, override_folder_id=folder_id)

    return None


# 変換履歴DB(設計書: 作から計への設計書_変換履歴DB設計_20260806.md §3 DDL準拠)
_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS transcription_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processed_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_original TEXT NOT NULL,
    source_title TEXT,
    model_name TEXT NOT NULL,
    device TEXT NOT NULL,
    language TEXT,
    diarization_enabled INTEGER NOT NULL DEFAULT 0,
    include_timestamps INTEGER NOT NULL DEFAULT 0,
    context_hints_used INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL,
    duration_sec REAL,
    processing_time_sec REAL NOT NULL,
    failed_chunks INTEGER NOT NULL DEFAULT 0,
    repeated_chunks INTEGER NOT NULL DEFAULT 0,
    result_text TEXT NOT NULL,
    output_text_path TEXT NOT NULL,
    gdrive_url TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_processed_at ON transcription_history(processed_at);
CREATE INDEX IF NOT EXISTS idx_history_source_type ON transcription_history(source_type);

-- キーワード検索(Phase3): external contentのFTS5仮想テーブル。
-- 本体テーブルへのINSERT/UPDATE/DELETEは下記トリガーで同期する(FTS5公式レシピ準拠)。
-- tokenize='trigram': 既定のunicode61トークナイザは分かち書きされていない日本語を
-- 空白の無い1トークンとして扱うため部分一致検索が機能しない(実測確認済み)。
-- trigram(3文字連続n-gram、SQLite 3.34+)であれば分かち書き不要で部分一致検索できる。
CREATE VIRTUAL TABLE IF NOT EXISTS transcription_history_fts USING fts5(
    source_title, source_original, result_text, notes,
    content='transcription_history', content_rowid='id',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS transcription_history_ai AFTER INSERT ON transcription_history BEGIN
    INSERT INTO transcription_history_fts(rowid, source_title, source_original, result_text, notes)
    VALUES (new.id, new.source_title, new.source_original, new.result_text, new.notes);
END;

CREATE TRIGGER IF NOT EXISTS transcription_history_ad AFTER DELETE ON transcription_history BEGIN
    INSERT INTO transcription_history_fts(transcription_history_fts, rowid, source_title, source_original, result_text, notes)
    VALUES ('delete', old.id, old.source_title, old.source_original, old.result_text, old.notes);
END;

CREATE TRIGGER IF NOT EXISTS transcription_history_au AFTER UPDATE ON transcription_history BEGIN
    INSERT INTO transcription_history_fts(transcription_history_fts, rowid, source_title, source_original, result_text, notes)
    VALUES ('delete', old.id, old.source_title, old.source_original, old.result_text, old.notes);
    INSERT INTO transcription_history_fts(rowid, source_title, source_original, result_text, notes)
    VALUES (new.id, new.source_title, new.source_original, new.result_text, new.notes);
END;
"""

DEFAULT_HISTORY_DB_PATH = Path("output/history.db")


def ensure_history_table(conn: sqlite3.Connection) -> None:
    """`transcription_history` テーブル(未作成時は自動作成)。DDLは設計書§3準拠。

    FTS5仮想テーブル(`transcription_history_fts`)を初めて作成する際は、
    導入前に登録済みの既存行がトリガーの対象外のため一度だけrebuildでバックフィルする。
    """
    fts_existed = (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='transcription_history_fts'"
        ).fetchone()[0]
        > 0
    )
    conn.executescript(_HISTORY_DDL)
    if not fts_existed:
        conn.execute("INSERT INTO transcription_history_fts(transcription_history_fts) VALUES ('rebuild')")
        conn.commit()


def record_transcription_history(
    *,
    result: "TranscriptionResult",
    resolution: InputResolution,
    output_file: Path,
    settings: Dict[str, Any],
    gdrive_url: Optional[str] = None,
    db_path: Path = DEFAULT_HISTORY_DB_PATH,
) -> None:
    """変換履歴をSQLiteへ記録する(設計書§5-2準拠)。

    `UnifiedTranscriber.transcribe()` は変更しないため、音源種別・出力ファイルパス・
    アップロードURLは呼び出し元(各CLIエントリポイントの保存処理)から受け取る。
    呼び出し元は本関数を独立した try/except で囲み、失敗を既存ワークフローへ
    伝播させないこと(設計書§6、既存CLIワークフローへの無影響要件)。
    """
    metadata = result.metadata or {}
    source_title = resolution.metadata.get("title") if resolution.metadata else None
    context_hints_used = bool(settings.get("context") or "")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_history_table(conn)
        conn.execute(
            """
            INSERT INTO transcription_history (
                processed_at, source_type, source_original, source_title,
                model_name, device, language, diarization_enabled,
                include_timestamps, context_hints_used, char_count,
                duration_sec, processing_time_sec, failed_chunks,
                repeated_chunks, result_text, output_text_path, gdrive_url, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                resolution.source_type,
                resolution.original_source,
                source_title,
                result.model_name,
                settings.get("device") or "",
                result.language,
                1 if settings.get("diarization", False) else 0,
                1 if settings.get("include_timestamps") else 0,
                1 if context_hints_used else 0,
                len(result.text),
                result.duration,
                result.processing_time,
                metadata.get("failed_chunks", 0),
                metadata.get("repeated_chunks", 0),
                result.text,
                str(output_file),
                gdrive_url,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()
