# 査から計への検査報告書(再検査) - Nemotron3.5ASR-StreamingPhase2実装完了報告(是正版)

> **発行日**: 2026年09月26日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書（再検査）
> **検査対象**: 実装差分 是正版（`webui.py`・`tests/test_core_nemotron_dispatch.py`・`tests/fixtures/webui_settings_panel_harness.py`） / **宛先**: 計ロール

## 検査結果

### 判定: **合格**

## 1. 前回の不合格根拠が今回も落ちることの確認（再検査の自己拘束・手順の義務）

前回の不合格根拠は「`include_timestamps`チェックボックスが`disabled=True`のみで値自体をFalseへ強制しておらず、Qwen等でチェック→Nemotron切替の順で操作すると`True`のまま送信される」ことであった。

査は是正版のコードを**一時的に是正前の状態へ差し戻し**、同じテスト（`TestIncludeTimestampsForcedFalseOnNemotron::test_checked_then_switch_to_nemotron_forces_value_false`）を同じ手順（`streamlit.testing.v1.AppTest`でチェック→Nemotron切替の操作順序を再現）で再実行した。

```
$ (webui.pyのinclude_timestamps=False強制行を一時的に削除)
$ uv run python -m pytest tests/test_core_nemotron_dispatch.py::TestIncludeTimestampsForcedFalseOnNemotron -v
FAILED ... AssertionError: Nemotron選択時はinclude_timestampsの値自体がFalseへ強制されること(disabled表示だけでは不十分)
assert True is False
1 failed in 1.56s
```

**前回の不備が今回も検出できる状態にあることを確認した**（是正前コードで確実に落ちる）。その後、是正版へ復元（`diff`でバイト同一を確認）し、再実行してPASSEDを確認した:

```
$ uv run python -m pytest tests/test_core_nemotron_dispatch.py::TestIncludeTimestampsForcedFalseOnNemotron -v
PASSED
1 passed in 1.62s
```

## 2. 是正内容の確認

`webui.py`の`nemotron_selected`ブロックに`include_timestamps = False`の代入を追加（`disabled=True`に加えて値自体を強制上書き）。コメントで理由（disabledは値をリセットしないため）を明記。設計として査の指摘に正確に対応している。

## 3. 完了条件の機械検証（査が独立実行）

```
$ uv run python -m pytest tests -q
130 passed, 1 skipped in 9.18s
```

作・計の報告（既存111+新規19=130件）と一致。新規19件目は今回追加の`TestIncludeTimestampsForcedFalseOnNemotron`1件（前回18件+今回1件）。

## 4. 回帰テストの実装品質の確認

`tests/fixtures/webui_settings_panel_harness.py`が`webui.py`の実関数`_render_settings_panel()`を直接importして呼び出しており、再実装・モックによる劣化的検証ではなく本物の実装を検証している。テストのdocstringに査の指摘日時・内容が明記され、検証観点（disabled表示だけでは不十分、値自体の検証が必要）も正確に引き継がれている。

## 5. 計ロールへの報告

最終承認をお願いします。

**文書終了**
