# 査から計への検査報告書 - Nemotronストリーミング推論Phase2本実装 最終合否(saku)

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書（最終）
> **検査対象**: `00_レビュー依頼/作から計への完了報告_Nemotronストリーミング推論Phase2本実装_20260927.md`（commit a051269時点） / **宛先**: 計ロール

## 検査結果

### 判定: **合格**（tc-ops #546 Phase2完了報告 全体）

## 1. 前回不合格根拠（訂正2・prompt_ids真因）の検証

前回の不合格根拠は「条件2再測定でCER・文字数が是正前（実質auto）と完全一致したのは、異なるプロンプトID(ja-JP=10/auto=101)を与えたにもかかわらず不自然であり、一次証拠なしに採用できない」であった。今回のsaku報告（訂正2）は、この疑義を裏付ける真因を提示している。

**真因の実ソース確認**: 査が直接、隔離venv内の実ファイルを確認した。

```
$ grep -n "prompt_ids" venv-nemotron/.../nemotron3_5_asr/generation_nemotron3_5_asr.py
26:        self._prompt_ids = kwargs.pop("prompt_ids", None)

$ grep -n "decoder_input_ids\|blank_token_id" venv-nemotron/.../nemotron_asr_streaming/generation_nemotron_asr_streaming.py
173:            decoder_input_ids=first_chunk.new_full((batch_size, 1), self.config.blank_token_id, dtype=torch.long),
```

報告書の主張（`prompt_ids`は`model.generate()`呼び出し時の**トップレベルkwargs**からのみ取り出され、streaming生成の実エントリポイントは`decoder_input_ids`を`blank_token_id`へ無条件初期化するため、チャンクごとの`processor(...)`が計算した`prompt_ids`は暗黙に参照されない）と、上記の実ソースが完全に一致することを確認した。

**是正diffの確認**: `git show c4f2c5d -- scripts/nemotron_infer.py`で、`prompt_ids = processor._resolve_prompt_ids(language, 1).to(model.device)`を直接計算し、`model.generate(..., prompt_ids=prompt_ids, ...)`へトップレベル引数として渡す変更を確認した。

**再検査の自己拘束（新パターン確認・旧パターン再現）**: 現状の`scripts/nemotron_infer.py`から`model.generate(...)`呼び出しの`prompt_ids=prompt_ids`のみを人為的に取り除いた版（訂正2前の状態の再現）を一時的に作成し、`TestStreamingLanguagePropagation`の2件（`test_explicit_language_reaches_generate_as_prompt_ids`・`test_different_languages_resolve_to_different_prompt_ids`）を実行したところ両方**FAILED**した。是正後の実ファイルへ復元して再実行したところ両方**PASSED**した。このテストは訂正2の真因（`prompt_ids`が`model.generate()`のトップレベルkwargsに届いているか）を直接検出する実効性があることを確認した。

`uv run python -m pytest tests -q`を独立再実行し、`182 passed, 1 skipped, 3 warnings`（報告と完全一致）を確認した。

## 2. 実効性確認・条件2最終再測定の評価

- 「`language="ja-JP"`→383字の正常な書き起こし、`language="en-US"`（意図的誤り）→出力0字」という対照実験結果は、`prompt_ids`是正前には区別できなかった2条件が明確に異なる挙動を示すという、真因の伝播を裏付ける具体的かつ検証可能な内容であり、単なる結論の宣言ではない点を評価する。
- 条件2最終再測定（streaming CER=13.33%/2506字、分割方式CER=13.73%/2536字、両方ja-JP明示）は、訂正1時点の測定値（13.49%/2495字）から実際に変化しており、これは是正が生成結果へ実際に影響するようになったことの追加的な証拠であり、前回査が指摘した「完全一致は不自然」という疑義が正しく解消されたことを示す。
- 「streamingが分割方式に劣らない」という結論（13.33% < 13.73%）は、今回の対称・真因是正済みの条件下でも維持されている。

## 3. その他の確認事項（合否に影響せず）

- 条件2の実効性確認で用いた`WORK_20260926_220529_phase1/test_audio/candidate3_20sent.wav`は、Phase1調査時からの既存テスト資産（未追跡だが本報告のために新規ダウンロードしたものではない）であることをファイルシステムで確認した。後片付け節に追記がない点は、削除対象の新規一時ファイルが生じていないためであり、矛盾ではないと判断する。
- `_build_streaming_chunk_generator()`は依然各チャンクの`processor(..., language=language, ...)`呼び出しで（今は使われない）`prompt_ids`をチャンクごとに計算しているが、これは無害な冗長計算であり正当性には影響しない（将来の可読性向上の余地として参考に留める。是正指示ではない）。

## 4. 計ロールへの報告

tc-ops #546 Nemotronストリーミング推論Phase2本実装、完了報告全体を最終合格とする。GPU使用完了報告（jev-local再開可の采への報告）は、計の判断で進めて構わない。

**文書終了**
