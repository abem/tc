# ローカルWhisperモデル最適化計画書

## 1. 目的

10分の会議音声ファイルを5分以内に文字起こし完了させ、Word Error Rate (WER) を15%以下に抑える。

## 2. 範囲

* モデルサイズの最適化
* 量子化・蒸留による軽量化
* バッチ・チャンク処理の最適化
* 音声前処理パイプラインの構築
* デバイス最適化

## 3. ゴール

1. 推論速度: 1分音声あたり30秒以内の処理時間
2. メモリ使用量: GPUメモリ8GB以下
3. 認識精度: WER 15%以下

## 4. 環境設定

### 4.1 ハードウェア
* GPU: NVIDIA RTX 3080 (10GB VRAM)
* CPU: Intel Core i9-11900K
* RAM: 32GB
* OS: Ubuntu 20.04 LTS

### 4.2 テストデータセット
* メイン: LibriSpeech dev-clean (5時間)
* カスタム: 会議音声サンプル（ノイズ環境含む）
* 評価用: 正解テキスト付き音声ファイル（1時間）

## 5. ステップと詳細

### 5.1 モデルサイズの最適化

```python
import pytest
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List

class ModelBenchmark:
    def __init__(self):
        self.results: List[Dict] = []
        self.warmup_iterations = 3
        
    def warmup_model(self, model, audio):
        for _ in range(self.warmup_iterations):
            model.transcribe(audio)
    
    @pytest.mark.parametrize("model_size", ["tiny", "base", "small", "medium"])
    def test_model_performance(self, model_size: str):
        model = whisper.load_model(model_size)
        audio = load_test_audio("test_1min.wav")
        
        # ウォームアップ
        self.warmup_model(model, audio)
        
        # ベンチマーク
        start_time = time.time()
        result = model.transcribe(audio)
        inference_time = time.time() - start_time
        
        # メモリ使用量
        memory_usage = torch.cuda.max_memory_allocated() / 1024**2  # MB
        
        # WER計算
        wer = calculate_wer(result["text"], reference_text)
        
        self.results.append({
            "model_size": model_size,
            "inference_time": inference_time,
            "memory_usage": memory_usage,
            "wer": wer
        })
    
    def save_results(self):
        df = pd.DataFrame(self.results)
        df.to_csv("benchmark_results.csv", index=False)
        
        # 可視化
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        df.plot(x="model_size", y="inference_time", ax=ax1)
        df.plot(x="model_size", y="wer", ax=ax2)
        plt.savefig("benchmark_results.png")
```

### 5.2 量子化・蒸留の実装

```python
from torch.quantization import quantize_dynamic
import onnxruntime as ort
from neural_compressor import quantization

class ModelOptimizer:
    def __init__(self, model):
        self.model = model
        self.quantization_config = {
            "int8": {
                "backend": "torch.quantization",
                "method": "dynamic"
            },
            "onnx": {
                "backend": "onnxruntime",
                "optimization_level": "ORT_ENABLE_ALL"
            }
        }
    
    def quantize_model(self, method: str):
        if method == "int8":
            return quantize_dynamic(
                self.model,
                {torch.nn.Linear},
                dtype=torch.qint8
            )
        elif method == "onnx":
            return self._convert_to_onnx()
    
    def create_distilled_model(self):
        teacher_model = self.model
        student_model = whisper.load_model("tiny")
        
        # 蒸留設定
        distillation_config = {
            "temperature": 2.0,
            "alpha": 0.5,
            "beta": 0.5
        }
        
        return self._distill_model(teacher_model, student_model, distillation_config)
```

### 5.3 バッチ・チャンク処理の最適化

