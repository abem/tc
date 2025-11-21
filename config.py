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

# ローカル開発環境でのHTTP使用を許可（localhostのみ）
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

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

                # WSL環境対応: localhostリダイレクトを使う手動認証フロー
                # デスクトップアプリの標準的なリダイレクトURIを明示的に設定
                flow.redirect_uri = 'http://localhost:8080/'
                auth_url, _ = flow.authorization_url(prompt='consent')

                print("\n" + "="*70)
                print("Google Drive API 認証")
                print("="*70)
                print("\n【重要】まず以下の設定を確認してください：")
                print("1. https://console.cloud.google.com/apis/credentials/consent を開く")
                print("2. 公開ステータスが「テスト」の場合:")
                print("   → 「テストユーザー」に your-email@gmail.com を追加")
                print("   または「本番環境に公開」をクリック")
                print("\n設定完了後、以下のURLをブラウザで開いて認証してください：")
                print(f"\n{auth_url}\n")
                print("認証後、ブラウザのアドレスバーに表示される完全なURLをコピーしてください")
                print("(例: http://localhost:xxxxx/?code=xxxxx&scope=...)")
                print("="*70)

                redirect_response = input("\nリダイレクトされた完全なURLを貼り付けてEnterを押してください: ").strip()
                flow.fetch_token(authorization_response=redirect_response)
                creds = flow.credentials

                print("\n✅ 認証が完了しました！")
                print("="*70 + "\n")
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
