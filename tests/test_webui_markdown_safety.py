"""画面(Streamlit)は st.warning / st.info / st.write / st.caption / st.success / st.error を Markdown として描画する。

外部由来の文字列(エラー文・ファイル名・URL・タイトル)にリンクや装飾が含まれていても、
文字として表示させる(偽のリンクで利用者を誘導させない)。 (tc-ops #578 独立レビュー指摘)
"""

import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import webui
from core.utils import markdown_safe
from core.webui_workflow import QueueItemState

EVIL = "[click](http://evil.example) **bold** :red[x] `code` <b>x</b> ~~s~~ | a\nline2"
# エスケープされていない Markdown の記号
UNSAFE = re.compile(r"(?<!\\)[\[\]*_`<>|~]|(?<!\\):[a-z]+\[")


def _texts(mock):
    out = []
    for call in mock.mock_calls:
        for arg in list(call.args) + list(call.kwargs.values()):
            if isinstance(arg, str):
                out.append(arg)
    return out


def _assert_safe(mock):
    texts = _texts(mock)
    assert texts
    for text in texts:
        assert not UNSAFE.search(text), text
        assert "\n" not in text, text


def test_markdown_safe_escapes_markup_and_joins_lines():
    out = markdown_safe(EVIL)
    assert not UNSAFE.search(out) and "\n" not in out
    plain = out.replace("\\", "")
    assert "click" in plain and "evil.example" in plain  # 内容は残る(見た目は同じ)


def test_markdown_safe_keeps_plain_japanese_readable():
    assert markdown_safe("会議の録音") == "会議の録音"


def test_markdown_safe_truncates():
    assert len(markdown_safe("あ" * 1000, limit=50)) <= 50


@pytest.fixture
def st_mock(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr(webui, "st", m)
    return m


def test_cleanup_warning_is_rendered_safely(st_mock, monkeypatch):
    monkeypatch.setattr(webui, "cleanup_input_audio", lambda resolution: EVIL)
    webui._cleanup_temp_file(SimpleNamespace())
    _assert_safe(st_mock)


def test_result_detail_renders_path_and_url_safely(st_mock):
    result = SimpleNamespace(metadata={}, text="t", segments=[])
    item = SimpleNamespace(
        job=SimpleNamespace(result=result), output_file=EVIL, gdrive_url=EVIL, item_id=1, settings={}
    )
    webui._render_result_detail(item)
    _assert_safe(st_mock.success)
    _assert_safe(st_mock.write)


def test_google_drive_link_stays_clickable(st_mock):
    url = "https://drive.google.com/file/d/ABC_def-123/view?usp=sharing"
    result = SimpleNamespace(metadata={}, text="t", segments=[])
    item = SimpleNamespace(job=SimpleNamespace(result=result), output_file="o.txt", gdrive_url=url, item_id=1, settings={})
    webui._render_result_detail(item)
    assert any(f"]({url})" in t for t in _texts(st_mock.write))


def test_progress_text_is_rendered_safely(st_mock):
    item = SimpleNamespace(progress=None, progress_text=EVIL)
    webui._render_item_progress(item, since=0.0, idle_text="x")
    _assert_safe(st_mock.info)

    st_mock.reset_mock()
    item = SimpleNamespace(progress=0.5, progress_text=EVIL)
    webui._render_item_progress(item, since=0.0, idle_text="x")
    _assert_safe(st_mock.progress)


def test_finished_item_label_is_safe():
    item = SimpleNamespace(
        state=QueueItemState.DONE, item_id=1, label=EVIL, finished_at=None
    )
    label = webui._format_finished_item_label(item)
    assert not UNSAFE.search(label.replace("[完了]", "").replace("[失敗]", "")), label
    assert "\n" not in label


@pytest.mark.parametrize("lead", ["- item", "+ item", "1. item", "12) item"])
def test_markdown_safe_neutralizes_list_markers_at_line_start(lead):
    out = markdown_safe(lead)
    assert out.startswith(("\\-", "\\+", "1\\.", "12\\)")), out


def test_markdown_safe_leaves_unrelated_symbols_alone():
    assert markdown_safe("ダウンロード中 40%/100") == "ダウンロード中 40%/100"
