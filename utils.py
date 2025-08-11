from typing import List, Tuple, Optional, Union, Generator
import logging
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm
from core.config import UnifiedConfig
from contextlib import contextmanager
from functools import wraps
import os
import time
from tenacity import retry_if_exception_type, before_sleep_log
from pathlib import Path
import torchaudio
import numpy as np
import torch
from logger import Logger
import re

class LogUtils:
    """ログ設定に関するユーティリティクラス（非推奨: Loggerクラスを利用してください）"""
    
    @staticmethod
    def setup_logger(name: str) -> logging.Logger:
        """ロガーの設定（非推奨: Logger.get_loggerを利用）"""
        return Logger.get_logger(name)

class ProgressUtils:
    """進捗表示に関するユーティリティクラス"""
    
    @staticmethod
    @contextmanager
    def create_progress_bar(desc: str, total: Optional[int]) -> Generator[tqdm, None, None]:
        """プログレスバーの作成"""
        pbar = tqdm(desc=desc, total=total, unit='B', unit_scale=True) if total else tqdm(desc=desc)
        try:
            yield pbar
        finally:
            pbar.close()

class AuthUtils:
    """認証処理に関するユーティリティクラス"""
    
    @staticmethod
    def refresh_token(token_path: Path) -> None:
        """トークンのリフレッシュ"""
        try:
            if token_path.exists():
                token_path.unlink()
        except Exception as e:
            logging.warning(f"トークン削除失敗: {e}")

class RetryUtils:
    """リトライ処理に関するユーティリティクラス"""
    
    @staticmethod
    def retry_decorator():
        """リトライデコレータ"""
        return retry(
            stop=stop_after_attempt(UnifiedConfig.get('MAX_RETRIES', default=3)),
            wait=wait_exponential(multiplier=UnifiedConfig.get('INITIAL_WAIT', default=1), max=UnifiedConfig.get('MAX_WAIT', default=10)),
            retry=retry_if_exception_type((HttpError,)),
            before_sleep=before_sleep_log(Logger.get_logger(__name__), logging.WARNING)
        )

class ChunkUtils:
    """チャンク処理に関するユーティリティクラス"""
    
    @staticmethod
    def process_chunks(chunks: Generator[Path, None, None], process_func: callable) -> Generator[str, None, None]:
        """チャンクの処理"""
        for chunk in chunks:
            try:
                yield process_func(chunk)
            finally:
                if chunk.exists():
                    try:
                        chunk.unlink()
                    except Exception as e:
                        logging.warning(f"チャンクファイル削除失敗: {e}")

class ErrorMessages:
    """エラーメッセージの一元管理クラス"""
    
    # ファイル操作関連
    FILE_NOT_FOUND = "ファイルが見つかりません: {path}"
    FILE_ACCESS_ERROR = "ファイルへのアクセスに失敗しました: {path}"
    FILE_DELETE_ERROR = "ファイルの削除に失敗しました: {path}"
    FILE_CREATE_ERROR = "ファイルの作成に失敗しました: {path}"
    FILE_READ_ERROR = "ファイルの読み込みに失敗しました: {path}"
    FILE_WRITE_ERROR = "ファイルの書き込みに失敗しました: {path}"
    
    # 一時ファイル関連
    TEMP_FILE_DELETE_ERROR = "一時ファイルの削除に失敗しました: {path}"
    TEMP_DIR_DELETE_ERROR = "一時ディレクトリの削除に失敗しました: {path}"
    
    # Google Drive関連
    DRIVE_INIT_ERROR = "Google Driveサービスの初期化に失敗しました"
    DRIVE_NOT_FOUND = "ファイルが見つかりません: {file_id}"
    DRIVE_PERMISSION_ERROR = "アクセス権限がありません: {file_id}"
    DRIVE_UPLOAD_ERROR = "ファイルのアップロードに失敗しました: {file_id}"
    DRIVE_DOWNLOAD_ERROR = "ファイルのダウンロードに失敗しました: {file_id}"
    
    # 文字起こし関連
    TRANSCRIPTION_ERROR = "文字起こし処理に失敗しました: {error}"
    AUDIO_SPLIT_ERROR = "音声ファイルの分割に失敗しました: {error}"
    CHUNK_PROCESS_ERROR = "チャンク処理に失敗しました: {error}"
    
    # 設定関連
    CONFIG_LOAD_ERROR = "設定の読み込みに失敗しました: {error}"
    CONFIG_VALIDATION_ERROR = "設定の検証に失敗しました: {error}"
    
    @classmethod
    def format(cls, message: str, **kwargs) -> str:
        """エラーメッセージをフォーマット
        
        Args:
            message (str): エラーメッセージ
            **kwargs: フォーマットパラメータ
            
        Returns:
            str: フォーマットされたエラーメッセージ
        """
        return message.format(**kwargs)

