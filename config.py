#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path
from typing import Final, Dict, Any
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import yaml
from logger import Logger

# ロガーの設定
logger = Logger.get_logger(__name__)

def get_drive_service(credentials_path: str = "credentials.json", token_path: str = "token.pickle") -> Any:
    """Google Drive APIのサービスを取得"""
    from core.config import UnifiedConfig
    
    creds = None
    
    # トークンファイルが存在する場合は読み込む
    if os.path.exists(token_path):
        try:
            with open(token_path, "rb") as token:
                creds = pickle.load(token)
        except Exception as e:
            if os.path.exists(token_path):
                os.remove(token_path)
                logger.warning(f"無効なトークンを削除しました: {e}")
    
    # 認証情報が無効な場合は再認証
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("認証トークンを更新しました")
            except Exception as e:
                logger.warning(f"トークンの更新に失敗しました: {e}")
                creds = None
        
        if not creds:
            try:
                # UnifiedConfigを使用してスコープを取得
                scopes = UnifiedConfig.get('gdrive', 'scopes', default=['https://www.googleapis.com/auth/drive'])
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
                creds = flow.run_local_server(port=0)
                logger.info("新しい認証情報を取得しました")
                
                # 新しい認証情報を保存
                try:
                    with open(token_path, "wb") as token:
                        pickle.dump(creds, token)
                    logger.info("認証情報を保存しました")
                except Exception as e:
                    logger.warning(f"認証情報の保存に失敗しました: {e}")
            except Exception as e:
                logger.error(f"認証に失敗しました: {e}")
                raise RuntimeError(f"Google Drive APIの認証に失敗しました: {e}")
    
    try:
        service = build("drive", "v3", credentials=creds)
        logger.info("Google Drive APIサービスを初期化しました")
        return service
    except Exception as e:
        logger.error(f"APIサービスの初期化に失敗しました: {e}")
        raise RuntimeError(f"Google Drive APIサービスの初期化に失敗しました: {e}")

# 設定関連
def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """設定ファイルを読み込む"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

# AppConfigクラスは廃止されました。
# UnifiedConfig (core.config.UnifiedConfig) を使用してください。
