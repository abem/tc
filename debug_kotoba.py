#!/usr/bin/env python3
"""
kotoba-whisper-v2.2モデルのデバッグツール
トークン情報、セグメント情報、アテンション等の詳細情報を確認
"""

import os
import sys
import torch
import warnings
from pathlib import Path
from typing import Dict, Any, List
import tempfile

# プロジェクトルートをPATHに追加
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import TranscriptionConfig
from core.transcription_interface import WhisperTranscriptionEngine
from gdrive_handler import GDriveHandler
from logger import Logger

# ロガー設定
logger = Logger.get_logger(__name__)

def debug_model_info(engine: WhisperTranscriptionEngine):
    """モデルの詳細情報をデバッグ"""
    print("\n=== モデル情報 ===")
    print(f"モデル名: {engine.config.model}")
    print(f"言語: {engine.config.language}")
    print(f"デバイス: {engine.config.device}")

    # モデルロード
    engine._load_model()

    print(f"モデルクラス: {type(engine._model).__name__}")
    print(f"プロセッサークラス: {type(engine._processor).__name__}")

    # モデル設定情報
    if hasattr(engine._model, 'config'):
        config = engine._model.config
        print(f"モデル設定:")
        print(f"  - vocab_size: {getattr(config, 'vocab_size', 'N/A')}")
        print(f"  - max_length: {getattr(config, 'max_length', 'N/A')}")
        print(f"  - decoder_layers: {getattr(config, 'decoder_layers', 'N/A')}")
        print(f"  - d_model: {getattr(config, 'd_model', 'N/A')}")

        # 日本語対応確認
        if hasattr(config, 'task_to_id'):
            print(f"  - サポートタスク: {config.task_to_id}")
        if hasattr(config, 'lang_to_id'):
            ja_support = 'ja' in getattr(config, 'lang_to_id', {})
            print(f"  - 日本語サポート: {ja_support}")

def debug_tokenizer_info(engine: WhisperTranscriptionEngine):
    """トークナイザーの詳細情報をデバッグ"""
    print("\n=== トークナイザー情報 ===")

    # トークナイザー取得
    tokenizer = engine._processor.tokenizer if hasattr(engine._processor, 'tokenizer') else None

    if tokenizer:
        print(f"トークナイザークラス: {type(tokenizer).__name__}")
        print(f"語彙サイズ: {tokenizer.vocab_size}")

        # 日本語トークンのテスト
        test_texts = ["こんにちは", "会議の議事録", "音声文字起こし", "Hello", "meeting"]

        print("\n日本語・英語トークン化テスト:")
        for text in test_texts:
            try:
                tokens = tokenizer.encode(text)
                decoded = tokenizer.decode(tokens)
                print(f"  '{text}' -> {len(tokens)}トークン -> '{decoded}'")
            except Exception as e:
                print(f"  '{text}' -> エラー: {e}")
    else:
        print("トークナイザーが見つかりません")

