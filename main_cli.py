#!/usr/bin/env python3
"""音声文字起こしシステムのメインCLI。"""

import argparse
import re
import sys
from pathlib import Path

import suppress_warnings  # noqa: F401

from core.cli_common import build_output_file, extract_gdrive_file_id, resolve_device, select_model
from core.config import DiarizationConfig, TranscriptionConfig, UnifiedConfig
from core.logging_config import UnifiedLogger
from core.transcription_interface import UnifiedTranscriber
from scripts.core.audio_loader import AudioLoader
from scripts.core.output_handler import OutputHandler
from scripts.core.storage_handler import GDriveStorageHandler
from youtube_gdrive_handler import YouTubeGDriveHandler
from youtube_handler import YouTubeHandler, check_yt_dlp_installed, install_yt_dlp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="音声ファイルの高精度文字起こし（日本語特化）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("audio_path", help="音声ファイルのパス、Google Drive URL、またはYouTube URL")
    parser.add_argument("--model", default=None, help="使用するWhisperモデル")
    parser.add_argument("--language", default="ja", choices=["ja", "en"], help="言語設定")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"], help="推論デバイス")
    parser.add_argument("--output-dir", default="output", help="出力ディレクトリ")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="ログレベル")
    parser.add_argument("--no-timestamps", action="store_true", help="タイムスタンプを無効化")
    parser.add_argument("--timestamp-format", default="elapsed", choices=["elapsed", "absolute", "relative"], help="タイムスタンプフォーマット")
    parser.add_argument("--enable-diarization", action="store_true", help="話者分離機能を有効化")
    parser.add_argument("--max-speakers", type=int, help="最大話者数（話者分離有効時）")
    return parser


def configure_logging(log_level: str):
    UnifiedLogger.configure(
        log_level=log_level,
        log_file=f"logs/transcribe_main_cli.log",
        log_format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return UnifiedLogger.get_logger(__name__)


def resolve_input_audio(audio_path: str, output_dir: Path, logger):
    youtube_handler = YouTubeHandler(output_dir=str(output_dir))

    if youtube_handler.is_youtube_url(audio_path):
        logger.info("YouTube URLを検出")
        if not check_yt_dlp_installed():
            logger.warning("yt-dlpがインストールされていないためインストールを試行します")
            install_yt_dlp()

        local_audio_path, metadata = youtube_handler.download_audio(audio_path)
        logger.info(f"音声抽出完了: {local_audio_path}")
        print(f"\n動画タイトル: {metadata.get('title', 'unknown')}")
        print(f"チャンネル: {metadata.get('channel', 'unknown')}")
        print(f"動画時間: {metadata.get('duration', 0)}秒\n")
        return local_audio_path, True, metadata, youtube_handler

    if re.match(r"^https://drive\.google\.com/", audio_path):
        logger.info("Google Drive URLを検出、ダウンロードを開始")
        local_audio_path = str(AudioLoader().load(audio_path))
        logger.info(f"ダウンロード完了: {local_audio_path}")
        return local_audio_path, False, None, youtube_handler

    return audio_path, False, None, youtube_handler


def upload_for_gdrive_source(original_audio_url: str, output_file: Path, logger):
    try:
        original_audio_id = extract_gdrive_file_id(original_audio_url)
        output_handler = OutputHandler(storage_handler=GDriveStorageHandler())
        upload_info = output_handler.upload(output_file, original_audio_gdrive_id=original_audio_id)
        if upload_info:
            url = upload_info.get("file_url", "URL取得失敗")
            logger.info(f"Google Driveアップロード完了: {url}")
            print(f"Google Driveにアップロードしました: {url}")
    except Exception as error:
        logger.warning(f"Google Driveアップロードに失敗: {error}")
        print("注意: Google Driveアップロードに失敗しましたが、ローカルファイルは保存されました")


def upload_for_youtube_source(metadata: dict, output_file: Path, logger):
    try:
        gdrive_handler = YouTubeGDriveHandler()
        upload_result = gdrive_handler.upload_transcription_result(str(output_file), metadata)
        if upload_result:
            logger.info("YouTube結果のGoogle Driveアップロード完了")
            print("\nGoogle Driveにアップロードしました")
            print(f"URL: {upload_result['file_url']}")
    except Exception as error:
        logger.warning(f"YouTube結果のGoogle Driveアップロード失敗: {error}")
        print("注意: Google Driveアップロードに失敗しましたが、ローカルファイルは保存されました")


def main():
    args = build_parser().parse_args()
    logger = configure_logging(args.log_level)

    try:
        UnifiedConfig.load("config/config.yaml")
    except Exception as error:
        logger.error(f"設定ファイルの読み込みに失敗しました: {error}")
        sys.exit(1)

    device = resolve_device(args.device)
    selected_model = select_model(args.language, args.model)

    transcription_config = TranscriptionConfig(
        model=selected_model,
        language=args.language,
        device=device,
        include_timestamps=not args.no_timestamps,
        timestamp_format=args.timestamp_format,
        show_progress=True,
    )

    diarization_config = None
    if args.enable_diarization:
        diarization_config = DiarizationConfig(enable_diarization=True, max_speakers=args.max_speakers)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    local_audio_path = None
    is_temp_file = False
    metadata = None
    youtube_handler = None

    try:
        logger.info(f"文字起こし開始: {args.audio_path}")
        local_audio_path, is_temp_file, metadata, youtube_handler = resolve_input_audio(args.audio_path, output_dir, logger)

        transcriber = UnifiedTranscriber(transcription_config, diarization_config)
        transcription_result = transcriber.transcribe(local_audio_path, progress_callback=lambda msg: print(msg))

        output_file = build_output_file(output_dir, diarization_enabled=args.enable_diarization)
        output_file.write_text(transcription_result.text, encoding="utf-8")

        logger.info(f"文字起こし完了: {output_file}")
        print(f"文字起こし結果を保存しました: {output_file}")

        if re.match(r"^https://drive\.google\.com/", args.audio_path):
            upload_for_gdrive_source(args.audio_path, output_file, logger)

        if metadata and youtube_handler and youtube_handler.is_youtube_url(args.audio_path):
            metadata["audio_file_path"] = local_audio_path
            upload_for_youtube_source(metadata, output_file, logger)

    except Exception as error:
        logger.error(f"文字起こし処理中にエラーが発生しました: {error}")
        print(f"エラー: {error}")
        sys.exit(1)

    finally:
        if is_temp_file and local_audio_path and youtube_handler:
            try:
                youtube_handler.cleanup_temp_file(local_audio_path)
            except Exception as cleanup_error:
                logger.warning(f"一時ファイルのクリーンアップに失敗: {cleanup_error}")


if __name__ == "__main__":
    main()
