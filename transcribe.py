#!/usr/bin/env python3
"""
Transcribe Audio - モダンなCLI音声文字起こしツール
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

# 警告を抑制
import warnings

# 環境変数で警告を抑制
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# すべての警告を抑制
warnings.filterwarnings("ignore")

# ログレベルを設定
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("transformers.generation_utils").setLevel(logging.ERROR)
logging.getLogger("transformers.tokenization_utils_base").setLevel(logging.ERROR)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

# Rich UI
from rich.console import Console
from rich.prompt import Prompt, Confirm

# プロジェクトモジュール
from core.cli_common import (
    build_output_file,
    detect_input_type,
    resolve_device,
    upload_text_to_gdrive_sibling,
)
from core.config import UnifiedConfig, TranscriptionConfig, DiarizationConfig
from core.transcription_interface import UnifiedTranscriber

# 音声処理
from youtube_handler import YouTubeHandler, check_yt_dlp_installed, install_yt_dlp
from youtube_gdrive_handler import YouTubeGDriveHandler
from scripts.core.audio_loader import AudioLoader

console = Console(width=200, soft_wrap=True)

class TranscribeLoader:
    """かっこいいローダークラス"""
    
    def __init__(self):
        self.config_loaded = False
        self.logger = None
        
    def show_banner(self):
        """アプリケーションバナー表示"""
        console.print("Transcribe Audio - AI音声文字起こしツール")
    
    def detect_input_type(self, input_path: str) -> Dict[str, Any]:
        """入力タイプを自動検出"""
        detected = detect_input_type(input_path)
        input_type = detected["type"]
        source = detected["source"]

        if input_type in {"youtube", "gdrive"}:
            return {"type": input_type, "url": source}
        if input_type == "local":
            return {"type": input_type, "path": source}
        return {"type": "unknown", "input": source}
    
    def select_profile(self) -> Dict[str, Any]:
        """プロファイル選択"""
        device = resolve_device("auto")
        
        profiles = {
            "1": {
                "name": "🇯🇵 日本語 (高速)",
                "language": "ja",
                "model": "kotoba-tech/kotoba-whisper-v2.2",
                "device": device
            },
            "2": {
                "name": "🇯🇵 日本語 (高精度・話者分離)",
                "language": "ja",
                "model": "kotoba-tech/kotoba-whisper-v2.2",
                "device": device,
                "diarization": True
            },
            "3": {
                "name": "🇺🇸 English (Fast)",
                "language": "en",
                "model": "openai/whisper-large-v3",
                "device": device
            },
            "4": {
                "name": "🇺🇸 English (High Quality + Diarization)",
                "language": "en",
                "model": "openai/whisper-large-v3",
                "device": device,
                "diarization": True
            },
            "5": {
                "name": "⚙️  カスタム設定",
                "custom": True
            }
        }
        
        # デフォルトプロファイル1を自動選択（確認なし）
        selected = profiles["1"]
        if selected.get("custom"):
            return self.custom_settings()
        
        return selected
    
    def custom_settings(self) -> Dict[str, Any]:
        """カスタム設定"""
        console.print("\n[bold cyan]カスタム設定[/bold cyan]")
        
        language = Prompt.ask("言語", choices=["ja", "en"], default="ja")
        
        # 言語に応じたモデル選択
        if language == "ja":
            model_choices = {
                "1": "kotoba-tech/kotoba-whisper-v2.2 (推奨)",
                "2": "openai/whisper-large-v3",
                "3": "openai/whisper-medium"
            }
        else:
            model_choices = {
                "1": "openai/whisper-large-v3 (推奨)",
                "2": "openai/whisper-medium",
                "3": "openai/whisper-base"
            }
        
        console.print("\n利用可能なモデル:")
        for k, v in model_choices.items():
            console.print(f"  {k}: {v}")
        
        model_choice = Prompt.ask("モデル選択", choices=list(model_choices.keys()), default="1")
        model = model_choices[model_choice].split(" ")[0]
        
        device = Prompt.ask("デバイス", choices=["auto", "cuda", "cpu"], default="auto")
        diarization = Confirm.ask("話者分離を有効にしますか？", default=False)
        
        settings = {
            "language": language,
            "model": model,
            "device": device,
            "diarization": diarization
        }
        
        if diarization:
            max_speakers = Prompt.ask("最大話者数 (空欄で自動)", default="")
            if max_speakers:
                settings["max_speakers"] = int(max_speakers)
        
        return settings
    
    def process_with_progress(self, input_info: Dict[str, Any], settings: Dict[str, Any]):
        """シンプルな処理"""
        try:
            # YouTube処理
            if input_info["type"] == "youtube":
                console.print("YouTube音声ダウンロード中...")
                
                # yt-dlpチェック
                if not check_yt_dlp_installed():
                    console.print("yt-dlpをインストール中...")
                    install_yt_dlp()
                
                # ダウンロード
                youtube_handler = YouTubeHandler(output_dir="output")
                local_audio_path, metadata = youtube_handler.download_audio(input_info["url"])
                
                console.print(f"ダウンロード完了: {metadata.get('title', 'unknown')}")
                is_temp_file = True
            
            # Google Drive処理
            elif input_info["type"] == "gdrive":
                console.print("Google Driveからダウンロード中...")
                audio_loader = AudioLoader()
                local_audio_path = str(audio_loader.load(input_info["url"]))
                is_temp_file = False
                metadata = None
                console.print("ダウンロード完了")
            
            # ローカルファイル
            else:
                local_audio_path = input_info.get("path", input_info.get("input"))
                is_temp_file = False
                metadata = None
            
            # 文字起こし設定
            transcription_config = TranscriptionConfig(
                model=settings["model"],
                language=settings["language"],
                device=resolve_device(settings["device"]),
                show_progress=True  # 元のプログレスバーを使用
            )
            
            diarization_config = None
            if settings.get("diarization"):
                diarization_config = DiarizationConfig(
                    enable_diarization=True,
                    max_speakers=settings.get("max_speakers")
                )
            
            # 文字起こし実行
            console.print("音声文字起こし実行中...")
            transcriber = UnifiedTranscriber(transcription_config, diarization_config)
            
            result = transcriber.transcribe(local_audio_path)
            
            # 結果保存
            self.save_results(result, input_info, settings, metadata)
            
            # クリーンアップ
            if is_temp_file and input_info["type"] == "youtube":
                youtube_handler.cleanup_temp_file(local_audio_path)
            
        except Exception as e:
            console.print(f"エラー: {str(e)}")
            raise
    
    def save_results(self, result, input_info, settings, metadata=None):
        """結果保存"""
        output_file = build_output_file(Path("output"), diarization_enabled=settings.get("diarization", False))
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result.text)
        
        # 結果表示
        console.print("文字起こし完了")
        console.print(f"ローカル保存先: {output_file}")
        
        # Google Driveアップロード
        try:
            if input_info["type"] == "youtube" and metadata:
                console.print("Google Driveにアップロード中...")
                gdrive_handler = YouTubeGDriveHandler()
                upload_result = gdrive_handler.upload_transcription_result(str(output_file), metadata)
                
                if upload_result:
                    full_url = upload_result['file_url']
                    console.print("Google Drive URL:")
                    console.print(f"{full_url}")
                else:
                    console.print("Google Driveアップロードに失敗")
            
            elif input_info["type"] == "gdrive":
                # Google Drive音声ファイルの場合、同じフォルダにアップロード
                console.print("Google Driveにアップロード中...")
                full_url = upload_text_to_gdrive_sibling(output_file, input_info["url"])
                if full_url:
                    console.print("Google Drive URL:")
                    console.print(f"{full_url}")
                else:
                    console.print("Google Driveアップロードに失敗")
                
        except Exception as e:
            console.print(f"Google Driveアップロードエラー: {e}")
    
    def run(self):
        """メイン実行"""
        self.show_banner()
        
        # 設定読み込み
        try:
            UnifiedConfig.load("config/config.yaml")
            console.print("設定ファイルを読み込みました")
        except Exception as e:
            console.print(f"設定ファイルエラー: {e}")
            return 1
        
        # 引数パース
        parser = argparse.ArgumentParser(description="AI音声文字起こしツール")
        parser.add_argument("input", nargs="?", help="音声ファイル、YouTube URL、またはGoogle Drive URL")
        parser.add_argument("--profile", "-p", help="プロファイル番号を直接指定")
        parser.add_argument("--language", "-l", choices=["ja", "en"], help="言語")
        parser.add_argument("--diarization", "-d", action="store_true", help="話者分離を有効化")
        
        args = parser.parse_args()
        
        # 入力取得
        if args.input:
            input_source = args.input
        else:
            # 設定ファイルからデフォルトURLを自動使用
            try:
                default_url = UnifiedConfig.get('gdrive', 'url')
                if default_url:
                    console.print(f"設定ファイルのURLを使用: {default_url}")
                    input_source = default_url
                else:
                    input_source = Prompt.ask("\n🎵 音声ソースを入力してください (URL/ファイルパス)")
            except:
                input_source = Prompt.ask("\n🎵 音声ソースを入力してください (URL/ファイルパス)")
        
        # 入力タイプ検出
        input_info = self.detect_input_type(input_source)
        
        if input_info["type"] == "unknown":
            console.print(f"エラー: 入力を認識できません: {input_source}")
            return 1
        
        # 入力タイプ表示
        type_names = {
            "youtube": "YouTube",
            "gdrive": "Google Drive",
            "local": "ローカルファイル"
        }
        console.print(f"入力タイプ: {type_names[input_info['type']]}")
        
        # プロファイル選択（引数で指定されていない場合）
        if args.profile:
            # TODO: プロファイル番号から設定を取得
            settings = self.select_profile()
        else:
            settings = self.select_profile()
        
        # 引数で上書き
        if args.language:
            settings["language"] = args.language
        if args.diarization:
            settings["diarization"] = True
        
        # 設定表示（確認なし）
        console.print(f"日本語音声文字起こしを開始 (デバイス: {settings['device']})")
        
        # 処理実行
        self.process_with_progress(input_info, settings)
        
        console.print("すべての処理が完了しました")
        return 0

def main():
    """エントリーポイント"""
    loader = TranscribeLoader()
    sys.exit(loader.run())

if __name__ == "__main__":
    main()
