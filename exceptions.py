"""
音声文字起こしシステムのカスタム例外定義

このモジュールはプロジェクト全体で使用される例外クラスを統合管理します。
以前は errors.py, exceptions.py, scripts/core/exceptions.py に分散していた定義を統合しました。
"""

from typing import Optional


class TranscriptionError(Exception):
    """音声文字起こし処理に関するベース例外"""
    pass


class ConfigurationError(TranscriptionError):
    """設定関連のエラー"""
    pass


class ModelLoadingError(TranscriptionError):
    """モデル読み込み関連のエラー"""
    pass


class AudioProcessingError(TranscriptionError):
    """音声処理関連のエラー"""
    pass


class DeviceError(TranscriptionError):
    """デバイス関連のエラー（GPU/CPU）"""
    pass


class ValidationError(TranscriptionError):
    """入力検証関連のエラー"""
    pass


# Google Drive関連のエラー（errors.pyから統合）
class DriveError(TranscriptionError):
    """Google Drive操作の基本例外クラス"""
    def __init__(self, message: str, error_code: str, original_error: Optional[Exception] = None, file: str = None, line: int = None):
        self.message = message
        self.error_code = error_code
        self.original_error = original_error
        self.file = file
        self.line = line
        super().__init__(f"[{error_code}] {message} (File: {file}, Line: {line})")


class AuthenticationError(DriveError):
    """認証関連のエラー"""
    pass


class DownloadError(DriveError):
    """ダウンロード関連のエラー"""
    pass


class UploadError(DriveError):
    """アップロード関連のエラー"""
    pass


class DriveServiceError(DriveError):
    """Drive APIサービスエラー"""
    pass


class FileSystemError(DriveError):
    """ファイルシステム関連のエラー"""
    pass


class DriveNotFoundError(DownloadError):
    """ファイルが見つからないエラー"""
    pass


class DrivePermissionError(DownloadError):
    """アクセス権限がないエラー"""
    pass


# scripts/core/exceptions.pyから統合
class AudioLoadError(AudioProcessingError):
    """音声ファイル読み込みエラー"""
    pass


class DriveAPIError(DriveError):
    """Google Drive APIエラー"""
    pass


# エラーコード定義
AUTH_ERROR_CODES = {
    'TOKEN_LOAD_FAILED': 'A001',
    'TOKEN_REFRESH_FAILED': 'A002',
    'NEW_TOKEN_FAILED': 'A003',
    'TOKEN_SAVE_FAILED': 'A004'
}

DOWNLOAD_ERROR_CODES = {
    'API_ERROR': 'D001',
    'UNEXPECTED_ERROR': 'D003',
    'FILE_NOT_FOUND': 'D004',
    'PERMISSION_DENIED': 'D005'
}

UPLOAD_ERROR_CODES = {
    'API_ERROR': 'U001',
    'FILE_READ_ERROR': 'U002',
    'UNEXPECTED_ERROR': 'U003'
}

FILE_ERROR_CODES = {
    'TEMP_FILE_CREATE_ERROR': 'F001',
    'TEMP_FILE_WRITE_ERROR': 'F002',
    'TEMP_FILE_DELETE_ERROR': 'F003'
}