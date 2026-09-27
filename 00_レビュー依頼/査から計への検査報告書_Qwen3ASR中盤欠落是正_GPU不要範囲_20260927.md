# 査から計への検査報告書 - Qwen3ASR中盤欠落是正（GPU不要範囲）完了報告(saku)

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書
> **検査対象**: `00_レビュー依頼/作から計への完了報告_Qwen3ASR中盤欠落是正_GPU不要範囲_20260927.md` / **宛先**: 計ロール

## 判定: **合格**

## 1. 完了条件の機械検証（査が独立実行）

```
$ uv run python -m pytest tests -q
178 passed, 1 skipped
$ sed -n '458p' core/transcription_interface.py
                max_new_tokens=1024,  # 長音声向けに十分確保
$ grep -n "_detect_repetition" core/transcription_interface.py
（定義・呼び出し4箇所を確認）
$ grep -n "_split_audio_at_silence\|_transcribe_chunk_with_fallback\|_MIN_SPLIT_DURATION_SEC" core/transcription_interface.py
（実装の存在を確認）
$ git diff --name-only -- .venv pyproject.toml uv.lock | wc -l
0
$ git diff --summary -- core/transcription_interface.py tests/test_core_transcription_interface.py
（出力なし＝mode change無し）
```

作・計の報告と一致。`tests/test_core_transcription_interface.py`（17件）を個別実行しすべてPASSEDを確認した。

## 2. 実装のコードレビュー（原則2。フォールバック連鎖を手で追跡し、テストが実際に検証しているか照合）

- `_detect_repetition`の拡張は既存アルゴリズム（フラグメント分割・スライド窓比較）を変更せず、検出時のみ`position = sum(len(f) for f in fragments[:i])`を追加した最小限の拡張であることを確認した。
- `_transcribe_chunk_with_fallback`の分岐（1回目→再試行→(d)無音分割(1段限定・`allow_split=False`で再帰)→(c)切り詰め/全体破棄）を手で追跡した。特に以下2点を重点確認した:
  - **(d)再帰後の再帰防止**: 分割後の各半分は`allow_split=False`で呼ばれるため、`if allow_split and len(chunk_audio) >= min_split_samples:`の条件が偽になり孫分割は発生しない。`test_split_fallback_recurses_once_then_truncates_remaining_half`がこの経路（片側は再度反復→(c)切り詰め、もう片側は正常）を実際に検証しており、`call_count == 5`（top:2＋left:2＋right:1）の期待値も手計算と一致する。
  - **(c)の`pos == 0`境界**: `if is_rep and pos:`はPythonの真偽評価により`pos == 0`（残せる正常テキストが無い）で偽になり、全体破棄へ正しく分岐する。`test_truncation_discards_when_no_salvageable_prefix`が実際にこの分岐を検証している。
- `core.nemotron_engine.find_silence_boundary`のimportが`_split_audio_at_silence`内のローカルimportになっていることを確認した（`core/nemotron_engine.py`が`core/transcription_interface.py`をトップレベルでimportしているため、逆方向をトップレベルimportすると循環importになる。既存の`UnifiedTranscriber.__init__`と同じ回避パターンを踏襲）。実際に`import core.transcription_interface`が問題なく成功することを確認した。
- 正常チャンク（反復なし）が`_transcribe_chunk_with_fallback`の分岐に一切入らず`transcribe()`を1回だけ呼ぶことを`test_no_repetition_single_call_no_fallback`・`test_no_repetition_no_retry`で確認し、査自身もコードの早期returnパスを確認した。

## 3. 計ロールへの報告

最終承認をお願いします。回帰ゲート5条件のGPU実測（着手前に計経由で采へ連絡）については、着手可否の判断を計に委ねる。

**文書終了**
