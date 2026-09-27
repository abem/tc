"""
core/__init__.py のpytest実行時ログ分離ガードの回帰テスト(tc-ops #548、2026-09-27是正)。

## 背景

`core/__init__.py`は`import core`されるだけで、無条件に
`UnifiedLogger.configure(log_file="logs/transcription.log", ...)`を実行する
副作用を持っていた。このためpytest実行時にも(`core`パッケージはほぼ全テストが
間接的にimportする)、テスト由来のログ行が本番ログファイルへ混入していた。

是正: `"pytest" in sys.modules`でpytest実行下かどうかを判定し、pytest実行時は
`logs/transcription_test.log`(既存の`core/logging.py` `__main__`ブロックと
同じ命名パターン)へ出力先を切り替えるようにした。

## 検証方法についての注記(完了報告にも記載)

素朴には「pytest実行前後で`logs/transcription.log`の行数を比較する」テストが
考えられるが、本番環境ではこのファイルへ**pytestとは無関係な稼働中プロセス**
(実際に稼働している本番WebUIサーバー等、チーム内の他ロールによる並行操作を含む)
が随時書き込むため、この比較は本質的にレースコンディションを含み信頼できない
(実機で確認済み: 本テスト実装時、ファイル編集を挟まない前後でも該当ファイルの
行数が2行増加する事象を観測し、両方とも`transcribe.py`の`TranscribeAudioApp.run()`
由来(logger名`__main__`)でpytestのキャプチャ出力には一切含まれないことを確認した。
すなわち別プロセスからの書き込みであり、pytestの実行とは無関係)。

そのため本ファイルは、外部要因に左右されない決定的な検証方法として、
`UnifiedLogger`の実際の設定状態(`_log_file`クラス属性)を直接検証する。
"""
from core.logging import UnifiedLogger


class TestPytestLogGuard:
    def test_unified_logger_uses_test_log_file_under_pytest(self):
        """`core`パッケージのimport副作用により、pytest実行下では
        UnifiedLoggerの設定先が本番ログ(logs/transcription.log)ではなく
        logs/transcription_test.logになっていることを確認する。

        このテスト自体がpytest配下で実行される時点で`sys.modules`に"pytest"が
        含まれるため、`core/__init__.py`のガードが機能していれば必ずこの状態になる。
        """
        assert UnifiedLogger._log_file == "logs/transcription_test.log"
        assert UnifiedLogger._log_file != "logs/transcription.log"

    def test_pytest_is_actually_in_sys_modules(self):
        """テスト自身の前提(pytest配下で実行されていること)を確認する
        (この前提が崩れていれば上記テストの意味がなくなるため)。"""
        import sys

        assert "pytest" in sys.modules
