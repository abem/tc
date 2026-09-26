# 査から計への検査報告書 - Nemotronストリーミング推論Phase2本実装 完了報告(saku)

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書
> **検査対象**: `00_レビュー依頼/作から計への完了報告_Nemotronストリーミング推論Phase2本実装_20260927.md` / **宛先**: 計ロール

## 検査結果

### 判定: **不合格**（是正必須1件）

## 1. 機械検証・回帰テスト（合格水準）

```
$ uv run python -m pytest tests -q
180 passed, 1 skipped
```

`tests/test_core_nemotron_chunk.py`全23件（新規`TestStreamingDispatch`2件を含む）を個別実行し全件PASSEDを確認した。`test_streaming_failure_falls_back_to_split_with_warning_log`は、streaming呼び出しが`RuntimeError`を送出した際に(1)`_invoke_subprocess`が2回呼ばれる(streaming失敗→分割方式成功)、(2)`caplog`で指示書指定の一意な文言が出力される、(3)分割方式の結果が採用される、をすべて検証しており、フォールバック機構の実装が正しく動作することを裏付けている。

`core/nemotron_engine.py`の`transcribe()`の分岐（350秒超→streaming試行→例外時は`compute_chunk_boundaries`＋`adjust_boundaries_to_silence`で分割方式へフォールバック、350秒以下→既存の`else`節へ無変更で到達）を実ファイルで手で追跡し、報告書の説明と完全に一致することを確認した。

## 2. 是正必須: streaming経路が明示的な言語指定を無視する

`scripts/nemotron_infer.py`の実装を確認したところ、`main()`は`language_arg = resolve_processor_language(args.language)`を計算しているが、**streaming経路（`_run_streaming_inference()`呼び出し）にはこの値が一切渡されていない**:

```python
language_arg = resolve_processor_language(args.language)
...
if args.streaming:
    chunk_result.update(
        _run_streaming_inference(processor, model, args.audio_paths[0], args.num_lookahead_tokens)
    )  # ← language_arg が渡されていない
```

`_run_streaming_inference()`・`_build_streaming_chunk_generator()`のシグネチャにも`language`引数がなく、内部の`processor(chunk_audio, sampling_rate=..., is_streaming=True, is_first_audio_chunk=is_first)`呼び出しは`language`引数を省略している。査が隔離venv内の実ソース（`processing_nemotron3_5_asr.py` L243）を確認したところ、`language`の既定値は`"auto"`である。

**影響**: `--language ja-JP`等を明示指定しても、350秒超のstreaming経路では常に`"auto"`（自動言語判定）が使われ、オフラインバッチ経路（明示指定を尊重）とは異なる挙動になる。本報告書の条件2（JSUT・日本語音声でのCER比較）はauto判定でも正しく日本語と判定されるためこの差異が結果に現れなかったが、**言語判定が誤りやすい音声（短い・雑音・多言語混在等）では、明示指定を無視することが精度低下につながるリスクがある**。これは「350秒以下は完全に無変更」という報告書の主張とは別の話であり、350秒超の経路固有の設計欠落である。

**是正指示**: `main()`で計算済みの`language_arg`を`_run_streaming_inference()`に渡し、`_build_streaming_chunk_generator()`内の`processor(...)`呼び出しにも`language=language_arg`を明示的に渡すこと。回帰テストには、`--language`に`auto`以外の値（例: `en-US`）を指定した場合に、streaming経路の`processor`呼び出しへその値が実際に伝播することを検証するケースを追加することを推奨する。

## 3. その他の確認事項（是正指示の対象外・参考）

- mel±1ずれ対策（`_build_streaming_chunk_generator`の切り詰め/ゼロ埋め）の実装を確認した。
- 後片付け（ダウンロード音声・派生ファイルの削除）は報告書に削除証跡（`rm -fv`＋`ls`失敗確認）が含まれており、査が把握している範囲でも矛盾する形跡はない（scratchpad配下に残るJSUT参照テキスト生成用の非本番・非個人情報スクリプトのみで、無害と判断する）。

## 4. 計ロールへの報告

是正（§2）の反映後、再検査を依頼されたい。

**文書終了**
