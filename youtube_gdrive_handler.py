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
        """指定した名前のフォルダをGoogle Drive上で検索"""
        service = self._get_service()
        
        try:
            # 検索クエリを構築
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            files = results.get('files', [])
            if files:
                logger.info(f"フォルダ '{folder_name}' を見つけました: {files[0]['id']}")
                return files[0]['id']
            else:
                logger.info(f"フォルダ '{folder_name}' が見つかりませんでした")
                return None
                
        except Exception as e:
            logger.error(f"フォルダ検索エラー: {e}")
            return None
    
    def _create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Google Drive上にフォルダを作成"""
        service = self._get_service()
        
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_id:
                folder_metadata['parents'] = [parent_id]
            
            folder = service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"フォルダ '{folder_name}' を作成しました: {folder_id}")
            return folder_id
            
        except Exception as e:
            logger.error(f"フォルダ作成エラー: {e}")
            return None
    
    def _find_or_create_base_folder(self) -> Optional[str]:
        """ベースフォルダ「ボイス共有」を見つけるか作成"""
        if self.base_folder_id:
            return self.base_folder_id
            
        # まず「マイドライブ」のルートで検索
        folder_id = self._find_folder_by_name(self.base_folder_name)
        
        if not folder_id:
            # 見つからない場合は作成
            logger.info(f"ベースフォルダ '{self.base_folder_name}' を作成します")
            folder_id = self._create_folder(self.base_folder_name)
        
        self.base_folder_id = folder_id
        return folder_id
    
    def _get_or_create_date_folder(self, youtube_title: str) -> Optional[str]:
        """YY_MM_DD_${youtubeタイトル名}フォルダを取得または作成"""
        base_folder_id = self._find_or_create_base_folder()
        if not base_folder_id:
            logger.error("ベースフォルダの取得/作成に失敗しました")
            return None
        
        # 現在の日付を取得 (YY_MM_DD形式)
        today = datetime.now()
        date_prefix = today.strftime("%y_%m_%d")
        
        # YouTubeタイトルをサニタイズ
        sanitized_title = self._sanitize_folder_name(youtube_title)
        
        # フォルダ名を構築
        folder_name = f"{date_prefix}_{sanitized_title}"
        
        # 既存フォルダを検索
        folder_id = self._find_folder_by_name(folder_name, base_folder_id)
        
        if not folder_id:
            # 見つからない場合は作成
            logger.info(f"日付フォルダ '{folder_name}' を作成します")
            folder_id = self._create_folder(folder_name, base_folder_id)
        
        return folder_id
    
    def upload_transcription_result(
        self, 
        file_path: str, 
        youtube_metadata: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        文字起こし結果をGoogle Driveにアップロード
        
        Args:
            file_path: アップロードするファイルのパス
            youtube_metadata: YouTube動画のメタデータ
            
        Returns:
            アップロード情報の辞書（file_id, file_url等）またはNone
        """
        try:
            # YouTube動画のタイトルを取得
            youtube_title = youtube_metadata.get('title', 'unknown_video')
            video_id = youtube_metadata.get('video_id', 'unknown')
            
            logger.info(f"YouTube動画 '{youtube_title}' の文字起こし結果をアップロード開始")
            
            # 対象フォルダを取得または作成
            target_folder_id = self._get_or_create_date_folder(youtube_title)
            if not target_folder_id:
                logger.error("対象フォルダの取得/作成に失敗しました")
                return None
            
            # ファイル名を決定
            file_name = Path(file_path).name
            
            # ファイルメタデータを構築
            file_metadata = {
                'name': file_name,
                'parents': [target_folder_id],
                'description': f'YouTube動画の文字起こし結果\n'
                             f'動画タイトル: {youtube_title}\n'
                             f'動画ID: {video_id}\n'
                             f'チャンネル: {youtube_metadata.get("channel", "unknown")}\n'
                             f'動画時間: {youtube_metadata.get("duration", 0)}秒\n'
                             f'アップロード日時: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
            }
            
            # ファイルをアップロード
            service = self._get_service()
            
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(
                file_path,
                mimetype='text/plain',
                resumable=True
            )
            
            file_result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            
            file_id = file_result.get('id')
            file_url = file_result.get('webViewLink')
            
            logger.info(f"アップロード完了: {file_name}")
            logger.info(f"ファイルID: {file_id}")
            logger.info(f"ファイルURL: {file_url}")
            
            # YouTube動画の音声ファイルもアップロード（オプション）
            audio_file = youtube_metadata.get('audio_file_path')
            if audio_file and os.path.exists(audio_file):
                self._upload_audio_file(audio_file, target_folder_id, youtube_metadata)
            
            return {
                'file_id': file_id,
                'file_url': file_url,
                'file_name': file_name,
                'folder_id': target_folder_id
            }
            
        except Exception as e:
            logger.error(f"Google Driveアップロードエラー: {e}")
            return None
    
    def _upload_audio_file(
        self, 
        audio_path: str, 
        folder_id: str, 
        youtube_metadata: Dict[str, Any]
    ) -> Optional[str]:
        """音声ファイルもGoogle Driveにアップロード（オプション）"""
        try:
            logger.info("音声ファイルもGoogle Driveにアップロード中...")
            
            audio_name = f"{youtube_metadata.get('title', 'audio')}_{youtube_metadata.get('video_id', 'unknown')}.wav"
            audio_name = self._sanitize_folder_name(audio_name) + ".wav"
            
            audio_metadata = {
                'name': audio_name,
                'parents': [folder_id],
                'description': f'YouTube動画から抽出した音声ファイル\n'
                             f'動画タイトル: {youtube_metadata.get("title", "unknown")}\n'
                             f'動画ID: {youtube_metadata.get("video_id", "unknown")}'
            }
            
            service = self._get_service()
            
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(
                audio_path,
                mimetype='audio/wav',
                resumable=True
            )
            
            audio_result = service.files().create(
                body=audio_metadata,
                media_body=media,
                fields='id, name'
            ).execute()
            
            logger.info(f"音声ファイルアップロード完了: {audio_name}")
            return audio_result.get('id')
            
        except Exception as e:
            logger.warning(f"音声ファイルのアップロードに失敗: {e}")
            return None
    
    def list_youtube_folders(self) -> list:
        """ボイス共有フォルダ内のYouTube関連フォルダ一覧を取得"""
        try:
            base_folder_id = self._find_or_create_base_folder()
            if not base_folder_id:
                return []
            
            service = self._get_service()
            
            # YY_MM_DD_パターンのフォルダを検索
            query = f"'{base_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            results = service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, createdTime, modifiedTime)',
                orderBy='createdTime desc'
            ).execute()
            
            files = results.get('files', [])
            
            # 日付パターンのフォルダのみフィルタ
            youtube_folders = []
            date_pattern = re.compile(r'^\d{2}_\d{2}_\d{2}_')
            
            for file in files:
                if date_pattern.match(file['name']):
                    youtube_folders.append({
                        'id': file['id'],
                        'name': file['name'],
                        'created_time': file['createdTime'],
                        'modified_time': file['modifiedTime']
                    })
            
            logger.info(f"YouTube関連フォルダ数: {len(youtube_folders)}")
            return youtube_folders
            
        except Exception as e:
            logger.error(f"フォルダ一覧取得エラー: {e}")
            return []