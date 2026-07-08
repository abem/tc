# 話者分離機能セットアップガイド（2025年版）

## 概要

このシステムでは、pyannote.audio v3.3.2を使用した話者分離機能を完全実装しています。話者分離機能により、複数の話者が含まれる音声から、誰がいつ話したかを自動的に識別し、話者ラベル付きの文字起こし結果を生成できます。

**✅ 完全実装済み機能:**
- 自動話者検出・区間分離
- 言語別モデル自動選択との統合
- 日本語・英語音声での話者分離
- HuggingFace Token自動検出
- エラーハンドリング・フォールバック機能

## 環境要件

### 推奨環境
- **Python**: 3.10以上（pyannote.audio v3.x対応）
- **GPU**: CUDA対応GPU（推奨、CPUでも動作可能）
- **メモリ**: 8GB以上（GPUメモリ 4GB以上推奨）

### 依存ライブラリ（アップデート済み ✅）
```bash
# 現在インストール済み（最新バージョン）
pyannote.audio==3.3.2
pyannote.pipeline==3.0.1
torch==2.7.1
torchaudio==2.7.1
torchvision==0.22.1
```

## セットアップ手順

### 1. ライブラリの確認（完了済み ✅）

すべての依存ライブラリは最新バージョンにアップデート済みです。

```bash
# 仮想環境をアクティベート
source venv-clean/bin/activate

# インストール確認
python -c "import pyannote.audio; print(f'pyannote.audio: {pyannote.audio.__version__}')"
python -c "import torch; print(f'torch: {torch.__version__}')"
```

### 1-1. テスト実行

```bash
# 話者分離機能のテスト
python test_speaker_diarization.py
```

### 2. HuggingFaceトークンの設定

話者分離モデルへのアクセスには、HuggingFaceアクセストークンが必要です。

```bash
# 環境変数に設定
export HUGGINGFACE_TOKEN=hf_your_token_here

# または.envファイルに記載
echo "HUGGINGFACE_TOKEN=hf_your_token_here" >> .env
```

### 3. モデルへのアクセス許可

HuggingFaceのモデルページでアクセス許可を取得：
- [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- "Agree and access repository"をクリック

## 使用方法

> **⚠️ 注意:** 現在の `tc` / `transcribe.py` ランチャーは `--enable-diarization`
> オプションを直接サポートしていません（`main_cli.py` 廃止時に CLI オプションが
> 統合されませんでした）。話者分離を使う場合は、下記「プログラムからの使用」
> (Python API) を利用するか、`transcribe.py` のプロファイル選択 UI
> (プロファイル 2/4 が話者分離対応) を使ってください。
> CLI からの話者分離オプション復活は別PRで計画中です。

### 基本的な使用方法

```bash
# transcribe.py を起動し、プロファイル 2(日本語・話者分離) を選択
./transcribe.py audio_file.wav
# → プロファイル選択プロンプトで "2" を入力

# または Python API から直接呼び出し(下記「プログラムからの使用」参照)
```

### プログラムからの使用

```python
from speaker_diarization import SpeakerAwareTranscriber, DiarizationConfig
from transcriber import TranscriptionConfig

# 設定
transcription_config = TranscriptionConfig(
    model="kotoba-tech/kotoba-whisper-v2.2",
    language="ja",
    device="cuda"
)

diarization_config = DiarizationConfig(
    enable_diarization=True,
    max_speakers=3,
    device="cuda"
)

# 実行
transcriber = SpeakerAwareTranscriber(transcription_config, diarization_config)
transcriber.load_models()
result = transcriber.transcribe_with_speakers("audio_file.wav")
print(result)
```

## 出力形式

話者分離機能を有効にした場合の出力例：

```
[00:00:05] 話者00: こんにちは。今日はお忙しい中、お時間をいただきありがとうございます。
[00:00:12] 話者01: こちらこそ、よろしくお願いします。
[00:00:15] 話者00: 早速ですが、今回のプロジェクトについてお聞かせください。
[00:00:20] 話者01: はい。このプロジェクトは...
```

## 設定オプション

`config/config.yaml`での設定：

```yaml
speaker_diarization:
  enable: false  # 話者分離機能の有効/無効
  model: "pyannote/speaker-diarization-3.1"
  min_speakers: null  # 最小話者数（自動検出）
  max_speakers: null  # 最大話者数（自動検出）
  device: "auto"  # auto/cuda/cpu
  
  # 出力設定
  output_format:
    show_speaker_labels: true  # 話者ラベル表示
    speaker_label_format: "話者{num}"  # 話者ラベル形式
    include_confidence: false  # 信頼度表示
    merge_short_segments: true  # 短い区間をマージ
    min_segment_duration: 0.5  # 最小区間長（秒）
```

## トラブルシューティング

### 1. pyannote.audioが見つからない

```bash
# インストール確認
python -c "import pyannote.audio; print('OK')"

# 再インストール
pip install pyannote.audio --force-reinstall
```

### 2. HuggingFaceトークンエラー

```bash
# トークンの確認
echo $HUGGINGFACE_TOKEN

# モデルアクセス権限の確認
# https://huggingface.co/pyannote/speaker-diarization-3.1 でAgree
```

### 3. CUDA/GPU関連エラー

```bash
# CPUモードで実行 (transcribe.py プロファイル 2 で CPU 指定)
./transcribe.py audio_file.wav --device cpu
# → プロファイル選択プロンプトで "2" を入力

# CUDA確認
python -c "import torch; print(torch.cuda.is_available())"
```

### 4. メモリ不足エラー

```bash
# 短い音声ファイルでテスト
./transcribe.py short_audio.wav
# → プロファイル選択プロンプトで "2" を入力

# CPUモード使用
./transcribe.py audio_file.wav --device cpu
```

## パフォーマンス

### 処理時間の目安
- **短時間音声（1-5分）**: リアルタイム比 0.5-1.0倍
- **中時間音声（10-30分）**: リアルタイム比 1.0-2.0倍
- **長時間音声（1時間以上）**: リアルタイム比 2.0-3.0倍

### メモリ使用量
- **GPU**: 4-8GB VRAM
- **CPU**: 8-16GB RAM

## 制限事項

1. **環境制約**: Python 3.10以上が推奨
2. **モデルサイズ**: 話者分離モデルは大容量（数GB）
3. **処理時間**: 音声長に比例して増加
4. **精度**: ノイズや重複発話で精度が低下する可能性
5. **言語**: 日本語音声で最適化、他言語では精度が変わる可能性

## 今後の改善予定

- [ ] リアルタイム話者分離対応
- [ ] 話者名のカスタマイズ機能
- [ ] 話者分離精度の向上
- [ ] 処理速度の最適化
- [ ] Web UI対応

## サポート

問題が発生した場合：
1. ログファイルを確認: `logs/transcribe_*.log`
2. 依存関係を確認: `pip list | grep pyannote`
3. テスト実行: `python speaker_diarization.py test_audio.wav`