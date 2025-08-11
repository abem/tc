#!/usr/bin/env python3
"""
音声文字起こしシステムのメインCLI
"""
# 警告抑制を最初に実行
import suppress_warnings

import argparse
import sys
import logging
from datetime import datetime
from pathlib import Path

# 新しい統一システムを使用
from core.config import UnifiedConfig, TranscriptionConfig, DiarizationConfig
from core.logging_config import UnifiedLogger
from core.transcription_interface import UnifiedTranscriber

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="音声ファイルの高精度文字起こし（日本語特化）",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "audio_path", 
        help="音声ファイルのパス、Google Drive URL、またはYouTube URL"
    )
    
    parser.add_argument(
        "--model", 
        default=None,
        help="使用するWhisperモデル (指定しない場合は言語に応じて自動選択)"
    )
    
    parser.add_argument(
        "--language", 
        default="ja", 
        choices=["ja", "en"],
        help="言語設定 (ja: 日本語, en: 英語, デフォルト: ja)"
    )
    
    parser.add_argument(
        "--device", 
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="推論デバイス (デフォルト: auto)"
    )
    
    parser.add_argument(
        "--output-dir", 
        default="output",
        help="出力ディレクトリ (デフォルト: output)"
    )
    
    parser.add_argument(
        "--log-level", 
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="ログレベル (デフォルト: INFO)"
    )
    
    parser.add_argument(
        "--no-timestamps", 
        action="store_true",
        help="タイムスタンプを無効化"
    )
    
    parser.add_argument(
        "--timestamp-format", 
        default="elapsed",
        choices=["elapsed", "absolute", "relative"],
        help="タイムスタンプフォーマット (デフォルト: elapsed)"
    )
    
    parser.add_argument(
        "--enable-diarization", 
        action="store_true",
        help="話者分離機能を有効化"
    )
    
    parser.add_argument(
        "--max-speakers", 
        type=int,
        help="最大話者数（話者分離有効時）"
    )
    
    args = parser.parse_args()
    
    # ログ設定
    logger = UnifiedLogger.get_logger(__name__)
    
    # ログファイルの設定
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/transcribe_{timestamp}.log"
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    UnifiedLogger.configure(
        log_level=args.log_level,
        log_file=log_file,
        log_format=log_format
    )
    
    # 設定ファイル読み込み
    try:
        UnifiedConfig.load("config/config.yaml")
        logger.info("設定ファイルを読み込みました")
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗しました: {e}")
        sys.exit(1)
    
    # デバイス自動選択
    if args.device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"デバイス自動選択: {device}")
    else:
        device = args.device
    
    # モデル自動選択（言語に応じて）
    if args.model is None:
        try:
            # config.yamlから言語別デフォルトモデルを取得
            language_models = UnifiedConfig.get('whisper', 'language_models', default={})
            if args.language in language_models:
                selected_model = language_models[args.language]['default']
                logger.info(f"言語 '{args.language}' に対応するモデルを自動選択: {selected_model}")
            else:
                # フォールバック: 英語の場合はopenai/whisper-large-v3、日本語の場合はkotoba
                if args.language == "en":
                    selected_model = "openai/whisper-large-v3"
                else:
                    selected_model = "kotoba-tech/kotoba-whisper-v2.2"
                logger.warning(f"設定ファイルにモデル情報なし。フォールバック: {selected_model}")
        except Exception as e:
            logger.warning(f"モデル自動選択エラー: {e}")
            # 最終フォールバック
            selected_model = "openai/whisper-large-v3" if args.language == "en" else "kotoba-tech/kotoba-whisper-v2.2"
    else:
        selected_model = args.model
        logger.info(f"指定されたモデルを使用: {selected_model}")
    
    # 統一設定システムを使用
    transcription_config = TranscriptionConfig(
        model=selected_model,
        language=args.language,
        device=device,
        include_timestamps=not args.no_timestamps,
        timestamp_format=args.timestamp_format,
        show_progress=True
    )
    
    diarization_config = None
    if args.enable_diarization:
        diarization_config = DiarizationConfig(
            enable_diarization=True,
            max_speakers=args.max_speakers
        )
    
    # 出力ディレクトリ作成
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Google Drive URLまたはローカルファイルの処理
        logger.info(f"文字起こし開始: {args.audio_path}")
        
        # 音声ファイルの取得（Google Drive、YouTube対応）
        import re
        from youtube_handler import YouTubeHandler, check_yt_dlp_installed, install_yt_dlp
        
        # YouTube URLのチェック
        youtube_handler = YouTubeHandler(output_dir=str(output_dir))
        
        if youtube_handler.is_youtube_url(args.audio_path):
            # YouTube URLの場合
            logger.info("YouTube URLを検出")
            
            # yt-dlpがインストールされているかチェック
            if not check_yt_dlp_installed():
                logger.warning("yt-dlpがインストールされていません")
                try:
                    install_yt_dlp()
                except Exception as e:
                    logger.error(f"yt-dlpのインストールに失敗しました: {e}")
                    print("エラー: yt-dlpのインストールに失敗しました。手動でインストールしてください: pip install yt-dlp")
                    sys.exit(1)
            
            try:
                logger.info("YouTube動画から音声を抽出中...")
                local_audio_path, metadata = youtube_handler.download_audio(args.audio_path)
                logger.info(f"音声抽出完了: {local_audio_path}")
                
                # メタデータを表示
                print(f"\n動画タイトル: {metadata.get('title', 'unknown')}")
                print(f"チャンネル: {metadata.get('channel', 'unknown')}")
                print(f"動画時間: {metadata.get('duration', 0)}秒")
                print("")
                
                # 一時ファイルとしてマーク（後で削除するため）
                is_temp_file = True
                
            except Exception as e:
                logger.error(f"YouTube音声抽出エラー: {e}")
                print(f"エラー: YouTube動画から音声を抽出できませんでした: {e}")
                sys.exit(1)
                
        elif re.match(r'^https://drive\.google\.com/', args.audio_path):
            # Google Drive URLの場合、ダウンロード処理
            logger.info("Google Drive URLを検出、ダウンロード中...")
            from scripts.core.audio_loader import AudioLoader
            from scripts.core.storage_handler import GDriveStorageHandler
            
            audio_loader = AudioLoader()
            local_audio_path = str(audio_loader.load(args.audio_path))
            logger.info(f"ダウンロード完了: {local_audio_path}")
            is_temp_file = False
            
        else:
            # ローカルファイルパス
            local_audio_path = args.audio_path
            is_temp_file = False
        
        # 統一トランスクライバーを使用
        transcriber = UnifiedTranscriber(transcription_config, diarization_config)
        
        # 進捗コールバック
        def progress_callback(message):
            logger.info(message)
            print(message)
        
        # 統一インターフェースで文字起こし実行
        transcription_result = transcriber.transcribe(
            local_audio_path,
            progress_callback=progress_callback
        )
        
        # 結果テキストを取得
        result = transcription_result.text
        
        if transcription_result.has_speakers:
            logger.info("話者分離付き文字起こし完了")
            print("話者分離機能を使用しました")
        else:
            logger.info("通常の文字起こし完了")
        
        # 結果保存
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_with_speakers" if args.enable_diarization else ""
        output_file = output_dir / f"{timestamp}_transcription{suffix}.txt"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result)
        
        logger.info(f"文字起こし完了: {output_file}")
        print(f"文字起こし結果を保存しました: {output_file}")
        
        # Google Driveファイルのアップロード処理（必要に応じて）
        if re.match(r'^https://drive\.google\.com/', args.audio_path):
            try:
                logger.info("Google Driveへの結果アップロードを試行中...")
                from scripts.core.output_handler import OutputHandler
                from scripts.core.storage_handler import GDriveStorageHandler
                
                # 元音声ファイルのIDを抽出
                import re
                match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', args.audio_path)
                original_audio_id = match.group(1) if match else None
                
                storage_handler = GDriveStorageHandler()
                output_handler = OutputHandler(storage_handler=storage_handler)
                
                upload_info = output_handler.upload(output_file, original_audio_gdrive_id=original_audio_id)
                if upload_info:
                    logger.info(f"Google Driveアップロード完了: {upload_info.get('file_url', 'URL取得失敗')}")
                    print(f"Google Driveにアップロードしました: {upload_info.get('file_url', 'URL取得失敗')}")
                
            except Exception as upload_error:
                logger.warning(f"Google Driveアップロードに失敗: {upload_error}")
                print(f"注意: Google Driveアップロードに失敗しましたが、ローカルファイルは保存されました")
        
        # YouTube動画の場合はGoogle Driveにアップロード
        if 'metadata' in locals() and youtube_handler.is_youtube_url(args.audio_path):
            try:
                logger.info("YouTube動画の文字起こし結果をGoogle Driveにアップロード中...")
                from youtube_gdrive_handler import YouTubeGDriveHandler
                
                gdrive_handler = YouTubeGDriveHandler()
                
                # メタデータに音声ファイルパスを追加
                metadata['audio_file_path'] = local_audio_path if 'local_audio_path' in locals() else None
                
                upload_result = gdrive_handler.upload_transcription_result(str(output_file), metadata)
                
                if upload_result:
                    logger.info(f"Google Driveアップロード完了")
                    print(f"\n🎉 Google Driveにアップロードしました!")
                    print(f"📁 フォルダ: ボイス共有/{datetime.now().strftime('%y_%m_%d')}_{metadata.get('title', 'unknown')}")
                    print(f"📄 ファイル: {upload_result['file_name']}")
                    print(f"🔗 URL: {upload_result['file_url']}")
                else:
                    logger.warning("Google Driveアップロードに失敗しました")
                    print("⚠️ Google Driveアップロードに失敗しましたが、ローカルファイルは保存されました")
                    
            except Exception as upload_error:
                logger.warning(f"Google Driveアップロード中にエラー: {upload_error}")
                print(f"⚠️ Google Driveアップロードエラー: {upload_error}")
                print("ローカルファイルは正常に保存されました")
        
        # YouTube一時ファイルのクリーンアップ
        if 'is_temp_file' in locals() and is_temp_file and 'local_audio_path' in locals():
            try:
                youtube_handler.cleanup_temp_file(local_audio_path)
            except Exception as cleanup_error:
                logger.warning(f"一時ファイルのクリーンアップに失敗: {cleanup_error}")
        
    except Exception as e:
        logger.error(f"文字起こし処理中にエラーが発生しました: {e}")
        print(f"エラー: {e}")
        
        # エラー時も一時ファイルをクリーンアップ
        if 'is_temp_file' in locals() and is_temp_file and 'local_audio_path' in locals():
            try:
                youtube_handler.cleanup_temp_file(local_audio_path)
            except:
                pass
        
        sys.exit(1)

if __name__ == "__main__":
    main()