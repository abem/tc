#!/usr/bin/env python3
"""
警告メッセージ抑制の統一設定
"""
import warnings
import logging
import os

def suppress_all_warnings():
    """不要な警告を抑制する。

    設計方針(レビュー指摘 #3/#4/#5 を反映):
    - カテゴリ全体の丸ごと無視は避け、意図したノイズだけを絞る。
      特に RuntimeWarning は librosa/numpy が音声データの NaN/Inf を知らせる
      ためのチャネルでもあるため、丸ごと消さない(異常検知シグナルを残す)。
    - 抑制対象のロガーは「実行時に大量の INFO/WARNING を出すことが分かっている
      もの」に限定する。matplotlib/PIL/filelock 等は本プロジェクトの主用途
      (音声処理)で頻出しないため、プロジェクト全体で黙らせない。
    - このファイルを唯一の抑制設定とし、各モジュールに散らばっていた
      filterwarnings はここに集約する。
    """

    # Python標準警告: FutureWarning/DeprecationWarning は抑制。
    # ※UserWarning/RuntimeWarning は抑制しない(本物の異常シグナルを残す)。
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # 特定の警告メッセージを抑制(ノイズとして知られているもの)
    warnings.filterwarnings("ignore", message=".*MPEG_LAYER_III.*")
    warnings.filterwarnings("ignore", message=".*degrees of freedom.*")
    warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")
    warnings.filterwarnings("ignore", message=".*file_cache is only supported.*")
    warnings.filterwarnings("ignore", message=".*bits_per_sample.*")
    warnings.filterwarnings("ignore", message=".*PySoundFile failed.*")
    warnings.filterwarnings("ignore", message=".*librosa.*audio_backend.*")
    # transformers/torch 系のうるさい個別メッセージ(従来 core/transcription_interface.py
    # に分散していたものをここへ統合 - レビュー指摘 #5)
    warnings.filterwarnings("ignore", message=".*attention_mask.*")
    warnings.filterwarnings("ignore", message=".*pad token.*")
    warnings.filterwarnings("ignore", message=".*weights_only=False.*")

    # 実行時に大量の INFO/WARNING ログを出すノイジーロガーだけを ERROR に下げる。
    # スコープは httpx/urllib3/huggingface_hub 系に限定し、プロジェクト全体の
    # WARNING を握りつぶさない(レビュー指摘 #4)。
    _NOISY_LOGGERS = [
        "pyannote.audio",
        "speechbrain",
        "googleapiclient.discovery_cache",
        "transformers",
        "huggingface_hub",
        # huggingface_hub は X-HF-Warning ヘッダーを子ロガーから WARNING 出力する
        # ため、親ロガー設定だけでは効かない。具体的な子ロガーも明示的に沈黙。
        "huggingface_hub.utils._http",
        "httpx",
        "urllib3",
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