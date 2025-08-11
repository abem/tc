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
    
    # 特定の警告メッセージを抑制
    warnings.filterwarnings("ignore", message=".*MPEG_LAYER_III.*")
    warnings.filterwarnings("ignore", message=".*degrees of freedom.*")
    warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")
    warnings.filterwarnings("ignore", message=".*file_cache is only supported.*")
    warnings.filterwarnings("ignore", message=".*bits_per_sample.*")
    
    # ライブラリのログレベルを調整
    logging.getLogger("pyannote.audio").setLevel(logging.ERROR)
    logging.getLogger("speechbrain").setLevel(logging.ERROR)
    logging.getLogger("torchaudio").setLevel(logging.ERROR)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    
    # 環境変数で警告を抑制
    os.environ["PYTHONWARNINGS"] = "ignore"
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# 自動実行
suppress_all_warnings()