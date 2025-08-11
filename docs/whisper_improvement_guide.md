# Whisper文字起こしスクリプトのHuggingFace対応に関する技術改善案

## 現在の主な問題（再確認）

| 項目 | 内容 |
| -------- | ------------------------------------------------------------- |
| 出力が空 | 推論は完了するが、`result["text"]` が空、または `"chunks"` が返らない |
| GPUは使用可能 | `nvidia-smi` 上で空きあり・TorchでもCUDA認識されている |
| モデル構成 | `drewschaub/whisper-large-v3-japanese-4k-steps`（HuggingFace） |
| 問題の推定原因 | `generate_kwargs` の誤用、forced_decoder_idsの未設定、tokenizer未活用など |

## 必要なコード上の改善指示

### 対象ファイル：`transcriber.py`

### A. モデルのロード (`load_model()`)

**現状の問題点**

* `pipeline()` によるロードと `generate_kwargs` の併用は非推奨
* `forced_decoder_ids` や `language` を `pipeline` 経由では正しく設定できない

**修正案（抜粋）**

```python
from transformers import AutoProcessor, WhisperForConditionalGeneration

# モデルとプロセッサをロード
self.processor = AutoProcessor.from_pretrained(self.config.model)
self.model = WhisperForConditionalGeneration.from_pretrained(self.config.model).to(self.config.device)

# 言語とタスクに応じたデコーダ設定
self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
    language=self.config.language,
    task="transcribe"
)
self.model.config.suppress_tokens = []
self.model.config.pad_token_id = self.processor.tokenizer.pad_token_id
```

### B. 推論部分 (`transcribe()` / `transcribe_audio_with_whisper()`)

**修正案（抜粋）**

```python
# 音声読み込み
audio = load_audio(audio_path, sr=16000)

# 特徴量抽出
inputs = self.processor(
    audio,
    sampling_rate=16000,
    return_tensors="pt"
)

# 入力をGPUへ
input_features = inputs.input_features.to(self.config.device)

# attention mask の作成
attention_mask = torch.ones_like(input_features[:, :, 0], dtype=torch.long).to(self.config.device)

# 推論
with torch.no_grad():
    generated_ids = self.model.generate(
        input_features,
        attention_mask=attention_mask,
        max_length=448,
        num_beams=self.config.beam_size,
        temperature=self.config.temperature
    )

# デコード
transcription = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
```

## テスト方針

| テスト項目 | 期待される結果 |
| -------------------- | ----------------------------- |
| GPU使用時の推論 | VRAMが増加し、出力が空でなくなる |
| `result["text"]` の有無 | 空文字でなく、日本語の文が返る |
| attention 警告 | pad_token_id と mask指定で抑制される |
| forced_decoder_ids | 日本語での出力に強制的に切り替わる |

## 確認すべきファイル（全て提供済・OK）

| ファイル名 | 確認済 | コメント |
| ------------------------- | --- | -------------- |
| `transcriber.py` | ✅ | ロード・推論部分ともに修正要 |
| `transcribe_audio.py` | ✅ | 呼び出し元問題なし |
| `chatgpt_help_request.md` | ✅ | 要件明確・分析済み |
| `implementation_notes.md` | ✅ | 要件・制約明確 |

## 次のステップ

1. `transcriber.py`の完全な修正版を生成
2. 修正内容のテスト実行
3. 必要に応じて追加の調整

## 注意事項

- GPUメモリの使用状況を監視
- エラーメッセージの詳細な記録
- 処理時間の計測
- 出力品質の確認 