#!/usr/bin/env python3
"""
YouTube動画から音声を抽出するハンドラー
"""

import os
import re
import tempfile
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict
import subprocess
import json

logger = logging.getLogger(__name__)


class YouTubeHandler:
    """YouTube動画の音声抽出を管理するクラス"""
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Args:
            output_dir: 一時ファイルの保存先ディレクトリ
        """
        self.output_dir = output_dir or tempfile.gettempdir()
        self.yt_dlp_path = self._find_yt_dlp()
        
    def _find_yt_dlp(self) -> str:
        """yt-dlpの実行パスを探す"""
        # 仮想環境内を優先的にチェック
        venv_path = Path("venv-clean/bin/yt-dlp")
        if venv_path.exists():
            return str(venv_path)
            
        # システムのyt-dlpをチェック
        try:
            result = subprocess.run(["which", "yt-dlp"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
            
        # 見つからない場合はデフォルト
        return "yt-dlp"
        
    def is_youtube_url(self, url: str) -> bool:
        """URLがYouTubeのものかチェック"""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
            r'(?:https?://)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/[\w-]+',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
        ]
        
        for pattern in youtube_patterns:
            if re.match(pattern, url):
                return True
        return False
        
    def extract_video_info(self, url: str) -> Dict:
        """動画の情報を取得"""
        try:
            cmd = [
                self.yt_dlp_path,
                "--dump-json",
                "--no-playlist",
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                logger.error(f"Failed to get video info: {result.stderr}")
                return {}
                
        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            return {}
            
    def download_audio(self, url: str, output_path: Optional[str] = None) -> Tuple[str, Dict]:
        """
        YouTube動画から音声を抽出してダウンロード
        
        Args:
            url: YouTube動画のURL
            output_path: 出力ファイルパス（指定しない場合は自動生成）
            
        Returns:
            Tuple[音声ファイルパス, メタデータ]
        """
        if not self.is_youtube_url(url):
            raise ValueError(f"無効なYouTube URL: {url}")
            
        # 動画情報を取得
        video_info = self.extract_video_info(url)
        if not video_info:
            raise RuntimeError("動画情報の取得に失敗しました")
            
        video_title = video_info.get('title', 'unknown')
        video_id = video_info.get('id', 'unknown')
        duration = video_info.get('duration', 0)
        
        logger.info(f"動画タイトル: {video_title}")
        logger.info(f"動画時間: {duration}秒")
        
        # 出力ファイル名を生成
        if output_path is None:
            # ファイル名に使えない文字を除去
            safe_title = re.sub(r'[^\w\s-]', '', video_title)
            safe_title = re.sub(r'[-\s]+', '-', safe_title)[:50]
            output_filename = f"{safe_title}_{video_id}.wav"
            output_path = os.path.join(self.output_dir, output_filename)
            
        # yt-dlpコマンドを構築
        cmd = [
            self.yt_dlp_path,
            "-x",  # 音声のみ抽出
            "--audio-format", "wav",  # WAV形式で出力
            "--audio-quality", "0",  # 最高品質
            "--no-playlist",  # プレイリストは無視
            "-o", output_path,  # 出力パス
            "--quiet",  # 静かなモード
            "--no-warnings",  # 警告を表示しない
            "--progress",  # 進捗表示
            url
        ]
        
        try:
            logger.info(f"音声抽出開始: {url}")
            
            # プロセスを実行
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # リアルタイムで進捗を表示
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # 進捗情報をログに記録
                    if "[download]" in output and "%" in output:
                        print(f"\r{output.strip()}", end='', flush=True)
                        
            # プロセスの終了を待つ
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"音声抽出に失敗しました: {stderr}")
                
            # 実際の出力ファイルを確認（yt-dlpが拡張子を追加する場合がある）
            if not os.path.exists(output_path):
                # .wavが追加されている可能性をチェック
                possible_paths = [
                    output_path,
                    output_path + ".wav",
                    output_path.replace(".wav", ".wav.wav")
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        output_path = path
                        break
                else:
                    raise FileNotFoundError(f"出力ファイルが見つかりません: {output_path}")
                    
            logger.info(f"音声抽出完了: {output_path}")
            
            # メタデータを構築
            metadata = {
                'title': video_title,
                'video_id': video_id,
                'duration': duration,
                'url': url,
                'channel': video_info.get('channel', 'unknown'),
                'upload_date': video_info.get('upload_date', 'unknown'),
                'description': video_info.get('description', '')[:500]  # 説明は最初の500文字まで
            }
            
            return output_path, metadata
            
        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlpコマンドが失敗しました: {e}")
            raise RuntimeError(f"音声抽出に失敗しました: {e}")
        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            raise
            
    def cleanup_temp_file(self, file_path: str):
        """一時ファイルを削除"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"一時ファイルを削除しました: {file_path}")
        except Exception as e:
            logger.warning(f"一時ファイルの削除に失敗: {e}")


def check_yt_dlp_installed() -> bool:
    """yt-dlpがインストールされているかチェック"""
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_yt_dlp():
    """yt-dlpをインストール"""
    try:
        logger.info("yt-dlpをインストールしています...")
        subprocess.run(["pip", "install", "yt-dlp"], check=True)
        logger.info("yt-dlpのインストールが完了しました")
    except subprocess.CalledProcessError as e:
        logger.error(f"yt-dlpのインストールに失敗しました: {e}")
        raise