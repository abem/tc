#!/usr/bin/env python3
"""Nemotron-3.5-ASR-Streaming 単体推論スクリプト(隔離venv専用、生産コード非import)。

`core/nemotron_engine.py` の `NemotronSubprocessEngine` からサブプロセスとして
起動される。標準出力にはJSON1行のみを出力し(`core/nemotron_engine.py`側の
`json.loads(proc.stdout)` がそれを前提としているため)、診断・進捗ログは
すべて標準エラー出力(`sys.stderr`)へ出す。

使い方: venv-nemotron/bin/python scripts/nemotron_infer.py <audio_path> [<audio_path> ...] \
    [--language ja-JP] [--device auto|cuda|cpu]

## 複数音声ファイル(チャンク)を1プロセス・1モデルロードで処理する(tc-ops #546/#548是正)

音声パスを可変長引数(`nargs="+"`)で受け取り、モデルを**1回だけ**ロードして
全ファイルをループ処理する。出力JSONは常に`{"chunks": [{...}, {...}, ...]}`形式
(1ファイルのみでも要素数1のchunks配列)。

**経緯**: 当初はチャンクごとに本スクリプトを新規プロセスとして起動する設計
だったが、`main()`が呼び出しごとに`AutoModelForRNNT.from_pretrained()`から
モデルを再ロードするため、チャンク数に比例してロード時間(実測5.6〜27.8秒/回)が
累積し、重大な性能劣化を招いた(実測: チャンク分割後62.5秒、分割前19.5秒)。
本設計により、モデルロードはプロセス全体で1回のみとなる。

各チャンクの推論後には明示的に`torch.cuda.empty_cache()`を呼ぶ(1プロセス内で
複数チャンクを処理する分、チャンクごとの一時的なアクティベーションメモリを
都度解放し、チャンク数に応じたVRAM累積を防ぐ、査sa指摘対応)。

1チャンクの処理が失敗しても、そのチャンクの`chunks`エントリに`"error"`キーを
入れて後続チャンクの処理を継続する(呼び出し元`core/nemotron_engine.py`が
これを検知して`[チャンクN失敗]`プレースホルダへ変換する設計)。モデルロード
自体の失敗など、全チャンク処理不能な異常はプロセス全体の異常終了(returncode=1)
として扱う。

## 不具合是正の記録(tc-ops #546、2026-09-26)

**言語自動判定でのTypeError**: 旧実装は `--language auto` を独自にPython `None`
へ変換してから `processor(..., language=None)` を呼んでいた。しかし
`transformers==5.17.0` の実ソース(`processing_nemotron3_5_asr.py`
`_resolve_prompt_ids()`)を確認したところ、`language` 引数は
`isinstance(language, str)` で文字列かどうかを判定しており、`None` を渡すと
`len(None)` に到達して `TypeError: object of type 'NoneType' has no len()`
になる(本番で実際に発生したエラーと文言完全一致、裏取り確認済み)。
`DEFAULT_PROMPT_DICTIONARY` には `"auto": 101` が実在し、`__call__()` の
`language` 引数の既定値も文字列 `"auto"` である。したがって**文字列
"auto" をそのまま渡す**のが正しい使い方であり、独自のNone変換は誤りだった。
本スクリプトはこの変換を行わない(`resolve_processor_language()` 参照)。

**デバイス指定が無視される疑い**: 旧実装は `device_map="auto"` に固定されており、
`--device cpu` 相当の指定を渡す経路自体が存在しなかった。実運用比較
(変換履歴#70: device=cpu指定で327秒音声を33.2秒処理、#71: GPU実行で19.5秒。
cpu指定時の処理時間がGPU実行と同水準であり、cpu指定が無視されていた疑いが濃厚)
を踏まえ、`--device` 引数を追加し、指定に応じて `device_map` を明示的に
解決する(`resolve_device_map()` 参照)。
"""
import argparse
import json
import sys
import time
import traceback


def _log(message: str) -> None:
    """診断・進捗ログは標準エラー出力へ(stdoutはJSON1行専用のため)。"""
    print(message, file=sys.stderr, flush=True)


def resolve_processor_language(language: str) -> str:
    """CLIの--language値をprocessor()のlanguage引数へ渡す値へ変換する。

    processorは文字列"auto"を直接サポートする(DEFAULT_PROMPT_DICTIONARYに
    "auto":101が実在。transformers==5.17.0実ソースで確認、tc-ops #546)。
    そのため独自にNoneへ変換しない(かつてこの変換がTypeError:
    object of type 'NoneType' has no len()の原因だった)。
    """
    return language


