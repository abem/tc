#!/usr/bin/env python3
"""
YouTube動画の文字起こし結果をGoogle Driveにアップロードするハンドラー
"""

import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from config import get_drive_service

logger = logging.getLogger(__name__)


class YouTubeGDriveHandler:
    """YouTube動画の文字起こし結果をGoogle Driveの指定フォルダにアップロードするクラス"""
    
    def __init__(self):
        """初期化"""
        self.service = None
        self.base_folder_name = "ボイス共有"
        self.base_folder_id = None
        
    def _get_service(self):
        """Google Drive APIサービスを取得"""
        if self.service is None:
            try:
                self.service = get_drive_service()
                logger.info("Google Drive APIサービスを初期化しました")
            except Exception as e:
                logger.error(f"Google Drive APIサービスの初期化に失敗: {e}")
                raise
        return self.service
    
    def _sanitize_folder_name(self, title: str) -> str:
        """フォルダ名として使用できるようにタイトルをサニタイズ"""
        # 日本語文字、英数字、一部の記号のみ許可
        sanitized = re.sub(r'[^\w\s\-_\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\u3400-\u4DBF]', '', title)
        # 連続する空白を単一の空白に変換
        sanitized = re.sub(r'\s+', ' ', sanitized)
        # 前後の空白を削除
        sanitized = sanitized.strip()
        # 長すぎる場合は切り詰める（100文字制限）
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        return sanitized
    
    def _find_folder_by_name(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """指定された名前のフォルダを検索"""
        try:
            service = self._get_service()
            query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=10
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            return None
            
        except Exception as e:
            logger.error(f"フォルダ検索エラー: {e}")
            return None
    
    def _create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """新しいフォルダを作成"""
        try:
            service = self._get_service()
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]
            
            folder = service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            return folder.get('id')
            
        except Exception as e:
            logger.error(f"フォルダ作成エラー: {e}")
            return None
    
    def _ensure_base_folder(self) -> Optional[str]:
        """ベースフォルダ（ボイス共有）を確認・作成"""
        if self.base_folder_id:
            return self.base_folder_id
        
        # 既存のフォルダを検索
        self.base_folder_id = self._find_folder_by_name(self.base_folder_name)
        
        # 存在しない場合は作成
        if not self.base_folder_id:
            logger.info(f"'{self.base_folder_name}'フォルダを作成します")
            self.base_folder_id = self._create_folder(self.base_folder_name)
            
        return self.base_folder_id
    
    def upload_transcription_result(self, transcription_file: str, video_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """文字起こし結果をGoogle Driveにアップロード"""
        try:
            # ベースフォルダを確認
            base_folder_id = self._ensure_base_folder()
            if not base_folder_id:
                logger.error("ベースフォルダの作成に失敗しました")
                return None
            
            # 動画タイトルからフォルダ名を生成
            video_title = video_metadata.get('title', 'Untitled')
            folder_name = self._sanitize_folder_name(video_title)
            
            # 動画用のフォルダを検索または作成
            video_folder_id = self._find_folder_by_name(folder_name, base_folder_id)
            if not video_folder_id:
                logger.info(f"動画フォルダ '{folder_name}' を作成します")
                video_folder_id = self._create_folder(folder_name, base_folder_id)
                if not video_folder_id:
                    logger.error("動画フォルダの作成に失敗しました")
                    return None
            
            # ファイル名を生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"transcription_{timestamp}.txt"
            
            # ファイルをアップロード
            service = self._get_service()
            file_metadata = {
                'name': file_name,
                'parents': [video_folder_id]
            }
            
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(
                transcription_file,
                mimetype='text/plain',
                resumable=True
            )
            
            uploaded_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            file_url = uploaded_file.get('webViewLink')
            logger.info(f"文字起こし結果をアップロードしました: {file_url}")
            
            return {
                'file_id': uploaded_file.get('id'),
                'file_url': file_url,
                'folder_name': folder_name,
                'file_name': file_name
            }
            
        except Exception as e:
            logger.error(f"アップロードエラー: {e}")
            return None