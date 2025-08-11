#!/usr/bin/env python3
"""
話者分離機能（Speaker Diarization）
pyannote.audioを使用した話者識別と区間分離
"""
# 警告抑制を最初に実行
import suppress_warnings

import torch
import soundfile as sf
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from dataclasses import dataclass
import os

try:
    from pyannote.audio import Pipeline
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False
    Pipeline = None

# 統一システムを使用
from core.config import TranscriptionConfig, DiarizationConfig
from core.logging_config import UnifiedLogger
from transcriber import WhisperTranscriber

class SpeakerDiarizer:
    """話者分離クラス"""
    
    def __init__(self, config: DiarizationConfig):
        self.config = config
        self.logger = UnifiedLogger.get_logger(__name__)
        self.pipeline = None
        self._validate_environment()
    
    def _validate_environment(self):
        """環境の検証"""
        if not PYANNOTE_AVAILABLE:
            self.logger.warning("pyannote.audioが利用できません。話者分離機能は無効化されます")
            self.config.enable_diarization = False
            return
        
        # HuggingFaceトークンの確認
        if not self.config.hf_token:
            # 環境変数から取得
            self.config.hf_token = os.environ.get("HUGGINGFACE_TOKEN")
            
            # HuggingFace CLIトークンファイルから取得
            if not self.config.hf_token:
                try:
                    from pathlib import Path
                    hf_home = os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")
                    token_file = Path(hf_home) / "token"
                    if token_file.exists():
                        with open(token_file, 'r') as f:
                            self.config.hf_token = f.read().strip()
                        self.logger.info("HuggingFace CLIトークンを読み込みました")
                except Exception as e:
                    self.logger.debug(f"HuggingFace CLIトークン読み込みエラー: {e}")
        
        if not self.config.hf_token and self.config.enable_diarization:
            self.logger.warning("HUGGINGFACE_TOKENが設定されていません。話者分離機能は無効化されます")
            self.config.enable_diarization = False
    
    def load_model(self):
        """話者分離モデルのロード"""
        if not self.config.enable_diarization:
            self.logger.info("話者分離機能は無効化されています")
            return
        
        try:
            self.logger.info(f"話者分離モデルをロード中: {self.config.model}")
            
            # pyannote.audioのバージョンに応じた処理
            try:
                # v3.x系の場合
                self.pipeline = Pipeline.from_pretrained(
                    self.config.model,
                    use_auth_token=self.config.hf_token
                )
            except TypeError:
                # v2.x系以前の場合
                try:
                    self.pipeline = Pipeline.from_pretrained(
                        self.config.model,
                        use_auth_token=self.config.hf_token
                    )
                except Exception as e:
                    self.logger.error(f"旧バージョンのpyannote.audioでのロードに失敗: {e}")
                    raise
            
            # デバイス設定
            if torch.cuda.is_available() and self.config.device == "cuda":
                self.pipeline.to(torch.device("cuda"))
            
            self.logger.info("話者分離モデルのロードが完了しました")
            
        except Exception as e:
            error_msg = f"話者分離モデルのロードに失敗: {str(e)}"
            self.logger.error(error_msg)
            self.config.enable_diarization = False
            raise RuntimeError(error_msg)
    
    def diarize(self, audio_path: str) -> List[Dict[str, Any]]:
        """音声ファイルの話者分離実行
        
        Args:
            audio_path: 音声ファイルのパス
            
        Returns:
            話者区間のリスト [{"start": float, "end": float, "speaker": str}, ...]
        """
        if not self.config.enable_diarization or not self.pipeline:
            self.logger.info("話者分離が無効化されているため、全体を1つの話者として処理します")
            # 音声ファイルの長さを取得
            try:
                audio, sr = sf.read(audio_path)
                duration = len(audio) / sr
                return [{"start": 0.0, "end": duration, "speaker": "SPEAKER_00"}]
            except Exception as e:
                self.logger.warning(f"音声ファイルの長さ取得に失敗: {e}")
                return [{"start": 0.0, "end": None, "speaker": "SPEAKER_00"}]
        
        try:
            self.logger.info(f"話者分離を実行中: {audio_path}")
            
            # pyannote.audioで話者分離実行
            diarization = self.pipeline(audio_path)
            
            # 結果を標準形式に変換
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append({
                    "start": float(turn.start),
                    "end": float(turn.end),
                    "speaker": speaker
                })
            
            self.logger.info(f"話者分離完了: {len(segments)}個の区間, {len(set(seg['speaker'] for seg in segments))}人の話者")
            return segments
            
        except Exception as e:
            error_msg = f"話者分離の実行中にエラー: {str(e)}"
            self.logger.error(error_msg)
            # エラー時はフォールバック
            return [{"start": 0.0, "end": None, "speaker": "SPEAKER_00"}]