```python
import optuna
import seaborn as sns

class ChunkOptimizer:
    def __init__(self):
        self.chunk_sizes = [10, 15, 20]  # 秒
        self.batch_sizes = [2, 4, 8]
    
    def optimize_parameters(self, audio_file: str):
        def objective(trial):
            chunk_size = trial.suggest_int("chunk_size", 10, 20)
            batch_size = trial.suggest_int("batch_size", 2, 8)
            
            processing_time = self._process_with_params(
                audio_file, chunk_size, batch_size
            )
            return processing_time
        
        study = optuna.create_study()
        study.optimize(objective, n_trials=20)
        
        # 結果の可視化
        self._visualize_results(study)
        
        return study.best_params
    
    def _visualize_results(self, study):
        results = pd.DataFrame(study.trials_dataframe())
        pivot_table = results.pivot(
            index="params_chunk_size",
            columns="params_batch_size",
            values="value"
        )
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(pivot_table, annot=True, cmap="YlOrRd")
        plt.savefig("chunk_optimization.png")
```

### 5.4 音声前処理パイプライン

```python
class AudioPreprocessor:
    def __init__(self):
        self.pipeline = {
            "noise_reduction": {
                "method": "spectral_gating",
                "threshold": 0.1,
                "enabled": True
            },
            "normalization": {
                "method": "peak_normalization",
                "target_level": -3.0,
                "enabled": True
            }
        }
    
    def optimize_pipeline(self, audio_file: str):
        # 各処理の効果測定
        results = []
        for step in self.pipeline:
            # 処理なし
            baseline_time = self._process_audio(audio_file, {step: False})
            baseline_wer = self._calculate_wer(audio_file, {step: False})
            
            # 処理あり
            processed_time = self._process_audio(audio_file, {step: True})
            processed_wer = self._calculate_wer(audio_file, {step: True})
            
            results.append({
                "step": step,
                "time_impact": processed_time - baseline_time,
                "wer_impact": processed_wer - baseline_wer
            })
        
        return pd.DataFrame(results)
```

### 5.5 デバイス最適化

```python
class DeviceOptimizer:
    def __init__(self):
        self.optimization_methods = {
            "mixed_precision": True,
            "tensorrt": True,
            "onnx_runtime": True
        }
    
    def optimize_device(self, model):
        if torch.cuda.is_available():
            # Mixed Precision
            if self.optimization_methods["mixed_precision"]:
                model = self._enable_mixed_precision(model)
            
            # TensorRT
            if self.optimization_methods["tensorrt"]:
                model = self._convert_to_tensorrt(model)
            
            # メモリ最適化
            torch.cuda.empty_cache()
            torch.cuda.set_per_process_memory_fraction(0.8)
        
        return model
    
    def _enable_mixed_precision(self, model):
        return torch.cuda.amp.autocast()(model)
    
    def _convert_to_tensorrt(self, model):
        # TensorRT変換処理
        pass
```

## 6. スケジュール

| フェーズ | 期間 | 担当 | 成果物 |
|---------|------|------|--------|
| モデルサイズ最適化 | 1日 | エンジニアA | ベンチマーク結果CSV、可視化グラフ |
| 量子化・蒸留 | 1日 | エンジニアB | 最適化済みモデル、性能比較レポート |
| バッチ処理最適化 | 1日 | エンジニアC | 最適パラメータ、ヒートマップ |
| 前処理パイプライン | 1日 | エンジニアA | 前処理効果分析レポート |
| デバイス最適化 | 1日 | エンジニアB | 最適化済みモデル、性能レポート |

## 7. リスクと対策

* **メモリ不足**
  * 対策: チャンク処理とメモリ監視
  * 監視: `nvidia-smi`によるリアルタイム監視

* **精度低下**
  * 対策: 各最適化ステップ後の自動テスト
  * 監視: CIパイプラインでのWERチェック

* **処理速度**
  * 対策: バッチ処理とデバイス最適化
  * 監視: ベンチマーク結果の自動記録

## 8. 次のステップ

1. ベンチマーク環境の構築
2. テストデータセットの準備
3. CIパイプラインの設定
4. 最適化スクリプトの実装 