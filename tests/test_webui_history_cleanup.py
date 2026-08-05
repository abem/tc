"""
Tests for webui._count_history_before() / _delete_history_before()
(2026-08-05、WebUI履歴削除機能: N日より前の変換履歴を一括削除)。

`webui.py`自体はStreamlit依存のため直接ユニットテスト対象に含めない(既存方針を踏襲)。
削除対象を決定するSQLロジック(`_count_history_before`/`_delete_history_before`、いずれも
`sqlite3.Connection`を直接受け取る純粋関数)を、一時SQLite DB(`transcription_history`と
同一DDL)に対して検証する。
"""

import sqlite3
from datetime import date, timedelta

import pytest

from webui import _count_history_before, _delete_history_before

_DDL = """
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
    output_file TEXT,
    gdrive_url TEXT,
    result_text TEXT
)
"""


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "history.db"
    connection = sqlite3.connect(str(db_path))
    connection.execute(_DDL)
    connection.commit()
    yield connection
    connection.close()


def _insert(conn, processed_at: str) -> None:
    conn.execute(
        "INSERT INTO transcription_history (processed_at, source_type, source_original) "
        "VALUES (?, 'local', 'dummy.wav')",
        (processed_at,),
    )
    conn.commit()


class TestCountHistoryBefore:
    def test_counts_only_rows_strictly_before_cutoff(self, conn):
        today = date.today()
        _insert(conn, (today - timedelta(days=31)).isoformat() + "T00:00:00")  # 対象
        _insert(conn, (today - timedelta(days=30)).isoformat() + "T00:00:00")  # 境界日(対象外)
        _insert(conn, (today - timedelta(days=29)).isoformat() + "T00:00:00")  # 対象外
        _insert(conn, today.isoformat() + "T12:00:00")  # 対象外(直近)

        cutoff = today - timedelta(days=30)
        assert _count_history_before(conn, cutoff) == 1

    def test_zero_when_no_rows_match(self, conn):
        today = date.today()
        _insert(conn, today.isoformat() + "T00:00:00")

        cutoff = today - timedelta(days=30)
        assert _count_history_before(conn, cutoff) == 0

    def test_count_does_not_delete_rows(self, conn):
        """①対象件数の確認だけでは実削除が行われないことを固定化する(誤操作防止要件)。"""
        today = date.today()
        _insert(conn, (today - timedelta(days=100)).isoformat() + "T00:00:00")

        cutoff = today - timedelta(days=30)
        _count_history_before(conn, cutoff)

        remaining = conn.execute("SELECT COUNT(*) FROM transcription_history").fetchone()[0]
        assert remaining == 1


class TestDeleteHistoryBefore:
    def test_delete_removes_matching_rows_and_returns_count(self, conn):
        today = date.today()
        _insert(conn, (today - timedelta(days=100)).isoformat() + "T00:00:00")
        _insert(conn, (today - timedelta(days=50)).isoformat() + "T00:00:00")
        _insert(conn, today.isoformat() + "T00:00:00")  # 削除対象外

        cutoff = today - timedelta(days=30)
        deleted = _delete_history_before(conn, cutoff)

        assert deleted == 2
        remaining = conn.execute("SELECT COUNT(*) FROM transcription_history").fetchone()[0]
        assert remaining == 1

    def test_delete_is_idempotent_when_nothing_matches(self, conn):
        today = date.today()
        _insert(conn, today.isoformat() + "T00:00:00")

        cutoff = today - timedelta(days=30)
        deleted = _delete_history_before(conn, cutoff)

        assert deleted == 0
        remaining = conn.execute("SELECT COUNT(*) FROM transcription_history").fetchone()[0]
        assert remaining == 1

    def test_count_before_delete_matches_actual_deleted_count(self, conn):
        """①確認時のカウントと②削除時の実削除件数が同一cutoff_dateを使う限り一致すること
        (session_state設計のズレ対策、予備調査1-4節)を固定化する。"""
        today = date.today()
        for days_ago in (40, 45, 60, 90):
            _insert(conn, (today - timedelta(days=days_ago)).isoformat() + "T00:00:00")
        _insert(conn, today.isoformat() + "T00:00:00")

        cutoff = today - timedelta(days=30)
        counted = _count_history_before(conn, cutoff)
        deleted = _delete_history_before(conn, cutoff)

        assert counted == deleted == 4
