# 査から計への検査報告書 - Nemotron3.5ASR-StreamingPhase2実装(GPU不要範囲)完了報告(saku)

> **発行日**: 2026年09月26日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書
> **検査対象**: 実装差分（`core/nemotron_engine.py`・`scripts/nemotron_infer.py`・`scripts/setup_nemotron_venv.sh`・`tests/test_core_nemotron_dispatch.py`・`core/transcription_interface.py`変更・`webui.py`変更） / **宛先**: 計ロール

## 検査結果

### 判定: **不合格**（是正必須1件）

## 1. セルフチェック証跡の確認

作の完了報告（agmsg）に機械検査結果・CPU範囲の動作確認・exec bit確認が明記されている。→ 品質検査へ進行。

## 2. 完了条件の機械検証（査が独立実行）

```
$ uv run python -m pytest tests -q
129 passed, 1 skipped in 9.58s

$ bash -n scripts/setup_nemotron_venv.sh && echo OK_SYNTAX
OK_SYNTAX

$ python3 -c "<ast解析スクリプト>"
OK_OPTIONS_APPEND_DEFAULT_UNCHANGED

$ git diff --name-only -- .venv pyproject.toml uv.lock
(空)

$ git diff --summary
(mode change なし)
```

全項目、作の報告と一致。`tests/test_core_nemotron_dispatch.py`を個別に`-v`実行し、18件すべてのテストIDとPASSEDを確認した（`TestIsNemotronModel`7件・`TestJudgeExclusivity`4件・`TestUnifiedTranscriberDispatch`4件・`TestWebuiSelectboxDefaultUnchanged`1件・`TestNemotronErrorHandling`2件）。

## 3. コードレビュー（原則2。実際にファイルを読み、静的検証・実地検証を行った）

- `core/nemotron_engine.py`: `TranscriptionEngine`抽象基底の`transcribe()`/`get_engine_name()`を実装。`validate_audio_file`（基底クラスに実在確認済み）・`perf_logger.start_timing/end_timing`（`core/logging.py`に実在確認済み）・`TranscriptionConfig.model/.language`（`core/config.py`に実在確認済み）の使用はいずれも正しい。
- `core/transcription_interface.py`の変更: `UnifiedTranscriber.__init__`内でのローカルimport（`from core.nemotron_engine import ...`）により循環import（`nemotron_engine.py`→`transcription_interface.py`）を正しく回避している。diffは最小（elif追加のみ）で意図と一致。
- `is_nemotron_model`/`Qwen3ASREngine.is_qwen3_model`の文字列排他性は査自身も確認し、テスト（`TestJudgeExclusivity`）で機械的に保証されている。
- `scripts/nemotron_infer.py`: stdout をJSON1行に限定し診断ログを`sys.stderr`へ分離する設計どおり。`transformers`公式API（`AutoModelForRNNT`/`AutoProcessor`/`load_audio`）の使用法は、査が別件（tc-ops #546予備調査）で直接確認済みの公式ドキュメントの使用例と一致している。
- `core/nemotron_engine.py`はモジュールレベルで`torch`/`transformers`をimportしない設計（重い依存は`scripts/nemotron_infer.py`側のみ、隔離venv上で実行）であることを確認した。これにより生産用`.venv`（`transformers==4.57.6`固定）でも`core.nemotron_engine`を問題なくimportできる（`webui.py`のトップレベルimportも含め、査が実際に`uv run python -m pytest`実行時に確認済み＝生産用`.venv`でのimportは実際に成功している）。

## 4. 是正必須（不合格の根拠）: `include_timestamps`無効化がウィジェット状態の持ち越しにより機能しない

采の追加指摘（2026-09-26T13:54:05Z）と本指示書§2は「Nemotron選択時は`include_timestamps`チェックボックスを無効化し、その旨を表示する」ことを明示的な設計要件としている。しかし実装（`webui.py`）は`disabled=nemotron_selected`のみを設定しており、**チェックボックスの値そのものをNemotron選択時にFalseへ強制していない**。

Streamlitのウィジェットは、値をユーザーが一度設定すると`disabled=True`にしても値は保持され続ける（`disabled`は入力の受理を止めるだけで、値のリセットは行わない）。査は`streamlit.testing.v1.AppTest`を用いて実際に再現し、この挙動を実機で確認した（stderrのScriptRunContext警告はbareモード実行時の既知の無害な警告であり、動作自体には影響しない）:

```python
at = AppTest.from_file(<webui.pyの該当ウィジェット構造を再現した最小スクリプト>)
at.run()
at.checkbox[0].check()          # モデル=Qwen(既定)のままチェックを入れる
at.run()
# → checkbox.value = True
at.selectbox[0].select("nvidia/nemotron-3.5-asr-streaming-0.6b")  # Nemotronへ切替
at.run()
# → checkbox.value = True, checkbox.disabled = True （値は保持されたまま無効化のみ）
# → RESULT_include_timestamps = True  （実際に送信される値）
```

再現手順（利用者操作として現実的なシナリオ）:
1. デフォルト（Qwen3-ASR-1.7B）のまま「タイムスタンプ付与」にチェックを入れる
2. モデル選択をNemotronへ切り替える（チェックボックスは灰色表示・操作不可になる）
3. **チェック状態は`True`のまま残り、変換実行時の設定（`item.settings["include_timestamps"]`）も`True`のまま送信される**

この結果、`webui.py` L409（`if item.settings.get("include_timestamps"): srt_text = segments_to_srt(result.segments)`）が実行され、Nemotronの単一セグメント出力に対してSRTプレビューが生成される。`NemotronSubprocessEngine`自体は`include_timestamps`を参照せず常に単一セグメントを返す設計のため例外や停止は発生しないが、**采が明示的に回避を求めた「実質1行になり壊れた出力に見える」状態がそのまま利用者に表示される**。「無効化する」という設計要件（案b）の実効性が、この操作順序では成立していない。

**是正指示**: `nemotron_selected`のとき`include_timestamps`の値そのものを`False`に強制すること。例:

```python
include_timestamps = st.checkbox(
    "タイムスタンプ付与(ForcedAligner使用、GPUメモリ約1.2GB追加)",
    value=False,
    disabled=nemotron_selected,
)
if nemotron_selected:
    include_timestamps = False
    st.caption("Nemotronは現時点でタイムスタンプ非対応です")
```

是正後、上記のAppTest再現手順（チェック→Nemotron切替→`include_timestamps`が`False`になること）をテストとして追加し、回帰テストに含めることを推奨する（現行の18件にはこのシナリオを検証するものがない）。

## 5. 計ロールへの報告

是正の反映後、再査読を依頼されたい。

**文書終了**
