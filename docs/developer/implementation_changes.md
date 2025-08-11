# Whisper実装改善計画書

## 1. 変更方針

現在の`pipeline()`ベースの実装から、`AutoProcessor` + `WhisperForConditionalGeneration`を使用する実装に完全移行します。

### 移行の理由
1. 言語指定の確実な反映（forced_decoder_idsの使用）
2. attention mask警告の解消
3. 空の出力問題の解決
4. より詳細な制御が可能

## 2. 具体的な変更内容

### 2.1 transcriber.pyの変更

```python
from transformers import (
    AutoProcessor,
    WhisperForConditionalGeneration
)

class WhisperTranscriber:
    def load_model(self):
        if self.model is not None:
            return

        try:
            if self.config.device == "cuda":
                torch.cuda.empty_cache()
                gc.collect()

            # プロセッサとモデルを個別にロード
            self.processor = AutoProcessor.from_pretrained(self.config.model)
            self.model = WhisperForConditionalGeneration.from_pretrained(
                self.config.model
            ).to(self.config.device)

            # 言語とタスクを明示的に設定
            self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
                language=self.config.language,
                task="transcribe"
            )
            
            # 不要なトークン抑制を解除
            self.model.config.suppress_tokens = []
            
            # パディングトークンを正しく設定
            self.model.config.pad_token_id = self.processor.tokenizer.pad_token_id

            logger.info(f"モデルを正常にロードしました: {self.config.model}")
            
        except Exception as e:
            logger.error(f"モデルのロード中にエラーが発生: {str(e)}")
            raise

    def transcribe(self, audio_array: np.ndarray) -> str:
        try:
            # 入力特徴量の生成
            input_features = self.processor(
                audio_array,
                sampling_rate=16000,
                return_tensors="pt"
            ).input_features.to(self.config.device)

            # attention maskの明示的な生成
            attention_mask = torch.ones(
                input_features.shape[:2],
                dtype=torch.long
            ).to(self.config.device)

            # 推論実行
            with torch.no_grad():
                generated_ids = self.model.generate(
                    input_features,
                    attention_mask=attention_mask,
                    max_length=448,
                    num_beams=self.config.beam_size,
                    temperature=self.config.temperature,
                    output_attentions=False  # SDPAの警告を抑制
                )

            # 結果のデコード
            transcription = self.processor.batch_decode(
                generated_ids,
                skip_special_tokens=True
            )[0]

            return transcription.strip()

        except Exception as e:
            logger.error(f"文字起こし中にエラーが発生: {str(e)}")
            raise
```

### 2.2 transcribe_audio.pyの変更

```python
def transcribe_audio_with_whisper(audio_path: str, config: TranscriptionConfig) -> str:
    transcriber = WhisperTranscriber(config)
    transcriber.load_model()

    try:
        # 音声データをロード
        audio_data = load_audio(audio_path)
        
        # 文字起こしを実行
        transcription = transcriber.transcribe(audio_data)
        
        if not transcription.strip():
            logger.warning("文字起こし結果が空でした")
            
        return transcription

    except Exception as e:
        logger.error(f"文字起こし処理中にエラーが発生: {str(e)}")
        raise
```

## 3. 実装の検証ポイント

1. **モデルのロード**
   - forced_decoder_idsが正しく設定されているか
   - pad_token_idが正しく設定されているか
   - GPUメモリの使用量が適切か（2.88GB以下）

2. **文字起こし処理**
   - attention mask警告が出ないか
   - 出力が空にならないか
   - 日本語の文字起こしが正しく行われるか

3. **エラー処理**
   - 適切なエラーログが出力されるか
   - 例外が適切にハンドリングされているか

## 4. 今後の拡張計画

1. **音声の分割処理**
   - 長時間音声に対応するためのチャンク処理の実装
   - チャンク間の文脈を考慮した結合処理

2. **パフォーマンス最適化**
   - バッチ処理の導入
   - 並列処理の検討

3. **品質向上**
   - ビームサーチパラメータの最適化
   - 温度パラメータの調整

## 5. 移行手順

1. 新実装のブランチを作成
2. テストケースの作成
3. 実装の変更
4. テストの実行と検証
5. レビュー
6. マージ 