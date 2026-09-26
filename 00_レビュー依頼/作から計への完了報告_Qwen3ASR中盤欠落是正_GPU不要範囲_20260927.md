# 作から計への完了報告: Qwen3ASR中盤欠落是正（GPU不要範囲）

**報告日**: 2026-09-27
**報告者**: 作成ロール（作、saku）
**対象**: tc-ops #547（是正実装、GPU不要範囲: (c)反復部分のみ除去・(d)無音区間2分割フォールバック）

## 実施概要

kei承認（2026-09-26T19:30:36Z「実装着手(GPU不要な範囲)は今すぐ進めてよい」）を受け、`core/transcription_interface.py`の反復ループ是正ロジックを実装した。GPU使用・実機推論は行っていない（既存の`_model`はテストで全てMagicMockに置換、実モデルのロード・推論は発生していない）。

## 実装内容

1. **`_detect_repetition`の拡張**（成果物要件2）: 戻り値を`bool`から`(bool, 反復開始位置の文字インデックスまたはNone)`へ拡張した。反復開始位置は「反復サイクルの最初の出現位置」までの文字数オフセットとして算出する（`fragments[:i]`の文字数合計）。呼び出し元2箇所（旧コード内）は本改修に伴い新ヘルパーメソッドへ統合した。

2. **`_transcribe_chunk_with_fallback`の新設**（成果物要件3・4を統合実装）: `_transcribe_long_audio`のチャンク単位処理を切り出した新メソッド。処理順序:
   - 1回目transcribe → 反復なしならそのまま採用（正常チャンクは従来と同じ1回呼び出しのみ、フォールバック分岐に一切入らない）。
   - 反復検出時は同一チャンクを1回再試行（既存動作を維持）。再試行で解消すればその結果を採用。
   - 再試行後も反復する場合、**(d) 無音区間2分割フォールバック**: チャンク長が`_MIN_SPLIT_DURATION_SEC`（40秒、無音探索窓±20秒×2の下限）以上かつ`allow_split=True`（トップレベル呼び出しのみ。再帰は1段に限定し孫分割はしない）であれば、`core.nemotron_engine.find_silence_boundary()`（tc-ops #546で実装済みの無音区間検出、転用）でチャンクを前半/後半に分割し、それぞれを独立に（`allow_split=False`で）本メソッドへ再帰的にかける。
   - 分割不可、または分割後の半分自体が再試行後も反復する場合、**(c) 反復部分のみ除去**: 反復開始位置以前の正常テキストを残し、以降を切り詰める。反復開始位置が0（残せる正常テキストが無い）場合のみ、既存の全体破棄方式（`[チャンクN反復検出のため破棄]`プレースホルダ）を維持する。

3. **`_transcribe_long_audio`側の変更**: チャンクごとの処理を上記ヘルパー呼び出しに置き換えた。正常チャンクの処理フロー・実行回数（1回のtranscribe呼び出し）には変更がない。

## 完了条件（機械検査）実測結果

```
$ uv run python -m pytest tests -q 2>&1 | tail -5
........................................................................ [ 40%]
.............................................s.......................... [ 80%]
...................................                                      [100%]
178 passed, 1 skipped, 3 warnings in 9.50s

$ sed -n '458p' core/transcription_interface.py
                max_new_tokens=1024,  # 長音声向けに十分確保
→ OK_MAX_NEW_TOKENS_UNCHANGED（(a)見送りのとおり、1024のまま変更なし）

$ grep -n "_detect_repetition" core/transcription_interface.py
（拡張後の定義・呼び出し3箇所を確認、既存呼び出し元は全て新戻り値形式へ移行済み）

$ grep -n "_split_audio_at_silence\|_transcribe_chunk_with_fallback\|_MIN_SPLIT_DURATION_SEC" core/transcription_interface.py
（(d)実装の存在を確認）

$ git diff --name-only -- .venv pyproject.toml uv.lock | wc -l
0 → OK_NO_ENV_CHANGE

$ git diff --summary -- core/transcription_interface.py tests/test_core_transcription_interface.py
（出力なし＝mode change無し、exec bit変更なし）
```

## 回帰テスト（新規・更新）

`tests/test_core_transcription_interface.py`に以下を追加・更新した（テスト総数: 12→17、うち新規5・更新3）:

- `TestDetectRepetition`: 全5テストを新戻り値形式`(bool, position)`へ更新。反復開始位置が正常プレフィックス長以内であること・冒頭反復ケースで`position == 0`であることを追加検証。
- `TestChunkRetryFallback`: 旧`test_retry_still_repetitive_inserts_placeholder`（チャンク全体破棄を前提とした旧仕様のテスト）を撤去し、(d)分割で前半/後半とも回復するケース、および分割後も両半分とも回復不能な最悪ケース（プレースホルダは半分単位になる）の2テストへ置き換えた。
- `TestPartialRepetitionRemovalAndSplitFallback`（新設）: `_transcribe_chunk_with_fallback`を直接呼び出し、(c)単独（分割不可・短チャンク）での切り詰め、(c)全体破棄（残せる正常テキストなし）、(d)→(c)のネスト（分割後の片側のみ切り詰め）、正常系（フォールバック不発火・呼び出し回数1回）の4パターンを個別に検証。

## 既知の制限事項（成果物要件4）

- 分割(d)の再帰は1段に限定している（分割後の半分をさらに分割することはしない）。3分割目以降が必要になるような極端な反復パターンは(c)の切り詰め止まりとなるが、これは仕様として意図的な制限（無限再帰・処理時間の際限ない増大を防止するため）。
- 分割点は`find_silence_boundary()`（既存関数の転用）に依存するため、無音区間が検出できない音声（BGM等が常時鳴っている等）では均等分割点（中間点）にフォールバックする。これは既存のtc-ops #546実装と同じ既知の制約であり、新規のリスクではない。
- 本報告は「GPU不要範囲」の完了報告であり、回帰ゲート5条件（JSUT CER・基準通話音声でのチャンク破棄なし＆#71系統中盤内容の目視確認・処理時間/VRAM実測・全テスト合格）のうちGPU実測が必要な項目は含まない。これらは着手前に計経由で采へ連絡のうえ、別途実施する。

---

## Git管理依頼

計ロールに以下のファイルのGit管理を依頼します:
- core/transcription_interface.py
- tests/test_core_transcription_interface.py
- 00_レビュー依頼/作から計への完了報告_Qwen3ASR中盤欠落是正_GPU不要範囲_20260927.md

## WBS更新依頼

WBSの更新をお願いします。

## 次のステップ

回帰ゲート5条件のGPU実測（着手前に計経由で采へjev-local停止連絡が必要）について、着手可否の指示を待ちます。