def debug_transcription_with_details(engine: WhisperTranscriptionEngine, audio_path: str):
    """詳細な文字起こし情報をデバッグ"""
    print("\n=== 詳細文字起こしデバッグ ===")

    import soundfile as sf
    import numpy as np

    # 音声ファイルの基本情報
    audio, sr = sf.read(audio_path)
    duration = len(audio) / sr
    print(f"音声ファイル情報:")
    print(f"  - 長さ: {duration:.2f}秒")
    print(f"  - サンプリングレート: {sr}Hz")
    print(f"  - チャンネル数: {1 if len(audio.shape) == 1 else audio.shape[1]}")

    # モデルロード
    engine._load_model()

    # 短いセグメントで詳細テスト（最初の10秒）
    test_duration = min(10.0, duration)
    test_samples = int(test_duration * sr)
    test_audio = audio[:test_samples]

    print(f"\nテストセグメント（最初の{test_duration}秒）を処理中...")

    # 前処理
    if len(test_audio.shape) > 1:
        test_audio = np.mean(test_audio, axis=1)

    # リサンプリング
    if sr != 16000:
        try:
            import resampy
            test_audio = resampy.resample(test_audio, sr, 16000)
        except ImportError:
            import scipy.signal
            test_audio = scipy.signal.resample(test_audio, int(len(test_audio) * 16000 / sr))
        sr = 16000

    # モデルに入力
    inputs = engine._processor(
        test_audio,
        sampling_rate=sr,
        return_tensors="pt"
    ).to(engine.config.device)

    print(f"入力形状: {inputs.input_features.shape}")

    # デコーダープロンプト
    forced_decoder_ids = engine._processor.get_decoder_prompt_ids(
        language=engine.config.language, task="transcribe"
    )
    print(f"デコーダープロンプトID: {forced_decoder_ids}")

    # 推論実行（詳細情報付き）
    with torch.no_grad(), warnings.catch_warnings():
        warnings.simplefilter("ignore")

        # return_dict=Trueで詳細情報を取得
        outputs = engine._model.generate(
            inputs.input_features,
            forced_decoder_ids=forced_decoder_ids,
            max_new_tokens=100,
            do_sample=False,
            temperature=0.0,
            return_dict_in_generate=True,
            output_scores=True,
            output_attentions=True
        )

    # 生成されたトークンID
    generated_ids = outputs.sequences
    print(f"生成トークンID形状: {generated_ids.shape}")
    print(f"生成トークンID: {generated_ids[0].tolist()[:20]}...")  # 最初の20トークンのみ表示

    # デコード
    text = engine._processor.batch_decode(
        generated_ids,
        skip_special_tokens=True
    )[0]

    print(f"デコード結果: '{text}'")

    # スコア情報（利用可能な場合）
    if hasattr(outputs, 'scores') and outputs.scores:
        print(f"スコア情報: {len(outputs.scores)}ステップ")
        # 最初のステップの確信度トップ5
        first_scores = outputs.scores[0][0]  # [batch_size, vocab_size]
        top_scores, top_indices = torch.topk(first_scores, 5)
        print("最初のトークンの確信度トップ5:")
        for i, (score, idx) in enumerate(zip(top_scores, top_indices)):
            try:
                token_text = engine._processor.tokenizer.decode([idx])
                print(f"  {i+1}. {token_text} (スコア: {score.item():.4f})")
            except:
                print(f"  {i+1}. Token#{idx} (スコア: {score.item():.4f})")

    # アテンション情報
    if hasattr(outputs, 'attentions') and outputs.attentions:
        print(f"アテンション情報: {len(outputs.attentions)}レイヤー")

def main():
    """メイン処理"""
    print("kotoba-whisper-v2.2 詳細デバッグツール")
    print("=" * 50)

    # 設定
    config = TranscriptionConfig(
        model="kotoba-tech/kotoba-whisper-v2.2",
        language="ja",
        device="cuda" if torch.cuda.is_available() else "cpu"
    )

    # エンジン作成
    engine = WhisperTranscriptionEngine(config)

    # モデル情報デバッグ
    debug_model_info(engine)
    debug_tokenizer_info(engine)

    # 音声ファイルの準備（config.yamlから取得）
    import yaml
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        yaml_config = yaml.safe_load(f)

    gdrive_url = yaml_config.get('gdrive', {}).get('url')
    if not gdrive_url:
        print("❌ config.yamlにGDriveのURLが設定されていません")
        return

    # Google Driveからダウンロード
    print(f"\n音声ファイルをダウンロード中: {gdrive_url}")
    handler = GDriveHandler()
    file_id = gdrive_url.split('/file/d/')[1].split('/')[0]

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    handler.download_file(file_id, tmp_path)

    try:
        # 詳細文字起こしデバッグ
        debug_transcription_with_details(engine, tmp_path)
    finally:
        # 一時ファイル削除
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    print("\n✅ デバッグ完了")

if __name__ == "__main__":
    main()