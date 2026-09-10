"""
Tests for the `transcription_history_fts` FTS5仮想テーブル(#438 Phase3実装:
キーワード検索)。`ensure_history_table()`が作成する同期トリガー3本(INSERT/UPDATE/DELETE)と、
導入前の既存行に対するrebuildバックフィルを検証する。
"""

import sqlite3

import pytest

from core.cli_workflow import ensure_history_table

_LEGACY_DDL = """
CREATE TABLE transcription_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processed_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_original TEXT NOT NULL,
    source_title TEXT,
    model_name TEXT,
    device TEXT,
    language TEXT,
    diarization_enabled INTEGER,
    include_timestamps INTEGER,
    context_hints_used INTEGER,
    char_count INTEGER,
    duration_sec REAL,
    processing_time_sec REAL,
    failed_chunks INTEGER,
    repeated_chunks INTEGER,
    result_text TEXT,
    output_text_path TEXT,
    gdrive_url TEXT,
    notes TEXT
)
"""


def _insert(conn: sqlite3.Connection, result_text: str, source_title: str = "title") -> int:
    cur = conn.execute(
        "INSERT INTO transcription_history "
        "(processed_at, source_type, source_original, source_title, model_name, device, "
        "char_count, processing_time_sec, result_text, output_text_path) "
        "VALUES ('2026-09-10T00:00:00', 'local', 'dummy.wav', ?, 'test-model', 'cpu', 0, 0.0, ?, 'out.txt')",
        (source_title, result_text),
    )
    conn.commit()
    return cur.lastrowid


def _match_ids(conn: sqlite3.Connection, keyword: str) -> list:
    rows = conn.execute(
        "SELECT rowid FROM transcription_history_fts WHERE transcription_history_fts MATCH ?",
        (f'"{keyword}"',),
    ).fetchall()
    return [row[0] for row in rows]


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "history.db"
    connection = sqlite3.connect(str(db_path))
    yield connection
    connection.close()


class TestFtsRoundtrip:
    def test_insert_is_searchable_via_match(self, conn):
        ensure_history_table(conn)
        row_id = _insert(conn, "これはキーワード検索のテストです")

        assert _match_ids(conn, "キーワード検索") == [row_id]

    def test_update_refreshes_fts_index(self, conn):
        ensure_history_table(conn)
        row_id = _insert(conn, "更新前のテキスト")

        conn.execute(
            "UPDATE transcription_history SET result_text = ? WHERE id = ?",
            ("更新後のテキスト", row_id),
        )
        conn.commit()

        assert _match_ids(conn, "更新前") == []
        assert _match_ids(conn, "更新後") == [row_id]

    def test_delete_removes_from_fts_index(self, conn):
        ensure_history_table(conn)
        row_id = _insert(conn, "削除対象のテキスト")
        assert _match_ids(conn, "削除対象") == [row_id]

        conn.execute("DELETE FROM transcription_history WHERE id = ?", (row_id,))
        conn.commit()

        assert _match_ids(conn, "削除対象") == []

    def test_ensure_history_table_backfills_pre_existing_rows(self, conn):
        """FTS5導入前(レガシーDDL)に登録済みの行が、初回ensure_history_table呼び出しの
        rebuildでバックフィルされ検索可能になることを固定化する。"""
        conn.executescript(_LEGACY_DDL)
        row_id = _insert(conn, "移行前に登録済みのテキスト")

        ensure_history_table(conn)

        assert _match_ids(conn, "移行前") == [row_id]

    def test_ensure_history_table_is_idempotent(self, conn):
        """複数回呼び出してもrebuildの再実行やスキーマ破壊が起きないこと。"""
        ensure_history_table(conn)
        row_id = _insert(conn, "冪等性確認用テキスト")
        ensure_history_table(conn)
        ensure_history_table(conn)

        assert _match_ids(conn, "冪等性確認") == [row_id]