class SpeakerAwareTranscriber:
    """話者分離統合文字起こしクラス"""
    
    def __init__(self, transcription_config: TranscriptionConfig, diarization_config: DiarizationConfig):
        self.transcription_config = transcription_config
        self.diarization_config = diarization_config
        self.logger = UnifiedLogger.get_logger(__name__)
        
        # コンポーネント初期化
        self.diarizer = SpeakerDiarizer(diarization_config)
        self.transcriber = WhisperTranscriber(transcription_config)
    
    def load_models(self):
        """全モデルのロード"""
        self.logger.info("話者分離統合文字起こしモデルをロード中...")
        
        # 話者分離モデルロード
        self.diarizer.load_model()
        
        # 文字起こしモデルロード
        self.transcriber.load_model()
        
        self.logger.info("全モデルのロードが完了しました")
    
    def transcribe_with_speakers(self, audio_path: str) -> str:
        """話者分離付き文字起こし実行
        
        Args:
            audio_path: 音声ファイルのパス
            
        Returns:
            話者ラベル付きの文字起こし結果
        """
        try:
            # 1. 話者分離実行
            speaker_segments = self.diarizer.diarize(audio_path)
            
            if not self.diarization_config.enable_diarization:
                # 話者分離が無効の場合は通常の文字起こし
                self.logger.info("話者分離無効 - 通常の文字起こしを実行")
                return self.transcriber.transcribe(audio_path)
            
            # 2. 各話者区間ごとに文字起こし
            results = []
            audio, sr = sf.read(audio_path)
            
            for i, segment in enumerate(speaker_segments):
                try:
                    start_time = segment["start"]
                    end_time = segment["end"]
                    speaker = segment["speaker"]
                    
                    # 音声区間の切り出し
                    start_sample = int(start_time * sr)
                    end_sample = int(end_time * sr) if end_time else len(audio)
                    
                    if start_sample >= len(audio):
                        continue
                    
                    segment_audio = audio[start_sample:end_sample]
                    
                    if len(segment_audio) < sr * 0.5:  # 0.5秒未満は無視
                        continue
                    
                    # 一時ファイルに保存
                    temp_path = f"/tmp/temp_segment_{i}_{speaker}.wav"
                    sf.write(temp_path, segment_audio, sr)
                    
                    try:
                        # 文字起こし実行
                        segment_text = self.transcriber.transcribe(temp_path)
                        
                        if segment_text.strip():
                            # タイムスタンプとスピーカーラベルを追加
                            formatted_time = self._format_timestamp(start_time)
                            speaker_label = self._format_speaker_label(speaker)
                            results.append(f"{formatted_time} {speaker_label}: {segment_text.strip()}")
                    
                    finally:
                        # 一時ファイル削除
                        if Path(temp_path).exists():
                            Path(temp_path).unlink()
                            
                except Exception as e:
                    self.logger.error(f"区間 {i} の処理中にエラー: {e}")
                    continue
            
            return "\n".join(results) if results else "文字起こし結果がありません"
            
        except Exception as e:
            error_msg = f"話者分離付き文字起こし中にエラー: {str(e)}"
            self.logger.error(error_msg)
            # フォールバック: 通常の文字起こし
            self.logger.info("フォールバック: 通常の文字起こしを実行")
            return self.transcriber.transcribe(audio_path)
    
    def _format_timestamp(self, seconds: float) -> str:
        """タイムスタンプのフォーマット"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    def _format_speaker_label(self, speaker: str) -> str:
        """話者ラベルのフォーマット"""
        # SPEAKER_XX -> 話者XX の形式に変換
        if speaker.startswith("SPEAKER_"):
            speaker_num = speaker.replace("SPEAKER_", "")
            return f"話者{speaker_num}"
        return speaker

# 使用例とテスト関数
def test_speaker_diarization(audio_path: str):
    """話者分離のテスト"""
    logger = UnifiedLogger.get_logger(__name__)
    logger.info("話者分離機能のテストを開始")
    
    # 設定
    transcription_config = TranscriptionConfig(
        model="kotoba-tech/kotoba-whisper-v2.2",
        language="ja",
        device="cuda" if torch.cuda.is_available() else "cpu",
        include_timestamps=True
    )
    
    diarization_config = DiarizationConfig(
        enable_diarization=True,
        device="cuda" if torch.cuda.is_available() else "cpu"
    )
    
    # 統合文字起こし実行
    transcriber = SpeakerAwareTranscriber(transcription_config, diarization_config)
    
    try:
        transcriber.load_models()
        result = transcriber.transcribe_with_speakers(audio_path)
        
        logger.info("話者分離付き文字起こし完了")
        print("\n=== 話者分離付き文字起こし結果 ===")
        print(result)
        print("=" * 50)
        
        return result
        
    except Exception as e:
        logger.error(f"テスト中にエラー: {e}")
        return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_speaker_diarization(sys.argv[1])
    else:
        print("使用方法: python speaker_diarization.py <音声ファイルパス>")