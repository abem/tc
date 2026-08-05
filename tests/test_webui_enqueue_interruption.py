"""
特性テスト(characterization test): tc-ops #440是正2「投入(enqueue)がキューに反映されず消える」現象。

診断ログによる実機再現(作から計への作業完了報告_WebUIジョブキュー処理化診断ログ追加_20260805.md)で
確認したとおり、Streamlitは`st.foo`呼び出し(`_resolve_input()`内部の`on_status=st.write`等、
および`st.spinner`ブロックの`__exit__`)を暗黙のyield pointとして扱い、他の操作(2件目のボタン
クリック)由来のRerunリクエストが保留中であれば、その場で`RerunException`
(`streamlit.runtime.scriptrunner.exceptions.RerunException`、`BaseException`派生、
`except Exception`では捕捉不可)を送出してスクリプト全体を中断する。

このテストは、`_resolve_input()`呼び出し中に`BaseException`派生の例外が発生した場合、
`_enqueue_job()`が`_get_queue().enqueue()`まで到達せず、当該投入がキューに一切残らないという
「現在の(未是正の)挙動」を機械的に固定化する。**是正実装(次チケット)でこの挙動が変わったら、
このテストのアサーションを反転させること**(割り込みが発生しても投入が失われない、または
再試行される、等の是正後挙動を検証する形へ更新する)。
"""

from unittest.mock import patch

import pytest


class _SimulatedRerunInterrupt(BaseException):
    """Streamlitの`RerunException`と同じ性質(`BaseException`派生、`except Exception`で捕捉
    不可)を持つ軽量ダミー。本物の`RerunException`は`RerunData`という内部専用オブジェクトを
    要求するため、Streamlit内部APIへの依存を増やさずに性質だけを再現する
    (予備調査完了報告1-3節の設計方針どおり)。"""


class TestEnqueueJobInterruption:
    def test_interruption_during_resolve_input_leaves_queue_unchanged(self):
        """`_resolve_input()`実行中にBaseException派生の例外で中断された場合、
        `_get_queue()`に新規`QueueItem`が一切追加されないことを固定化する。"""
        import webui

        job_queue_before = webui._get_queue()
        items_before = list(job_queue_before.items)

        form_values = {"source_url": "https://www.youtube.com/watch?v=dummy", "uploaded_file": None}
        settings_values = {
            "model": "Qwen/Qwen3-ASR-1.7B",
            "device": "auto",
            "language": None,
            "diarization": False,
            "include_timestamps": False,
        }

        with patch("webui._resolve_input", side_effect=_SimulatedRerunInterrupt()):
            with pytest.raises(_SimulatedRerunInterrupt):
                webui._enqueue_job(form_values, settings_values, "")

        job_queue_after = webui._get_queue()
        assert job_queue_after is job_queue_before
        assert list(job_queue_after.items) == items_before

    def test_interruption_propagates_uncaught(self):
        """`_enqueue_job()`内にBaseException派生例外を捕捉するtry/exceptが存在しないこと
        (=RerunExceptionが握りつぶされずStreamlitのスクリプトランナーまで正しく伝播すること)
        を確認する。上記テストの`pytest.raises`が実質的に同じ性質を検証しているが、
        「例外が発生しても投入が消えるだけで、握りつぶされて処理が続行するわけではない」
        という区別を明示的に固定化するため独立したテストとして残す。"""
        import webui

        with patch("webui._resolve_input", side_effect=_SimulatedRerunInterrupt()):
            with pytest.raises(_SimulatedRerunInterrupt):
                webui._enqueue_job(
                    {"source_url": "https://www.youtube.com/watch?v=dummy2", "uploaded_file": None},
                    {
                        "model": "Qwen/Qwen3-ASR-1.7B",
                        "device": "auto",
                        "language": None,
                        "diarization": False,
                        "include_timestamps": False,
                    },
                    "",
                )
