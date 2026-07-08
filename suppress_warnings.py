#!/usr/bin/env python3
"""
警告メッセージ抑制の統一設定
"""
import warnings
import logging
import os

def suppress_all_warnings():
    """すべての不要な警告を抑制"""
    
    # Python標準警告を抑制
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    # 特定の警告メッセージを抑制
    warnings.filterwarnings("ignore", message=".*MPEG_LAYER_III.*")
    warnings.filterwarnings("ignore", message=".*degrees of freedom.*")
    warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")
    warnings.filterwarnings("ignore", message=".*file_cache is only supported.*")
    warnings.filterwarnings("ignore", message=".*bits_per_sample.*")
    warnings.filterwarnings("ignore", message=".*PySoundFile failed.*")
    warnings.filterwarnings("ignore", message=".*librosa.*audio_backend.*")

    # サードパーティライブラリのログレベルを ERROR に統一
    # （httpx, urllib3, huggingface_hub の大量 INFO/WARNING ログを抑制）
    _NOISY_LOGGERS = [
        "pyannote.audio",
        "speechbrain",
        "torchaudio",
        "googleapiclient.discovery_cache",
        "transformers",
        "huggingface_hub",
        # huggingface_hub は子ロガーで X-HF-Warning ヘッダーを WARNING 出力するため
        # 親ロガー設定だけでは効かない。具体的な子ロガーも明示的に沈黙させる。
        "huggingface_hub.utils._http",
        "httpx",
        "urllib3",
        "matplotlib",
        "PIL",
        "numba",
        "filelock",
        "sympy",
    ]
    for _name in _NOISY_LOGGERS:
        logging.getLogger(_name).setLevel(logging.ERROR)

    # 環境変数で警告を抑制
    os.environ["PYTHONWARNINGS"] = "ignore"
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

# 自動実行
suppress_all_warnings()