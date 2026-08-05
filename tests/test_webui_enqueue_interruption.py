"""
特性テスト(characterization test): tc-ops #440是正3「投入(enqueue)がキューに反映されず消える」
現象への是正の固定化(初版のアサーションを反転)。

is正前(tc-ops #440是正2で確定): `_resolve_input()`実行中にStreamlitの`RerunException`
(`BaseException`派生、`except Exception`では捕捉不可)でスクリプトが中断されると、
`_enqueue_job()`が`_get_queue().enqueue()`まで到達せず、投入内容が消失していた。

is正後(tc-ops #440是正3): `_enqueue_job()`は入力解決(ダウンロード等)を待たず、即座に
`QueueItem`を`RESOLVING`状態でキューへ追加してから返る。この処理は`st.foo`呼び出しを
一切含まないため、Streamlitのスクリプト中断(RerunException)を原理的に受けない。ダウンロード
自体はバックグラウンドスレッドで非同期に行われ、その完了/失敗は`QueueItem`の状態遷移
(`RESOLVING`→`QUEUED`/`FAILED`)としてのみ反映される(消失しない)。

注意: `unittest.mock.patch`は`with`ブロックを抜けると即座に元に戻るため、バックグラウンド
スレッドが実際にモック対象を呼び出すまでは`with`ブロックを抜けないこと(そうしないと、
スレッドがCPUを得たタイミング次第で本物の関数が呼ばれてしまう競合状態になる)。
"""

import threading
import time
from unittest.mock import patch

from core.webui_workflow import QueueItemState


class _SimulatedInterrupt(BaseException):
    """Streamlitの`RerunException`と同じ性質(`BaseException`派生、`except Exception`で捕捉
    不可)を持つ軽量ダミー。本物の`RerunException`は`RerunData`という内部専用オブジェクトを
    要求するため、Streamlit内部APIへの依存を増やさずに性質だけを再現する。"""


def _settings():
    return {
        "model": "Qwen/Qwen3-ASR-1.7B",
        "device": "auto",
        "language": None,
        "include_timestamps": False,
    }


def _new_items_since(job_queue, item_ids_before):
    return [item for item in job_queue.items if item.item_id not in item_ids_before]


class TestEnqueueJobReturnsImmediately:
    def test_enqueue_job_does_not_block_on_resolution(self):
        """`_enqueue_job()`は入力解決(ダウンロード等)の完了を待たず即座に返る
        (st.foo呼び出しを含まないため、RerunExceptionによる中断を原理的に受けない、是正の核心)。"""
        import webui

        call_started = threading.Event()
        release_event = threading.Event()

        def _slow_resolve(form_values, download_dir, on_status):
            call_started.set()
            release_event.wait(timeout=5)
            return None

        form_values = {"source_url": "https://www.youtube.com/watch?v=slow", "uploaded_file": None}

        with patch("webui._resolve_input", side_effect=_slow_resolve):
            start = time.time()
            webui._enqueue_job(form_values, _settings(), "")
            elapsed = time.time() - start
            assert elapsed < 1.0, f"_enqueue_job()が解決処理の完了を待ってブロックした(elapsed={elapsed:.2f}s)"

            assert call_started.wait(timeout=5), "バックグラウンドスレッドがモックを呼び出さなかった"
            release_event.set()
            time.sleep(0.1)  # パッチ有効なうちにバックグラウンドスレッドの後続処理を完了させる


class TestQueueItemSurvivesResolutionInterruption:
    def test_item_is_enqueued_as_resolving_before_resolution_completes(self):
        """`_enqueue_job()`呼び出し直後、解決(ダウンロード)が完了していなくても`QueueItem`が
        `RESOLVING`状態で既にキューに存在する(是正の核心)。"""
        import webui

        call_started = threading.Event()
        release_event = threading.Event()

        def _slow_resolve(form_values, download_dir, on_status):
            call_started.set()
            release_event.wait(timeout=5)
            return None

        job_queue = webui._get_queue()
        ids_before = {item.item_id for item in job_queue.items}

        form_values = {"source_url": "https://www.youtube.com/watch?v=slow2", "uploaded_file": None}

        with patch("webui._resolve_input", side_effect=_slow_resolve):
            webui._enqueue_job(form_values, _settings(), "")

            new_items = _new_items_since(job_queue, ids_before)
            assert len(new_items) == 1
            assert new_items[0].state is QueueItemState.RESOLVING
            assert new_items[0].resolution is None

            assert call_started.wait(timeout=5), "バックグラウンドスレッドがモックを呼び出さなかった"
            release_event.set()
            time.sleep(0.1)

    def test_interruption_during_background_resolution_does_not_remove_item_from_queue(self):
        """バックグラウンドスレッドでの解決(ダウンロード)中に`BaseException`派生の例外
        (`RerunException`と同じ性質)が発生しても、既にキューに追加済みの`QueueItem`は消えず、
        `FAILED`へ遷移するのみである(消失しない、is正前との決定的な違い)。"""
        import webui

        def _interrupted_resolve(form_values, download_dir, on_status):
            raise _SimulatedInterrupt("simulated RerunException-like interruption")

        job_queue = webui._get_queue()
        ids_before = {item.item_id for item in job_queue.items}

        form_values = {"source_url": "https://www.youtube.com/watch?v=interrupted", "uploaded_file": None}

        with patch("webui._resolve_input", side_effect=_interrupted_resolve):
            webui._enqueue_job(form_values, _settings(), "")  # 例外はバックグラウンドに留まり伝播しない

            new_items = _new_items_since(job_queue, ids_before)
            assert len(new_items) == 1
            item = new_items[0]

            for _ in range(50):  # バックグラウンドスレッドの状態遷移完了を待つ(パッチ有効なうちに)
                if item.state is not QueueItemState.RESOLVING:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("バックグラウンドスレッドの完了待ちがタイムアウトした")

        assert item.state is QueueItemState.FAILED
        assert item in job_queue.items  # キューから消えていないことの直接確認
        assert isinstance(item.resolve_error, _SimulatedInterrupt)