class ErrorUtils:
    """エラーメッセージに関するユーティリティクラス"""
    
    @staticmethod
    def format_error_message(error_type: str, file_id: str) -> str:
        """エラーメッセージのフォーマット"""
        error_messages = {
            'download_error': f"ダウンロードエラー: {file_id}",
            'upload_error': f"アップロードエラー: {file_id}",
            'transcription_error': f"文字起こしエラー: {file_id}"
        }
        return error_messages.get(error_type, f"不明なエラー: {file_id}")

# カスタム例外クラス
class DriveError(Exception):
    """Google Drive操作の基本エラー"""
    pass

class DriveNotFoundError(DriveError):
    """ファイルが見つからないエラー"""
    pass

class DrivePermissionError(DriveError):
    """アクセス権限がないエラー"""
    pass

class DownloadError(DriveError):
    """ダウンロード関連のエラー"""
    pass

class UploadError(DriveError):
    """アップロード関連のエラー"""
    pass

class FileSystemError(Exception):
    """ファイルシステム関連のエラー"""
    pass

def segment_text(text: str) -> List[str]:
    """テキストをセグメントに分割する関数"""
    return text.split()  # 単純な例として、空白文字で分割

def detect_duplicate_segments(segments: List[str]) -> List[Tuple[int, int]]:
    """連続する同一セグメントのインデックス範囲を検出する関数"""
    duplicate_ranges: List[Tuple[int, int]] = []
    start = 0
    while start < len(segments):
        end = start
        while end + 1 < len(segments) and segments[end] == segments[end + 1]:
            end += 1
        if end > start:
            duplicate_ranges.append((start, end))
            start = end + 1
        else:
            start += 1
    return duplicate_ranges

def suppress_duplicates(segments: List[str], duplicate_ranges: List[Tuple[int, int]], method: str = "merge", threshold: int = 3) -> List[str]:
    """重複セグメントを処理する関数"""
    if method == "merge":
        suppressed_segments = []
        i = 0
        while i < len(segments):
            if any(start <= i <= end for start, end in duplicate_ranges):
                # 重複範囲内
                start, end = next((start, end) for start, end in duplicate_ranges if start <= i <= end)
                suppressed_segments.append(segments[i])
                i = end + 1
            else:
                # 重複範囲外
                suppressed_segments.append(segments[i])
                i += 1
        return suppressed_segments
    elif method == "suppress":
        suppressed_segments = []
        for i, segment in enumerate(segments):
            if not any(start <= i <= end and (end - start + 1) >= threshold for start, end in duplicate_ranges):
                suppressed_segments.append(segment)
        return suppressed_segments
    else:
        return segments

def load_audio(file_path: str, sr: int = 16000) -> np.ndarray:
    """
    音声ファイルを読み込んでnumpy配列として返します。
    Args:
        file_path (str): 音声ファイルのパス
        sr (int): サンプリングレート（デフォルト: 16000）
    Returns:
        np.ndarray: 音声データ
    """
    try:
        waveform, sample_rate = torchaudio.load(file_path)
        # モノラルに変換
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
        # サンプリングレートを変換
        if sample_rate != sr:
            resampler = torchaudio.transforms.Resample(sample_rate, sr)
            waveform = resampler(waveform)
        return waveform.squeeze().numpy()
    except Exception as e:
        logging.error(f"音声ファイルの読み込み中にエラーが発生: {e}")
        raise

def remove_timestamp_tags(text: str) -> str:
    """Whisperの<|数字|>形式のタイムスタンプタグや断片を除去"""
    # 完全なタグ
    text = re.sub(r'<\|\d+(\.\d+)?\|>', '', text)
    # 不完全なタグ断片（例: <, >, <|数字, |数字|>, <|数字| など）
    text = re.sub(r'<\|\d+(\.\d+)?', '', text)
    text = re.sub(r'\|\d+(\.\d+)?\|>', '', text)
    text = re.sub(r'<', '', text)
    text = re.sub(r'>', '', text)
    text = re.sub(r'\|', '', text)
    return text.strip()

def format_timestamp(seconds: float) -> str:
    """秒数を[HH:MM:SS]形式の文字列に変換"""
    total_seconds = int(float(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds_val = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_val:02d}"
