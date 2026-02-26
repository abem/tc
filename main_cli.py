#!/usr/bin/env python3
"""音声文字起こしシステムのメインCLI。"""

import argparse
import sys
from pathlib import Path

import suppress_warnings  # noqa: F401

from core.cli_common import build_output_file, resolve_device, select_model
from core.config import DiarizationConfig, TranscriptionConfig, UnifiedConfig
from core.logging_config import UnifiedLogger
from core.cli_workflow import resolve_input_audio, upload_transcription_result


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
    parser.add_argument("--dry-run", action="store_true", help="入力解決と出力パス確認のみ実行")
    return parser


def configure_logging(log_level: str):
    UnifiedLogger.configure(
        log_level=log_level,
        log_file=f"logs/transcribe_main_cli.log",
        log_format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return UnifiedLogger.get_logger(__name__)


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

    resolution = None

    try:
        logger.info(f"文字起こし開始: {args.audio_path}")
        resolution = resolve_input_audio(
            args.audio_path,
            output_dir,
            ensure_yt_dlp=True,
            on_status=logger.info,
        )

        if resolution.source_type == "youtube" and resolution.metadata:
            print(f"\n動画タイトル: {resolution.metadata.get('title', 'unknown')}")
            print(f"チャンネル: {resolution.metadata.get('channel', 'unknown')}")
            print(f"動画時間: {resolution.metadata.get('duration', 0)}秒\n")

        output_file = build_output_file(output_dir, diarization_enabled=args.enable_diarization)

        if args.dry_run:
            logger.info("ドライラン: 入力解決と出力パスのみ確認")
            print(f"ドライラン: 入力={resolution.local_audio_path}")
            print(f"ドライラン: 出力先={output_file}")
            return

        from core.transcription_interface import UnifiedTranscriber

        transcriber = UnifiedTranscriber(transcription_config, diarization_config)
        transcription_result = transcriber.transcribe(
            resolution.local_audio_path,
            progress_callback=lambda msg: print(msg),
        )

        output_file.write_text(transcription_result.text, encoding="utf-8")

        logger.info(f"文字起こし完了: {output_file}")
        print(f"文字起こし結果を保存しました: {output_file}")

        try:
            if resolution.metadata and resolution.source_type == "youtube":
                resolution.metadata["audio_file_path"] = resolution.local_audio_path
            url = upload_transcription_result(
                source_type=resolution.source_type,
                original_source=resolution.original_source,
                output_file=output_file,
                metadata=resolution.metadata,
            )
            if url:
                logger.info(f"Google Driveアップロード完了: {url}")
                print(f"Google Driveにアップロードしました: {url}")
        except Exception as error:
            logger.warning(f"Google Driveアップロードに失敗: {error}")
            print("注意: Google Driveアップロードに失敗しましたが、ローカルファイルは保存されました")

    except Exception as error:
        logger.error(f"文字起こし処理中にエラーが発生しました: {error}")
        print(f"エラー: {error}")
        sys.exit(1)

    finally:
        if resolution and resolution.is_temp_file and resolution.local_audio_path and resolution.youtube_handler:
            try:
                resolution.youtube_handler.cleanup_temp_file(resolution.local_audio_path)
            except Exception as cleanup_error:
                logger.warning(f"一時ファイルのクリーンアップに失敗: {cleanup_error}")


if __name__ == "__main__":
    main()
