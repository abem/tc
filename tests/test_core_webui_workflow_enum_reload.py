"""
QueueItemState のモジュール再読込耐性テスト(tc-ops #548、2026-09-27是正)。

## 背景(本番不具合)

実運用でWebUI #7(Nemotron、ja、cuda)を操作したところ、画面上は「失敗: None」と
表示されたが、ログはPROCESSING→DONE、940字、Drive履歴#75への記録も成功していた
(実際には成功していたのに失敗表示になった)。

原因: `webui.py`・`core/webui_workflow.py`内の`item.state is QueueItemState.DONE`
という同一性比較(`is`演算子)が、Streamlitの自動リロード(作業ツリーへの編集を検知して
モジュールを再読込する挙動)に耐えられなかった。モジュールが再読込されると
`QueueItemState`は別クラスオブジェクトとして再定義され、リロード前に生成された
`QueueItem.state`(旧クラスのメンバー)と、リロード後に評価される`QueueItemState.DONE`
(新クラスのメンバー)は、値が同じ"done"でも`is`比較では一致しなくなる。

是正: `QueueItemState(Enum)` → `QueueItemState(str, Enum)`とし、全ての`is`比較を
`==`へ置換した。`str, Enum`の`__eq__`は文字列値としての比較にフォールバックするため、
モジュール再読込後も一致し続ける。

## テスト実装上の注意(重要、教訓)

当初`importlib.reload(core.webui_workflow)`で実際にモジュールを再読込するテストを
書いたが、これは`sys.modules["core.webui_workflow"]`を書き換えてしまい、既に
`from core.webui_workflow import QueueItemState`していた**他のテストファイル**
(`test_core_webui_workflow_queue.py`等)が保持する参照が古いクラスオブジェクトの
ままになり、新規に生成される`QueueItem.state`(reload後の新クラス)との`is`比較で
食い違いが発生してpytest全体で8件が新規に失敗する事故を起こした(本ファイルの
作成時に実機で再現・原因確定し、下記の独立ロード方式へ修正した)。

教訓: 共有される`sys.modules`を書き換える`importlib.reload()`は、同一pytest
プロセス内の他テストへ波及する副作用を持つため、モジュール再読込を模する場合は
`importlib.util.spec_from_file_location`で**別名の独立したモジュールコピー**を
作り、`sys.modules`上の正規のエントリには一切触れない方式を用いること。
"""
import importlib.util
import sys
from pathlib import Path

from core.webui_workflow import QueueItemState

_INDEPENDENT_MODULE_NAME = "webui_workflow_reload_copy_for_test"


def _load_independent_copy():
    """core/webui_workflow.py を、sys.modules上の正規エントリ(`core.webui_workflow`)
    とは独立した別名のモジュールとして読み込む。Streamlitの自動リロードで
    `QueueItemState`が別クラスオブジェクトとして再定義される状況を、
    他のテストファイルの参照を一切汚染せずに再現する。

    別名(`_INDEPENDENT_MODULE_NAME`)は`sys.modules`へ登録する必要がある
    (`QueueItem`がdataclassであり、dataclassesの内部実装が型解決のため
    `sys.modules[cls.__module__].__dict__`を参照するため。未登録のままだと
    `AttributeError: 'NoneType' object has no attribute '__dict__'`になる)。
    この別名は他のどのテストファイルも参照しないため、登録したままでも
    既存の`core.webui_workflow`(正規のsys.modulesエントリ)には一切影響しない。
    """
    path = Path(__file__).parent.parent / "core" / "webui_workflow.py"
    spec = importlib.util.spec_from_file_location(_INDEPENDENT_MODULE_NAME, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_INDEPENDENT_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


class TestQueueItemStateStrMixin:
    """str, Enumミックスインの基本的性質の確認。"""

    def test_is_str_subclass(self):
        assert isinstance(QueueItemState.DONE, str)

    def test_equals_its_string_value(self):
        assert QueueItemState.DONE == "done"
        assert QueueItemState.FAILED == "failed"
        assert QueueItemState.PROCESSING == "processing"
        assert QueueItemState.QUEUED == "queued"
        assert QueueItemState.RESOLVING == "resolving"


class TestModuleReloadEquality:
    """独立ロードした「別クラスオブジェクト」のQueueItemStateが、==で本来の
    QueueItemStateと一致し続けることを検証する(本番不具合の再現条件相当)。"""

    def test_independently_loaded_member_equals_original_via_string_value(self):
        reloaded_module = _load_independent_copy()
        reloaded_done = reloaded_module.QueueItemState.DONE

        # 前提の確認: 独立ロードなので、正規の QueueItemState.DONE とは
        # 別クラスオブジェクトのメンバーになっている。
        assert QueueItemState.DONE is not reloaded_done, (
            "前提の再現に失敗: 独立ロードしたモジュールが別クラスオブジェクトになっていない"
        )

        # 是正後(str, Enum・==比較)は、文字列値としての比較にフォールバックし一致する。
        assert QueueItemState.DONE == reloaded_done
        assert reloaded_done == "done"

    def test_membership_check_survives_independent_reload(self):
        """`item.state in (QueueItemState.DONE, QueueItemState.FAILED)`のような
        membership比較(finishedプロパティで使用)も、独立ロードされた別クラス
        オブジェクトの値と引き続き一致することを確認する。"""
        reloaded_module = _load_independent_copy()
        new_done = reloaded_module.QueueItemState.DONE
        new_failed = reloaded_module.QueueItemState.FAILED

        assert QueueItemState.DONE in (new_done, new_failed)
