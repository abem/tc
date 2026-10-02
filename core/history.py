"""履歴DB(`transcription_history`)の検索・件数・削除。

UI(streamlit)に依存しない純粋な関数群。DDL・FTSトリガーは `core.cli_workflow`
(`ensure_history_table`)が持つ。ここでは変更しない。
"""

import sqlite3
from datetime import date
from pathlib import Path


def connect_history(db_path: Path | str) -> sqlite3.Connection:
    """履歴DBへ接続する(カラム名でアクセスできる `sqlite3.Row` 付き)。呼び出し側がcloseする。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def search_history(
    conn: sqlite3.Connection,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str = "",
) -> list[sqlite3.Row]:
    """履歴を `processed_at` 降順で返す。日付は両端を含み、キーワードはFTS5で検索する。"""
    query = "SELECT * FROM transcription_history"
    conditions = []
    params: list = []
    if date_from:
        conditions.append("date(processed_at) >= date(?)")
        params.append(date_from.isoformat())
    if date_to:
        conditions.append("date(processed_at) <= date(?)")
        params.append(date_to.isoformat())
    if keyword:
        # フレーズ全体を1トークン列として扱う(MATCH演算子の誤解釈を避けるため" "で囲む)。
        escaped_keyword = keyword.replace('"', '""')
        conditions.append(
            "id IN (SELECT rowid FROM transcription_history_fts WHERE transcription_history_fts MATCH ?)"
        )
        params.append(f'"{escaped_keyword}"')
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY processed_at DESC"
    return conn.execute(query, params).fetchall()


def count_history_before(conn: sqlite3.Connection, cutoff_date: date) -> int:
    """`processed_at`が`cutoff_date`より前(境界日当日は含まない)の変換履歴件数を返す。
    SQLiteの`date()`関数で日付部分のみ比較し、値自体はPython側で計算する。"""
    row = conn.execute(
        "SELECT COUNT(*) FROM transcription_history WHERE date(processed_at) < date(?)",
        (cutoff_date.isoformat(),),
    ).fetchone()
    return row[0] if row else 0


def delete_history_before(conn: sqlite3.Connection, cutoff_date: date) -> int:
    """`processed_at`が`cutoff_date`より前の変換履歴を削除し、実際の削除件数を返す。
    `output/`配下のファイル実体・Google Drive上のファイルは削除しない(DB行のみ)。"""
    cursor = conn.execute(
        "DELETE FROM transcription_history WHERE date(processed_at) < date(?)",
        (cutoff_date.isoformat(),),
    )
    conn.commit()
    return cursor.rowcount
