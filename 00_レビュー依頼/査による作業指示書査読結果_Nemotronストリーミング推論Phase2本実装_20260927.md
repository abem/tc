# 査による作業指示書査読結果_Nemotronストリーミング推論Phase2本実装_20260927

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 作業指示書査読結果
> **査読対象**: `00_レビュー依頼/計から作への作業指示書_Nemotronストリーミング推論Phase2本実装_20260927.md` / **宛先**: 計ロール

## 判定: **不合格**（是正必須1件）

## 1. 検証方法

- 采決定原文（2026-09-26T22:14:45Z、sai→kei）と本指示書§2・§3・§6の対応を確認
- commit `74029ec`実在確認、`CHUNK_THRESHOLD_SEC=350`（L79）・`compute_chunk_boundaries`（L93）・`NemotronSubprocessEngine.transcribe`（L337）を実ファイルで確認
- 完了条件3件を現状（是正前）で実地実行

## 2. 検証結果（前提事項）

采決定原文と本指示書§2・§6の対応、commit・行番号引用はすべて一致した。

## 3. 是正必須: 完了条件「フォールバック機構」のgrepが実装前から偽陽性になる

```
$ grep -n "def.*fallback\|streaming.*fallback\|フォールバック" core/nemotron_engine.py scripts/nemotron_infer.py
```

これを現状（ストリーミング推論のフォールバック機構は未実装）で実地実行したところ、**8行がヒットした**:

```
scripts/nemotron_infer.py:85:    (auto/cuda/cpu)と対応させ、未知の値は安全側の"auto"にフォールバックする。
core/nemotron_engine.py:165:    フォールバック。呼び出し元は本関数の戻り値をそのまま分割点として使えばよく、
core/nemotron_engine.py:166:    フォールバック時の分岐を別途持つ必要はない)。
core/nemotron_engine.py:191:        # librosa側の予期しない失敗時も、均等分割点へのフォールバックで処理を継続する。
core/nemotron_engine.py:212:    返すため、本関数も自動的に既存の均等分割へフォールバックする。
core/nemotron_engine.py:241:    def _get_audio_duration_fallback() -> float:
core/nemotron_engine.py:242:        """音声長取得失敗時のフォールバック(既存エンジンと同一パターン)。"""
core/nemotron_engine.py:364:            # 無音区間が見つからない場合は自動的に均等分割点へフォールバックする。
```

`device_map`のフォールバック・無音区間検出のフォールバック・音声長取得のフォールバックなど、**既存の無関係な機能に「フォールバック」という語・`def..._fallback`という命名パターンが既に多数存在する**ため、本指示書が求める「ストリーミング推論失敗時の分割方式へのフォールバック」を一切実装しなくても、このチェックは常に真になる。この完了条件は機能を検証していない。

**是正指示**: 本指示書§4項目2で自ら例示している一意な文言（`logger.warning("Streaming推論が失敗、分割方式へフォールバック: ...")`）そのものをgrep対象にする、または新設する専用関数名（例: `_transcribe_with_streaming_fallback`）の定義行の存在を確認するchecksへ変更されたい。念のため、この文言・関数名が現状ではヒットしないことも確認した（`grep -q "Streaming推論が失敗" core/nemotron_engine.py` → 該当なし）。

## 4. その他の確認事項（是正指示の対象外・参考）

- 完了条件1（`num_lookahead_tokens`）・3（mel±1ずれ対策の各キーワード）は、現状（未実装）でいずれも該当なしを確認した。偽陽性のリスクはない。
- 既存の均等分割・無音区間調整ロジック（`compute_chunk_boundaries`・`find_silence_boundary`・`adjust_boundaries_to_silence`）を削除せずフォールバック用に維持するという§4項目4の指示は、上記③是正必須で指摘した既存フォールバック群を指しており、削除しない旨の明記は適切である。

## 5. 計ロールへの報告

是正（§3）の反映後、再査読を依頼されたい。

**文書終了**
