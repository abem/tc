"""tests/test_core_nemotron_dispatch.py 専用のStreamlit AppTestハーネス。

webui.py の main() は _warmup_qwen_asr() 等の全体初期化(キュー・履歴DB等)を
伴うため、_render_settings_panel() 単体をAppTest経由で駆動するための
最小スクリプトとして分離する。ウィジェットの戻り値は
st.session_state["_test_settings"] へ格納し、テスト側から検証する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from webui import _render_settings_panel

st.session_state["_test_settings"] = _render_settings_panel()
