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
import logging

import core.logging as core_logging
from core.logging import UnifiedLogger, setup_logging

# 注記(Task 5.6): ログ初期化は `import core` の副作用から、エントリポイントが呼ぶ
# core.logging.setup_logging() に移った。ガードの性質(pytest実行下では本番ログを
# 汚さず logs/transcription_test.log へ出す)は setup_logging() 側で維持しており、
# 本テストは setup_logging() を呼んだ結果の設定先を検証する。
# ルートロガー・クラス状態は終了時に復元し、cwdはtmp_pathに隔離する。


class TestPytestLogGuard:
    def test_unified_logger_uses_test_log_file_under_pytest(self, tmp_path, monkeypatch):
        """pytest実行下で setup_logging() を呼ぶと、UnifiedLoggerの設定先が
        本番ログ(logs/transcription.log)ではなく logs/transcription_test.log になる。"""
        root = logging.getLogger()
        saved_handlers, saved_level = list(root.handlers), root.level
        saved_state = (UnifiedLogger._log_file, UnifiedLogger._configured, UnifiedLogger._log_level)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(core_logging, "_setup_done", False)
        try:
            setup_logging()
            assert UnifiedLogger._log_file == "logs/transcription_test.log"
            assert UnifiedLogger._log_file != "logs/transcription.log"
        finally:
            for h in list(root.handlers):
                if h not in saved_handlers:
                    h.close()
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)
            UnifiedLogger._log_file, UnifiedLogger._configured, UnifiedLogger._log_level = saved_state

    def test_pytest_is_actually_in_sys_modules(self):
        """テスト自身の前提(pytest配下で実行されていること)を確認する
        (この前提が崩れていれば上記テストの意味がなくなるため)。"""
        import sys

        assert "pytest" in sys.modules
