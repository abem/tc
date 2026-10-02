"""core.history(履歴DBの検索・件数・削除)のテスト。一時SQLite DB(本番と同一DDL/FTS)を使う。"""

from datetime import date

import pytest

from core.cli_workflow import ensure_history_table
from core.history import connect_history, count_history_before, delete_history_before, search_history


@pytest.fixture
def conn(tmp_path):
    connection = connect_history(tmp_path / "history.db")
    ensure_history_table(connection)
    yield connection
    connection.close()


def _insert(conn, processed_at: str, text: str = "本文") -> None:
    conn.execute(
        "INSERT INTO transcription_history (processed_at, source_type, source_original, model_name, "
        "device, char_count, processing_time_sec, result_text, output_text_path) "
        "VALUES (?, 'local', 'dummy.wav', 'm', 'cpu', 1, 1.0, ?, 'out.txt')",
        (processed_at, text),
    )
    conn.commit()


def test_connect_history_returns_row_accessible_by_name(conn):
    _insert(conn, "2026-01-01T00:00:00")
    row = conn.execute("SELECT * FROM transcription_history").fetchone()
    assert row["source_type"] == "local"


def test_count_excludes_boundary_day(conn):
    _insert(conn, "2026-01-09T23:59:59")
    _insert(conn, "2026-01-10T00:00:00")
    _insert(conn, "2026-01-11T00:00:00")
    assert count_history_before(conn, date(2026, 1, 10)) == 1


def test_count_empty_is_zero(conn):
    assert count_history_before(conn, date(2026, 1, 10)) == 0


def test_delete_removes_only_older_and_returns_count(conn):
    _insert(conn, "2026-01-08T10:00:00")
    _insert(conn, "2026-01-09T10:00:00")
    _insert(conn, "2026-01-10T10:00:00")
    assert delete_history_before(conn, date(2026, 1, 10)) == 2
    remaining = conn.execute("SELECT processed_at FROM transcription_history").fetchall()
    assert [r[0] for r in remaining] == ["2026-01-10T10:00:00"]


def test_delete_also_cleans_fts_via_trigger(conn):
    _insert(conn, "2026-01-01T10:00:00", "古い履歴テキスト")
    delete_history_before(conn, date(2026, 1, 10))
    assert search_history(conn, keyword="古い履歴") == []


def test_search_no_filter_orders_by_processed_at_desc(conn):
    _insert(conn, "2026-01-01T10:00:00")
    _insert(conn, "2026-01-03T10:00:00")
    _insert(conn, "2026-01-02T10:00:00")
    rows = search_history(conn)
    assert [r["processed_at"] for r in rows] == [
        "2026-01-03T10:00:00",
        "2026-01-02T10:00:00",
        "2026-01-01T10:00:00",
    ]


def test_search_date_range_is_inclusive(conn):
    for d in ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"):
        _insert(conn, f"{d}T12:00:00")
    rows = search_history(conn, date_from=date(2026, 1, 2), date_to=date(2026, 1, 3))
    assert sorted(r["processed_at"][:10] for r in rows) == ["2026-01-02", "2026-01-03"]


def test_search_keyword_matches_fts_and_combines_with_date(conn):
    _insert(conn, "2026-01-01T10:00:00", "今日の会議の議事録です")
    _insert(conn, "2026-01-05T10:00:00", "今日の会議の議事録です")
    _insert(conn, "2026-01-05T11:00:00", "全く別の内容")
    assert len(search_history(conn, keyword="会議の議事")) == 2
    rows = search_history(conn, date_from=date(2026, 1, 4), keyword="会議の議事")
    assert len(rows) == 1 and rows[0]["processed_at"].startswith("2026-01-05")


def test_search_keyword_with_double_quote_does_not_error(conn):
    _insert(conn, "2026-01-01T10:00:00", "引用 abc def")
    assert isinstance(search_history(conn, keyword='"abc'), list)
