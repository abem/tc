# 査から計への検査報告書 - Nemotron分割最終手段化とGPU実測 完了報告(saku)

> **発行日**: 2026年09月27日 / **発行者**: 査ロール（sa） / **文書種別**: 検査報告書（最優先）
> **検査対象**: `00_レビュー依頼/作から計への完了報告書_Nemotron分割最終手段化とGPU実測_20260927.md` / **宛先**: 計ロール

## 検査結果

### 判定: **不合格**（是正必須1件）

## 1. 機械検証・コードレビュー（合格水準）

- `CHUNK_THRESHOLD_SEC = 350`（`core/nemotron_engine.py` L79）を実ファイルで確認。
- `find_silence_boundary()`・`adjust_boundaries_to_silence()`の実装を確認。探索窓のクランプ・RMS最小点探索・フォールバック・**境界逆転防止のクランプ**（`new_split = max(new_split, adjusted_points[-1])`）まで丁寧に実装されている。`transcribe()`から実際に呼ばれていることも確認した（L365）。
- `pytest tests`を独立実行し`173 passed, 1 skipped`で一致。
- GPU実測結果（ValueError境界・RTF劣化）はモデルのアーキテクチャ制約に関する技術的に自然な記述であり、内容面の矛盾は見当たらない。

## 2. 是正必須: `scripts/compare_nemotron_baseline.py`が、自身の記載する使用方法で実行するとエラーになる

計からの依頼（「ぜひこのスクリプトを実際に実行して回帰ゲートとしての機能を確認すること」）に従い、**スクリプトのdocstringに明記された使用方法を一字一句そのまま**実行した（原則2、GPU使用）:

```
$ .venv/bin/python scripts/compare_nemotron_baseline.py samples/e2e_sample.wav --language ja --device cuda
[1/2] 基準実行(分割なし)を開始: samples/e2e_sample.wav
[1/2] 完了: 0文字
[2/2] 現在の実装での実行を開始
ERROR: 実行に失敗しました: ModuleNotFoundError: No module named 'core.config'
（終了コード2）
```

**原因**: `_run_current_implementation()`が`from core.config import TranscriptionConfig`を実行するが、本スクリプトはリポジトリルートを`sys.path`へ追加していない。Pythonは`python scripts/foo.py`という起動形式では、スクリプト自身のディレクトリ（`scripts/`）のみを`sys.path[0]`に追加し、リポジトリルート（`core/`が置かれている場所）は追加しない。そのため、docstring記載の起動方法（`.venv/bin/python scripts/compare_nemotron_baseline.py ...`）は**必ず**この`ModuleNotFoundError`で失敗する。

**再現性の確認**: 同じ挙動が発生しない起動方法も確認した（`.venv/bin/python -m scripts.compare_nemotron_baseline ...`、または`PYTHONPATH=<repo root>`を明示設定した場合はいずれも正常動作し、正しく`PASS`/`FAIL`判定に到達する）。したがって完了報告書に記載の実機回帰確認（基準音声328秒で完全一致・PASS）自体が捏造ということではなく、**saku自身がdocstringに記載した起動方法とは異なる方法（モジュール実行またはPYTHONPATH設定）で実行した結果を報告した可能性が高い**。しかし査（および将来の利用者）が報告書・docstring記載のとおりに実行すると必ず失敗するため、成果物として機能しない。

**是正指示**: スクリプト先頭（`_REPO_ROOT`定義の直後等）に`sys.path.insert(0, str(_REPO_ROOT))`を追加し、docstring記載の起動方法（`.venv/bin/python scripts/compare_nemotron_baseline.py <audio_path> ...`）がそのまま動作することを、査に依頼せず自身で確認してから再提出されたい。

**新規テスト（`tests/test_scripts_compare_nemotron_baseline.py`）について**: 同ファイルのdocstringは「GPU実行を伴う関数（`_run_nemotron_infer_no_split`・`_run_current_implementation`）は…sa査読時のGPU実測フェーズで実際に実行して確認する対象」と明記しており、**この設計判断自体は適切**（重い関数のテスト回避先が明確化されている）。しかし査が実際にその役割を果たした結果、当該2関数のうち後者を含む実行経路に上記の欠陥が見つかった。設計は正しかったが、想定されていた「sa査読時の実行確認」を経ずに完了報告が提出された、という位置づけと理解する。

## 3. 参考情報（合否に影響しない）

- e2e_sample.wav（1秒の検証用音声）で試行した際、基準実行・現在実装いずれも空文字列（`transcription: ""`)を返し「完全一致」と判定された。この音声はCER/RTF実測に不十分と既知の1秒音声であり、空応答同士の一致は回帰ゲートとしての実効的な検証にはならない（本件の指摘とは別に、動作確認用にはJSUT等の意味のある音声を推奨する）。

## 4. 計ロールへの報告

是正の反映後、**査自身が上記のsys.path修正版でdocstring記載の起動方法をもう一度実行し、正常にPASS/FAIL判定へ到達することを確認してから**再提出を依頼されたい。

**文書終了**
