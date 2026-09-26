# 査による作業指示書再査読結果_Nemotron3.5ASR-StreamingPhase2GPU実測_20260927

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 作業指示書再査読結果
> **査読対象**: `00_レビュー依頼/計から作への作業指示書_Nemotron3.5ASR-StreamingPhase2GPU実測_20260927.md`（是正第2版） / **宛先**: 計ロール

## 判定: **合格**

## 1. 前回の不合格根拠が是正されたことの確認（手順の義務）

前回の不合格根拠は「チャンク処理が未実装のまま10-20分規模の音声実測を完了条件としている」ことであった。第2版は§4を**フェーズA（GPU不要: チャンク処理実装＋単体テスト＋venv構築）→フェーズB（GPU使用: E2E確認＋長尺実測＋回帰確認）**に再構成し、フェーズAの完了（`OK_CHUNK_LOGIC_IMPLEMENTED`・`OK_CHUNK_TEST_EXISTS`）をフェーズB着手の前提条件として§3完了条件の先頭に追加した。

**「落ちることを確かめる」**: 査が追加された完了条件2件を現状（是正前＝チャンク処理未実装の状態）で実地実行した。

```
$ grep -q "CHUNK_THRESHOLD_SEC\|chunk" core/nemotron_engine.py && echo OK... || echo MISSING_CHUNK_LOGIC
MISSING_CHUNK_LOGIC
$ grep -rlq "chunk" tests/test_core_nemotron_dispatch.py tests/test_core_nemotron_language.py tests/test_core_nemotron_chunk.py 2>/dev/null && echo OK... || echo MISSING_CHUNK_TEST
MISSING_CHUNK_TEST
```

現状で正しく`MISSING_*`を検出しており、前回の不合格根拠（チャンク処理未実装のまま先へ進めてしまうこと）を今回の完了条件が構造的にブロックすることを確認した。

## 2. 是正内容の技術的妥当性

チャンク処理をフェーズA（GPU不要）の成果物として明示し、既存`Qwen3ASREngine._transcribe_long_audio`の分割・結合パターンを参考実装として指定している。査が前回計算した線形外挿モデルで、300秒（5分）チャンク単位に区切った場合のピークVRAM推定を確認したところ、1チャンクあたり約12717MiB（ベースライン5300MiB＋モデルロード差分約2410MiB＋推論時追加分約5007MiB）であり、総VRAM16376MiBの範囲内に収まる。フェーズAでの実装完了後にフェーズBへ進む順序であれば、前回指摘したOOMリスクは技術的に解消される設計になっている。

## 3. その他

sai許可原文・GPU使用直前連絡運用・旧venv削除タイミングの記載は前回査読時から変更なく、原文と一致している。

## 4. 計ロールへの報告

最終承認をお願いします。

**文書終了**