def resolve_device_map(device: str):
    """CLIの--device値をfrom_pretrained()のdevice_map引数へ変換する。

    transformersのdevice_mapはAccelerateの自動配置("auto")のほか、
    "cpu"/"cuda"等の単一デバイス文字列もそのまま受け付ける
    (modeling_utils.pyのfrom_pretrained docstring実測: "device_map (`str`...)")。
    既存エンジン(Qwen3ASREngine/WhisperTranscriptionEngine)の device 値域
    (auto/cuda/cpu)と対応させ、未知の値は安全側の"auto"にフォールバックする。
    """
    if device in ("cpu", "cuda"):
        return device
    return "auto"


def main() -> int:
    parser = argparse.ArgumentParser(description="Nemotron-3.5-ASR-Streaming 単体推論")
    parser.add_argument(
        "audio_paths", nargs="+",
        help="音声ファイルのパス(複数指定可。複数指定時はチャンクとして1モデルロードで順次処理する)",
    )
    parser.add_argument(
        "--language", default="auto",
        help="言語コード(例: ja-JP, en-US)。既定はauto(自動検出)。",
    )
    parser.add_argument(
        "--device", default="auto", choices=["auto", "cuda", "cpu"],
        help="推論デバイス。既定はauto(Accelerateによる自動配置)。",
    )
    args = parser.parse_args()

    result = {"language": args.language, "device": args.device}

    try:
        import torch
        from transformers import AutoModelForRNNT, AutoProcessor
        from transformers.audio_utils import load_audio

        model_id = "nvidia/nemotron-3.5-asr-streaming-0.6b"
        device_map = resolve_device_map(args.device)
        result["device_map"] = device_map

        _log(f"Loading model: {model_id} (device_map={device_map})")
        t0 = time.time()
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForRNNT.from_pretrained(model_id, device_map=device_map)
        load_elapsed = time.time() - t0
        result["load_elapsed_sec"] = load_elapsed
        _log(f"Model loaded in {load_elapsed:.2f}s (once for {len(args.audio_paths)} chunk(s))")

        language_arg = resolve_processor_language(args.language)
        chunks = []

        for i, audio_path in enumerate(args.audio_paths):
            chunk_result = {"audio_path": audio_path}
            try:
                audio = load_audio(audio_path, sampling_rate=processor.feature_extractor.sampling_rate)
                audio_duration_sec = len(audio) / processor.feature_extractor.sampling_rate
                chunk_result["audio_duration_sec"] = audio_duration_sec

                inputs = processor(
                    audio, sampling_rate=processor.feature_extractor.sampling_rate, language=language_arg
                )
                inputs = inputs.to(model.device, dtype=model.dtype)

                _log(f"Chunk {i + 1}/{len(args.audio_paths)}: running inference...")
                t1 = time.time()
                output = model.generate(**inputs, return_dict_in_generate=True)
                infer_elapsed = time.time() - t1
                chunk_result["infer_elapsed_sec"] = infer_elapsed
                chunk_result["rtf"] = infer_elapsed / audio_duration_sec if audio_duration_sec > 0 else None
                _log(f"Chunk {i + 1}/{len(args.audio_paths)}: done in {infer_elapsed:.2f}s")

                text = processor.decode(output.sequences, skip_special_tokens=True)
                if isinstance(text, list):
                    text = "".join(text)
                chunk_result["transcription"] = text

                del inputs, output
            except Exception as chunk_e:  # noqa: BLE001 - このチャンクだけ失敗として記録し、後続チャンクは継続する
                chunk_result["error"] = f"{type(chunk_e).__name__}: {chunk_e}"
                _log(f"Chunk {i + 1}/{len(args.audio_paths)} failed: {chunk_e}")
                traceback.print_exc(file=sys.stderr)
            finally:
                # 査sa指摘: 1プロセス内で複数チャンクを処理する分、チャンクごとに
                # 明示的なVRAM後処理を行い、チャンク数に応じたメモリ累積を防ぐ。
                torch.cuda.empty_cache()

            chunks.append(chunk_result)

        del model
        torch.cuda.empty_cache()

        result["chunks"] = chunks

    except Exception as e:  # noqa: BLE001 - モデルロード等、全チャンク処理不能な異常
        # returncode!=0として異常終了を伝える。詳細はstderrへ出す(stdoutはJSON専用)。
        _log(f"ERROR: {type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
