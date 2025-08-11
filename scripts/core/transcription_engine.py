from typing import Any, List, Dict
import torch
import soundfile as sf
import numpy as np
# from pyannote.audio import Pipeline
from transcriber import WhisperTranscriber, TranscriptionConfig
import os

class TranscriptionError(Exception):
    pass

class TranscriptionEngine:
    def __init__(self, model_name: str, device: str = 'cpu', hf_token: str = None, language: str = 'ja'):
        self.model_name = model_name
        self.device = device
        self.hf_token = hf_token
        self.language = language
        self.whisper_transcriber = None
        # self.diarization_pipeline = None

    def load_model(self):
        try:
            # WhisperTranscriber（transformersベース）をロード
            config = TranscriptionConfig(
                model=self.model_name, 
                device=self.device,
                language=self.language,  # 言語設定を追加
                include_timestamps=True,  # タイムスタンプ機能を確実に有効化
                timestamp_format="absolute"  # 実際の時刻形式でタイムスタンプを表示
            )
            self.whisper_transcriber = WhisperTranscriber(config)
            self.whisper_transcriber.load_model()
            # pyannote.audioの話者分離パイプラインのロード（今回はスキップ）
            # if self.hf_token is None:
            #     raise TranscriptionError("HuggingFaceのアクセストークン(hf_token)が必要です")
            # self.diarization_pipeline = Pipeline.from_pretrained(
            #     "pyannote/speaker-diarization-3.1",
            #     use_auth_token=self.hf_token
            # )
            # self.diarization_pipeline.to(self.device)
        except Exception as e:
            raise TranscriptionError(f"モデルロード失敗: {e}")

    def transcribe(self, audio_path: str, language: str = "ja") -> List[Dict[str, Any]]:
        try:
            # 音声ファイルの読み込み
            # waveform, sr = sf.read(audio_path)
            # 話者分離はスキップ
            # diarization = self.diarization_pipeline(audio_path)
            # WhisperTranscriberで音声全体を文字起こし
            text = self.whisper_transcriber.transcribe(audio_path)
            
            # デバッグ: 修正前のテキストを確認
            print(f"[DEBUG] WhisperTranscriber出力の冒頭:\n{text[:500]}")
            
            # タイムスタンプ修正機能を適用
            if hasattr(self.whisper_transcriber, '_ensure_timestamps_at_line_start'):
                text = self.whisper_transcriber._ensure_timestamps_at_line_start(text)
                print(f"[DEBUG] 修正後のテキストの冒頭:\n{text[:500]}")
            
            return [{
                "start": 0.0,
                "end": None,
                "speaker": "all",
                "text": text
            }]
        except Exception as e:
            raise TranscriptionError(f"推論失敗: {e}") 