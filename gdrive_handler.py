#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path
from typing import Generator, Optional, Dict, Any, Union
import tempfile
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import shutil
from google.oauth2 import service_account

from config import get_drive_service
from core.config import UnifiedConfig
from logger import Logger

logger = Logger.get_logger(__name__)

class DriveError(Exception):
    """Google Drive操作時のエラー"""
    def __init__(self, message: str, error_code: str = "UNKNOWN"):
        self.message = message
        self.error_code = error_code
        super().__init__(f"{error_code}: {message}")

class UploadError(DriveError):
    """アップロード時のエラー"""
    def __init__(self, message: str, error_code: str = "UPLOAD_ERROR"):
        super().__init__(message, error_code)

class DownloadError(DriveError):
    """ダウンロード時のエラー"""
    def __init__(self, message: str, error_code: str = "DOWNLOAD_ERROR"):
        super().__init__(message, error_code)

class GDriveHandler:
    """Google Drive APIを使用してファイルを操作するクラス"""
    
    def __init__(self, credentials_path: str = "credentials.json"):
        """初期化"""
        self.credentials_path = credentials_path
        self.service = get_drive_service()
    
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """ファイルのメタデータを取得"""
        try:
            return self.service.files().get(fileId=file_id, fields="id, name, size, parents").execute()
        except Exception as e:
            logger.error(f"メタデータ取得エラー: {e}")
            raise
    
    def get_parent_folder_id(self, file_id: str) -> Optional[str]:
        """
        指定されたファイルIDの親フォルダIDを取得します。
        ファイルに親が複数ある場合、最初の親IDを返します。
        親が見つからない、またはエラーが発生した場合はNoneを返します。
        """
        try:
            # self.service は __init__ で初期化されているはず
            if not self.service:
                logger.error("Drive service not initialized in GDriveHandler.")
                return None

            file_metadata = self.service.files().get(
                fileId=file_id,
                fields='parents'  # 親フォルダのIDリストを取得
            ).execute()
            
            parents = file_metadata.get('parents')
            if parents:
                logger.info(f"Parent folder ID for {file_id}: {parents[0]}")
                return parents[0]  # 最初の親フォルダIDを返す
            else:
                logger.warning(f"ファイルID {file_id} に親フォルダが見つかりませんでした。")
                return None
        except Exception as e:
            logger.error(f"ファイルID {file_id} の親フォルダID取得中にエラーが発生しました: {e}")
            return None
    
    def stream_file_chunks(self, file_id: str, chunk_size_mb: int = None) -> Generator[bytes, None, None]:
        """ファイルをチャンク単位でストリーミング"""
        if chunk_size_mb is None:
            chunk_size_mb = UnifiedConfig.get('gdrive', 'chunk_size', default=100)
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"ダウンロード進捗: {int(status.progress() * 100)}%")
                
                if fh.getbuffer().nbytes >= chunk_size_mb * 1024 * 1024 or done:
                    fh.seek(0)
                    chunk_data = fh.getvalue()
                    fh = io.BytesIO()
                    yield chunk_data
        
        except Exception as e:
            logger.error(f"ストリーミングエラー: {e}")
            raise
    
    def upload_file(self, file_content: Union[str, Path, io.BytesIO], filename: str, parent_id: Optional[str] = None, mimetype: str = "text/plain") -> str:
        """ファイルをアップロード。ファイルパスまたはio.BytesIOオブジェクトを受け付ける。"""
        try:
            file_metadata = {
                "name": filename,
                "mimeType": mimetype
            }
            if parent_id:
                file_metadata["parents"] = [parent_id]
            
            media_body_content: io.BytesIO | io.FileIO
            if isinstance(file_content, io.BytesIO):
                file_content.seek(0)
                media_body_content = file_content
                logger.info(f"io.BytesIOオブジェクトから直接アップロードします: {filename}")
            elif isinstance(file_content, (str, Path)):
                file_path_obj = Path(file_content)
                if not file_path_obj.is_file():
                    raise FileNotFoundError(f"指定されたファイルパスが見つかりません: {file_path_obj}")
                media_body_content = io.FileIO(str(file_path_obj), "rb")
                logger.info(f"ファイルパスからアップロードします: {file_path_obj}")
            else:
                raise TypeError("file_contentはファイルパス(str/Path)またはio.BytesIOである必要があります")

            media = MediaIoBaseUpload(
                media_body_content,
                mimetype=mimetype,
                resumable=True,
                chunksize=1024*1024
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True
            ).execute()
            
            logger.info(f"ファイルをアップロードしました: {file.get('webViewLink')}")
            return file.get("id")
            
        except Exception as e:
            logger.error(f"アップロードエラー: {str(e)}")
            raise UploadError(f"ファイルのアップロードに失敗: {str(e)}")
    
    def get_file_url(self, file_id: str) -> str | None:
        """ファイルのURLを取得"""
        try:
            file = self.service.files().get(fileId=file_id, fields="webViewLink").execute()
            return file.get("webViewLink")
        except Exception as e:
            logger.error(f"ファイルURL取得エラー: {e}")
            return None
    
    def get_file_path(self, file_id: str) -> str | None:
        """ファイルのパスを取得"""
        try:
            file_metadata = self.get_file_metadata(file_id)
            parents = file_metadata.get('parents', [])
            if not parents:
                return ""  # ルートフォルダの場合
            
            path_components = []
            current_parent_id = parents[0]
            
            while current_parent_id:
                parent_metadata = self.service.files().get(fileId=current_parent_id, fields="id, name, parents").execute()
                name = parent_metadata.get("name", "不明なフォルダ")
                if name != "マイドライブ":  # 重複を防ぐ
                    path_components.insert(0, name)
                parents = parent_metadata.get('parents', [])
                current_parent_id = parents[0] if parents else None
            
            return " ＞ ".join(["マイドライブ"] + path_components)
        except Exception as e:
            logger.error(f"ファイルパス取得エラー: {e}")
            return None

    def download_file(self, file_id: str, output_path: str) -> None:
        """Google Driveからファイルをダウンロード"""
        try:
            request = self.service.files().get_media(fileId=file_id)
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.info(f"ダウンロード進捗: {int(status.progress() * 100)}%")
        except Exception as e:
            logger.error(f"ファイルのダウンロードに失敗しました: {e}")
            raise