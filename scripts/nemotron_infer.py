#!/usr/bin/env python3
"""Nemotron-3.5-ASR-Streaming 単体推論スクリプト(隔離venv専用、生産コード非import)。

`core/nemotron_engine.py` の `NemotronSubprocessEngine` からサブプロセスとして
起動される。標準出力にはJSON1行のみを出力し(`core/nemotron_engine.py`側の
`json.loads(proc.stdout)` がそれを前提としているため)、診断・進捗ログは
すべて標準エラー出力(`sys.stderr`)へ出す。

tc-ops #546 Phase1実測(`WORK_20260926_220529_phase1/nemotron_infer.py`)で
動作確認済みのモデルロード・推論パターンを踏襲する。Phase1版との違いは、
(1) stdoutをJSON1行に限定した点、(2) `--language` 引数を受け付ける点、の2点。

使い方: venv-nemotron-poc/bin/python scripts/nemotron_infer.py <audio_path> [--language ja-JP]
"""
import argparse
import json
import sys
import time


def _log(message: str) -> None:
    """診断・進捗ログは標準エラー出力へ(stdoutはJSON1行専用のため)。"""
    print(message, file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Nemotron-3.5-ASR-Streaming 単体推論")
    parser.add_argument("audio_path", help="音声ファイルのパス")
    parser.add_argument(
        "--language", default="auto",
        help="言語コード(例: ja-JP, en-US)。既定はauto(自動検出)。",
    )
    args = parser.parse_args()

    result = {"audio_path": args.audio_path, "language": args.language}

    try:
        import torch
        from transformers import AutoModelForRNNT, AutoProcessor
        from transformers.audio_utils import load_audio

        model_id = "nvidia/nemotron-3.5-asr-streaming-0.6b"

        _log(f"Loading model: {model_id}")
        t0 = time.time()
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForRNNT.from_pretrained(model_id, device_map="auto")
        load_elapsed = time.time() - t0
        result["load_elapsed_sec"] = load_elapsed
        _log(f"Model loaded in {load_elapsed:.2f}s")

        audio = load_audio(args.audio_path, sampling_rate=processor.feature_extractor.sampling_rate)
        audio_duration_sec = len(audio) / processor.feature_extractor.sampling_rate
        result["audio_duration_sec"] = audio_duration_sec

        language_arg = None if args.language == "auto" else args.language
        inputs = processor(
            audio, sampling_rate=processor.feature_extractor.sampling_rate, language=language_arg
        )
        inputs = inputs.to(model.device, dtype=model.dtype)

        _log("Running inference...")
        t1 = time.time()
        output = model.generate(**inputs, return_dict_in_generate=True)
        infer_elapsed = time.time() - t1
        result["infer_elapsed_sec"] = infer_elapsed
        result["rtf"] = infer_elapsed / audio_duration_sec if audio_duration_sec > 0 else None
        _log(f"Inference completed in {infer_elapsed:.2f}s")

        text = processor.decode(output.sequences, skip_special_tokens=True)
        if isinstance(text, list):
            text = "".join(text)
        result["transcription"] = text

        del model, inputs, output
        torch.cuda.empty_cache()

    except Exception as e:  # noqa: BLE001 - 呼び出し元(core/nemotron_engine.py)へ
        # returncode!=0として異常終了を伝える。詳細はstderrへ出す(stdoutはJSON専用)。
        _log(f"ERROR: {type(e).__name__}: {e}")
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
