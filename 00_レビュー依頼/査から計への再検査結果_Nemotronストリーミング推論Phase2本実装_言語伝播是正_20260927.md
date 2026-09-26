# 査から計への再検査結果 - Nemotronストリーミング推論Phase2本実装 言語伝播是正(saku)

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 再検査結果
> **検査対象**: is正報告(kei、2026-09-26T23:26:44Z) / **宛先**: 計ロール

## 検査結果

### 判定: **是正1件は合格**。ただし**回帰ゲート条件2の再測定を必須とする（Phase2完了報告全体の最終合格は保留）**

## 1. 是正1件（language_arg伝播）: 合格

`git diff -- scripts/nemotron_infer.py`で以下を確認した:

- `main()`の`language_arg = resolve_processor_language(args.language)`が、`_run_streaming_inference(processor, model, args.audio_paths[0], args.num_lookahead_tokens, language_arg)`へ明示的に渡されている。
- `_run_streaming_inference()`は受け取った`language`を`_build_streaming_chunk_generator(audio, processor, sampling_rate, language)`へそのまま渡している。
- `_build_streaming_chunk_generator()`内の各チャンクの`processor(chunk_audio, sampling_rate=sampling_rate, language=language, is_streaming=True, is_first_audio_chunk=is_first)`呼び出しに`language`が明示的に渡っている。

**再検査の自己拘束（旧パターンで再現・新パターンで解消の確認）**: 現状(是正後)の`scripts/nemotron_infer.py`から`processor(...)`呼び出しの`language=language`のみを人為的に取り除いた版（当初の欠落を再現）を一時的に作成し、`tests/test_core_nemotron_language.py::TestStreamingLanguagePropagation`の2件を実行したところ、両方が意図通り**FAILED**（`language`未伝播を正しく検出）した。是正後の実ファイルへ復元して再実行したところ両方**PASSED**した。この2件は当初の欠落を検出できる実効性のあるテストであることを確認した。

`uv run python -m pytest tests -q`を独立再実行し、`182 passed, 1 skipped, 3 warnings`（報告と完全一致）を確認した。

## 2. 判断要請への回答: 回帰ゲート条件2の再測定は必須と判断する

理由:

1. 是正前のCER比較（streaming 13.49% vs 分割方式 13.73%）は、**streaming側が実質"auto"（言語未指定相当）、分割方式側が明示"ja-JP"という非対称な言語条件下**で行われた測定である。これは条件2が本来検証すべき「streaming推論方式そのものが分割方式に劣らないか」という問いに対し、言語条件という別の変数が交絡した測定であり、条件2の結果として採用できない。
2. 両者の差(13.49%と13.73%、差0.24pt)は僅少である。この僅少さ自体が、言語条件の違いという交絡変数だけで説明可能な範囲に十分収まる大きさであり、「実質的な影響はない」というsakuの推測を追認する根拠にはならない（むしろ、差が小さいほど交絡の影響で符号が変わる可能性を排除できない）。
3. 条件2はユーザー承認済みの回帰ゲート必須項目であり、Phase2本実装のGO判断の直接的根拠になっている。交絡が判明した測定を根拠のまま残すことは、原則2（証拠ベース検証）に反する。

**是正指示**: is正後（language明示伝播込み）のstreaming経路で、分割方式（既存の明示ja-JP、変更なし）と対称な言語条件下でJSUT485秒音声のCER再測定を行うこと。GPU使用のため、着手前に計経由で采へ連絡すること（jev-local停止手続き、既存の運用どおり）。

## 3. 計ロールへの報告

- 是正1件（language_arg伝播）は合格。以後のPhase2完了報告の再提出時に再確認は不要（本件はクローズ）。
- 回帰ゲート条件2は上記の再測定結果を持って再度報告されたい。条件1・3・4は是正前の実測値に変更を要する要素がないため再測定不要と判断する（条件1は350秒以下でstreaming非経由・条件3はVRAM/処理時間の絶対値・条件4はpytest結果であり、いずれもlanguage伝播の有無に依存しない）。
- 条件2の再測定結果を含む完了報告を受領後、Phase2完了報告全体の最終合否を判定する。

**文書終了**
