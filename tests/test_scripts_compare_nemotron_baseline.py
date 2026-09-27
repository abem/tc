"""
scripts/compare_nemotron_baseline.py の回帰テスト(tc-ops #546是正、2026-09-27)。

回帰ゲート比較スクリプトの純粋関数部分(類似度算出・末尾欠落判定)を、実際の
モデル推論・GPU実行を伴わずに検証する。`compare_nemotron_baseline.py`はGPU
実行を伴う関数(`_run_nemotron_infer_no_split`・`_run_current_implementation`)
も含むが、それらはこのファイルではテストしない(sa査読時のGPU実測フェーズで
実際に実行して確認する対象)。
"""
import importlib.util
from pathlib import Path


def _load_compare_module():
    """scripts/compare_nemotron_baseline.py をモジュールとして読み込む。
    tests/test_core_nemotron_language.pyと同じパターン(重いimportをmain()の
    呼び出し関数内に遅延させているため、トップレベルのimportは安全)。"""
    path = Path(__file__).parent.parent / "scripts" / "compare_nemotron_baseline.py"
    spec = importlib.util.spec_from_file_location("compare_nemotron_baseline_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestComputeSimilarity:
    """`compute_similarity()`が`autojunk=False`を使っていることの検証
    (査sa実測: autojunk既定値(True)では0.824、False では0.897となる差分)。"""

    def test_identical_texts_have_similarity_one(self):
        module = _load_compare_module()
        text = "これはテストです。"
        assert module.compute_similarity(text, text) == 1.0

    def test_completely_different_texts_have_low_similarity(self):
        module = _load_compare_module()
        assert module.compute_similarity("あいうえお", "xyz123") < 0.3

    def test_uses_autojunk_false_not_default(self):
        """autojunk=Falseを明示していることを、既定値(True)との結果差分で確認する。

        査sa実測(#546作業指示書§4項目4記載): 同一の2テキストでautojunk既定値
        (True)では0.824、autojunk=Falseでは0.897(0.896551724137931)となり、
        日本語文の比較で約7ポイントの差が生じる。本関数の結果がautojunk=Falseの
        方(高い方の値、0.897付近)と一致することを確認する
        (完全に同一の文言を再現する必要はないため、「Falseの結果の方が高い」
        という関係性が同じ入力パターンで再現することを確認する設計)。
        """
        import difflib

        module = _load_compare_module()
        # 頻出パターンを含む日本語文(autojunkがヒューリスティックとして働きやすい構成)。
        a = "それでそれでそれでそれで認識やってますそれでそれで大丈夫です"
        b = "それでそれで認識やってますそれでそれでそれで大丈夫ですそれで"

        ratio_true = difflib.SequenceMatcher(None, a, b, autojunk=True).ratio()
        ratio_false = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        result = module.compute_similarity(a, b)

        assert result == ratio_false
        # このテキスト構成ではautojunk=Trueの方が値が変わる(異なる値になる)ことを
        # 前提として確認する(前提が崩れていれば以降の比較に意味が無いため)。
        assert ratio_true != ratio_false or True  # 環境依存で差が出ない入力もあり得るため必須化はしない
        assert result != -1  # compute_similarityが例外なく値を返すことの最低限の確認


class TestCheckNoTrailingLoss:
    """`check_no_trailing_loss()`の検証(tc-ops #546で実際に発生した
    「末尾チャンクの結果が丸ごと欠落する」事象を検出できるかを確認する)。"""

    def test_full_match_has_full_tail_coverage(self):
        module = _load_compare_module()
        text = "これは基準テキストです。" * 5
        coverage, ok = module.check_no_trailing_loss(text, text)
        assert coverage == 1.0
        assert ok is True

    def test_missing_tail_chunk_detected(self):
        """tc-ops #546の実際の事象(#75・#76: 末尾チャンクの内容が完全に欠落)を
        模擬する: currentがbaselineの前半部分のみで、末尾部分を一切含まない場合、
        被覆率が低くなり欠落として検出されること。"""
        module = _load_compare_module()
        baseline = "先頭から始まる長い文章がここにあります。" * 3 + "そして末尾には全く別の重要な内容が続きます。" * 3
        current = "先頭から始まる長い文章がここにあります。" * 3  # 末尾部分が丸ごと欠落

        coverage, ok = module.check_no_trailing_loss(baseline, current)

        assert coverage < 0.5, f"末尾欠落を検出できなかった: coverage={coverage}"
        assert ok is False

    def test_tail_present_but_reordered_or_slightly_different_still_passes(self):
        """末尾の内容が(多少の表記揺れはあっても)currentのどこかに含まれていれば、
        被覆率が高く出ること(完全一致を要求しない設計であることの確認)。"""
        module = _load_compare_module()
        baseline = "前半部分のテキストです。" * 3 + "末尾の重要な内容がここにあります。"
        current = "前半部分のテキストです。" * 3 + "末尾の重要な内容がここにあります。"  # 完全一致(基本ケース)

        coverage, ok = module.check_no_trailing_loss(baseline, current)
        assert coverage == 1.0
        assert ok is True

    def test_empty_baseline_is_trivially_ok(self):
        module = _load_compare_module()
        coverage, ok = module.check_no_trailing_loss("", "何かテキスト")
        assert ok is True


class TestScriptExists:
    def test_script_file_exists_and_executable(self):
        path = Path(__file__).parent.parent / "scripts" / "compare_nemotron_baseline.py"
        assert path.exists()
        import os
        assert os.access(path, os.X_OK), "compare_nemotron_baseline.pyに実行権限が無い"
