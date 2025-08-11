import torch
import numpy as np
import soundfile as sf
from typing import List, Any, Optional, Callable
from tqdm import tqdm

# 統一システム
from core.config import TranscriptionConfig
from core.logging_config import UnifiedLogger, PerformanceLogger

# リファクタリングされたコンポーネント
from transcriber.model_cache import ModelCache
from transcriber.text_processing import TextProcessor
from transcriber.performance_optimizer import PerformanceOptimizer

class WhisperTranscriber:
    """
    Refactored WhisperTranscriber using modular components.
    Delegates functionality to specialized components for better maintainability.
    """
    
    def __init__(self, config: TranscriptionConfig):
        self.config = config
        
        # 統一ログシステム
        self.logger = UnifiedLogger.get_logger(__name__)
        self.perf_logger = PerformanceLogger(__name__)
        
        # リファクタリングされたコンポーネント
        self.model_cache = ModelCache(config.max_cache_size)
        self.text_processor = TextProcessor(config.max_line_length)
        self.performance_optimizer = PerformanceOptimizer(config)
        
        # モデル参照
        self.model = None
        self.processor = None
        
        # パフォーマンス最適化
        self.device_info = self.performance_optimizer.optimize_for_device()
        
        self.logger.info(f"WhisperTranscriber initialized: {self.config.model} on {self.config.device}")

    def load_model(self):
        """モデルのロード（統一キャッシュシステム使用）"""
        try:
            # Use model cache for consistency with unified system
            self.model, self.processor = self.model_cache.get_model(
                self.config.model, 
                self.config.device
            )
            
            self.logger.info(f"Model loaded successfully: {self.config.model}")
            
        except Exception as e:
            self.logger.error(f"Failed to load model: {str(e)}")
            raise
            
        if self.model is not None and self.processor is not None:
            return
            
        try:
            self.logger.info(f"モデルをロード中: {self.config.model}")
            
            # HuggingFaceトークンが必要な場合の処理
            import os
            hf_token = os.environ.get("HUGGINGFACE_TOKEN")
            kwargs = {}
            if hf_token:
                kwargs["token"] = hf_token
            
            self.processor = AutoProcessor.from_pretrained(self.config.model, **kwargs)
            self.model = WhisperForConditionalGeneration.from_pretrained(self.config.model, **kwargs).to(self.device)
            
            # キャッシュサイズ制限チェック
            self._manage_cache_size()
            
            # キャッシュに保存
            self._model_cache[self._cache_key] = (self.model, self.processor)
            import time
            self._cache_usage[self._cache_key] = time.time()
            
            # 言語とタスクを明示的に設定
            self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
                language=self.language,
                task="transcribe"
            )
            self.model.config.suppress_tokens = []
            self.model.config.pad_token_id = self.processor.tokenizer.pad_token_id
            self.logger.info(f"モデルを正常にロードしました: {self.config.model}")
            
        except ImportError as e:
            error_msg = f"必要なライブラリが見つかりません: {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except OSError as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                error_msg = f"モデルへのアクセスが拒否されました。HUGGINGFACE_TOKENを確認してください: {str(e)}"
            else:
                error_msg = f"モデルファイルの読み込みに失敗しました: {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except RuntimeError as e:
            if "CUDA out of memory" in str(e):
                error_msg = f"GPU メモリ不足です。CPUモードを試してください: {str(e)}"
            else:
                error_msg = f"モデルのロード中にランタイムエラーが発生: {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"モデルのロード中に予期しないエラーが発生: {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _manage_cache_size(self):
        """LRUキャッシュ管理"""
        if len(self._model_cache) >= self.max_cache_size:
            # 最も古いエントリを削除
            oldest_key = min(self._cache_usage.keys(), key=lambda k: self._cache_usage[k])
            del self._model_cache[oldest_key]
            del self._cache_usage[oldest_key]
            self.logger.info(f"キャッシュ制限により削除: {oldest_key}")

    def _get_memory_pool_tensor(self, shape, dtype, device):
        """動的メモリプールからテンソルを取得"""
        if not self.enable_dynamic_memory_pool:
            return torch.empty(shape, dtype=dtype, device=device)
        
        key = f"{shape}_{dtype}_{device}"
        if key in self._memory_pool and len(self._memory_pool[key]) > 0:
            tensor = self._memory_pool[key].pop()
            # テンソルをリセット
            tensor.zero_()
            return tensor
        else:
            return torch.empty(shape, dtype=dtype, device=device)
    
    def _return_memory_pool_tensor(self, tensor):
        """動的メモリプールにテンソルを返却"""
        if not self.enable_dynamic_memory_pool:
            return
        
        key = f"{tensor.shape}_{tensor.dtype}_{tensor.device}"
        if key not in self._memory_pool:
            self._memory_pool[key] = []
        
        # プールサイズ制限
        if len(self._memory_pool[key]) < 10:  # 最大10個まで保持
            self._memory_pool[key].append(tensor)
    
    def _get_next_stream(self):
        """次のGPUストリームを取得"""
        if self._gpu_streams is None:
            return None
        
        stream = self._gpu_streams[self._current_stream_idx]
        self._current_stream_idx = (self._current_stream_idx + 1) % len(self._gpu_streams)
        return stream

    def transcribe(self, audio_path: str) -> str:
        # パフォーマンス監視開始
        import time
        start_time = time.time()
        
        # 音声ファイルのメタデータから録音時刻を取得
        self._recording_start_time = self._get_recording_start_time(audio_path)
        
        # 処理開始時刻を記録
        self._start_time = time.time()
        
        self.load_model()
        audio, sr = self._preprocess_audio(audio_path)
        
        # バッチ処理可能なチャンクサイズで分割
        chunk_size = 30 * sr
        chunks = self._create_chunks(audio, chunk_size)
        
        if not chunks:
            return ""
            
        # バッチサイズを動的に決定（メモリ使用量を考慮）
        batch_size = self._calculate_optimal_batch_size(len(chunks))
        texts = []
        
        forced_decoder_ids = self.processor.get_decoder_prompt_ids(language=self.language, task="transcribe")
        
        # バッチ処理でトランスクリプション実行
        total_batches = (len(chunks) - 1) // batch_size + 1
        
        # パフォーマンス監視情報
        self.logger.info(f"処理開始: チャンク数={len(chunks)}, バッチサイズ={batch_size}, 総バッチ数={total_batches}")
        
        if self.progress_bar:
            progress = tqdm(total=total_batches, desc="音声文字起こし", unit="batch")
        
        batch_times = []  # バッチ処理時間を記録
        
        for i in range(0, len(chunks), batch_size):
            batch_start_time = time.time()
            batch_chunks = chunks[i:i + batch_size]
            
            if self.enable_async and len(batch_chunks) > 1:
                # 非同期処理
                batch_texts = self._transcribe_batch_async(batch_chunks, forced_decoder_ids)
            else:
                # 同期処理
                batch_texts = self._transcribe_batch(batch_chunks, forced_decoder_ids)
            
            # タイムスタンプ付きテキストを生成
            if self.include_timestamps:
                timestamped_texts = []
                for j, text in enumerate(batch_texts):
                    # 各チャンクの開始時刻を計算（30秒間隔）
                    chunk_index = i + j
                    chunk_start_seconds = chunk_index * 30
                    
                    # テキストを適切に分割してタイムスタンプを追加
                    timestamped_text = self._add_timestamps_to_text(text, chunk_start_seconds)
                    if timestamped_text:
                        timestamped_texts.append(timestamped_text)
                texts.extend(timestamped_texts)
            else:
                texts.extend(batch_texts)
            
            # バッチ処理時間を記録
            batch_time = time.time() - batch_start_time
            batch_times.append(batch_time)
            
            if self.progress_bar:
                progress.update(1)
            else:
                self.logger.debug(f"バッチ処理完了: {i//batch_size + 1}/{total_batches}, 処理時間: {batch_time:.2f}秒")
        
        if self.progress_bar:
            progress.close()
        
        # パフォーマンス監視結果を出力
        total_time = time.time() - start_time
        avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0
        self.logger.info(f"処理完了: 総時間={total_time:.2f}秒, 平均バッチ時間={avg_batch_time:.2f}秒, "
                        f"処理速度={len(chunks)/total_time:.2f}チャンク/秒")
        
        # 最終出力の整形（タイムスタンプが確実に行頭に来るように）
        if self.include_timestamps:
            final_output = self._ensure_timestamps_at_line_start("\n".join(texts))
            return final_output
        else:
            return "\n".join(texts)
    
    def _preprocess_audio(self, audio_path: str):
        """音声データの前処理（モノラル化、リサンプリング）"""
        try:
            # ファイル存在チェック
            from pathlib import Path
            if not Path(audio_path).exists():
                raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")
            
            # 音声ファイル読み込み
            try:
                audio, sr = sf.read(audio_path)
            except RuntimeError as e:
                if "does not match actual file contents" in str(e):
                    raise ValueError(f"音声ファイルの形式が不正です: {audio_path}")
                else:
                    raise RuntimeError(f"音声ファイルの読み込みに失敗しました: {str(e)}")
            
            if audio.size == 0:
                raise ValueError(f"音声ファイルが空です: {audio_path}")
            
            self.logger.debug(f"音声ファイル読み込み: shape={audio.shape}, sr={sr}, min={audio.min()}, max={audio.max()}")
            
            # モノラル化
            if len(audio.shape) > 1:
                audio = np.mean(audio, axis=1)
                self.logger.debug(f"モノラル化完了: shape={audio.shape}")
                
            # リサンプリング（必要な場合のみ）
            if sr != 16000:
                try:
                    import torchaudio
                    audio_tensor = torch.tensor(audio, dtype=torch.float32)
                    audio_tensor = torchaudio.functional.resample(audio_tensor, orig_freq=sr, new_freq=16000)
                    audio = audio_tensor.numpy()
                    sr = 16000
                    self.logger.debug(f"リサンプリング完了: shape={audio.shape}, sr={sr}")
                    del audio_tensor  # メモリ解放
                except ImportError:
                    self.logger.warning("torchaudioが見つかりません。リサンプリングをスキップします")
                except Exception as e:
                    self.logger.warning(f"リサンプリングに失敗しました: {e}")
                    
            return audio, sr
            
        except FileNotFoundError:
            raise
        except ValueError:
            raise
        except Exception as e:
            error_msg = f"音声前処理中にエラーが発生しました: {str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _create_chunks(self, audio, chunk_size):
        """音声データをチャンクに分割"""
        chunks = []
        n_chunks = int(np.ceil(len(audio) / chunk_size))
        
        for i in range(n_chunks):
            start = i * chunk_size
            end = min((i + 1) * chunk_size, len(audio))
            chunk = audio[start:end]
            if len(chunk) > 0:
                chunks.append(chunk)
        return chunks
    
    def _calculate_optimal_batch_size(self, num_chunks):
        """最適なバッチサイズを計算（RTX 4080向け高度最適化）"""
        if torch.cuda.is_available():
            try:
                # GPU使用時は利用可能メモリに基づいて決定
                gpu_memory = torch.cuda.get_device_properties(0).total_memory
                gpu_allocated = torch.cuda.memory_allocated(0)
                gpu_free = gpu_memory - gpu_allocated
                
                self.logger.debug(f"GPU メモリ状況: 総容量={gpu_memory/1e9:.1f}GB, "
                                f"使用中={gpu_allocated/1e9:.1f}GB, "
                                f"空き={gpu_free/1e9:.1f}GB")
                
                # RTX 4080 (16GB)向けの高度最適化 + 新機能活用
                if self.enable_multi_stream and self.enable_dynamic_memory_pool:
                    # マルチストリーム + 動的メモリプール有効時
                    if gpu_free > 14e9:  # 14GB以上の空き（RTX 4080の87%）
                        batch_size = min(16, num_chunks)  # 最大16チャンク同時処理
                    elif gpu_free > 12e9:  # 12GB以上の空き（RTX 4080の75%）
                        batch_size = min(12, num_chunks)  # 最大12チャンク同時処理
                    elif gpu_free > 10e9:  # 10GB以上の空き（RTX 4080の62%）
                        batch_size = min(10, num_chunks)  # 最大10チャンク同時処理
                    elif gpu_free > 8e9:  # 8GB以上の空き（RTX 4080の50%）
                        batch_size = min(8, num_chunks)  # 最大8チャンク同時処理
                    elif gpu_free > 6e9:  # 6GB以上の空き
                        batch_size = min(6, num_chunks)  # 最大6チャンク同時処理
                    elif gpu_free > 4e9:  # 4GB以上の空き
                        batch_size = min(4, num_chunks)  # 最大4チャンク同時処理
                    elif gpu_free > 2e9:  # 2GB以上の空き
                        batch_size = min(2, num_chunks)  # 最大2チャンク同時処理
                    else:
                        batch_size = 1
                else:
                    # 従来の最適化（後方互換性）
                    if gpu_free > 12e9:  # 12GB以上の空き（RTX 4080の75%）
                        batch_size = min(8, num_chunks)  # 最大8チャンク同時処理
                    elif gpu_free > 8e9:  # 8GB以上の空き（RTX 4080の50%）
                        batch_size = min(6, num_chunks)  # 最大6チャンク同時処理
                    elif gpu_free > 6e9:  # 6GB以上の空き
                        batch_size = min(4, num_chunks)  # 最大4チャンク同時処理
                    elif gpu_free > 3e9:  # 3GB以上の空き
                        batch_size = min(2, num_chunks)  # 最大2チャンク同時処理
                    elif gpu_free > 1e9:  # 1GB以上の空き
                        batch_size = 1
                    else:
                        # メモリ不足の可能性が高い場合は同期処理に切り替え
                        self.logger.warning("GPU メモリ不足により同期処理を推奨")
                        batch_size = 1
                
                self.logger.debug(f"計算されたバッチサイズ: {batch_size} (最適化機能: "
                                f"マルチストリーム={self.enable_multi_stream}, "
                                f"動的メモリプール={self.enable_dynamic_memory_pool})")
                return batch_size
                
            except Exception as e:
                self.logger.warning(f"GPU メモリ情報取得失敗: {e}")
                # フォールバック: RTX 4080向けの静的計算
                gpu_memory = torch.cuda.get_device_properties(0).total_memory
                if gpu_memory > 15e9:  # 15GB以上（RTX 4080相当）
                    return min(12, num_chunks)
                elif gpu_memory > 10e9:  # 10GB以上
                    return min(8, num_chunks)
                elif gpu_memory > 8e9:
                    return min(6, num_chunks)
                elif gpu_memory > 4e9:
                    return min(4, num_chunks)
                else:
                    return 1
        else:
            # CPU使用時はシステムメモリを考慮（16コア環境向け最適化）
            try:
                import psutil
                available_memory = psutil.virtual_memory().available
                cpu_count = psutil.cpu_count()
                
                # 16コア環境での最適化 + パイプライン並列処理
                if self.enable_pipeline_parallel:
                    if available_memory > 20e9 and cpu_count >= 16:  # 20GB以上、16コア以上
                        return min(8, num_chunks)
                    elif available_memory > 16e9 and cpu_count >= 12:  # 16GB以上、12コア以上
                        return min(6, num_chunks)
                    elif available_memory > 12e9 and cpu_count >= 8:  # 12GB以上、8コア以上
                        return min(4, num_chunks)
                    elif available_memory > 8e9:  # 8GB以上
                        return min(3, num_chunks)
                    elif available_memory > 4e9:  # 4GB以上
                        return min(2, num_chunks)
                    else:
                        return 1
                else:
                    # 従来の最適化（後方互換性）
                    if available_memory > 16e9 and cpu_count >= 16:  # 16GB以上、16コア以上
                        return min(6, num_chunks)
                    elif available_memory > 12e9 and cpu_count >= 8:  # 12GB以上、8コア以上
                        return min(4, num_chunks)
                    elif available_memory > 8e9:  # 8GB以上
                        return min(3, num_chunks)
                    elif available_memory > 4e9:  # 4GB以上
                        return min(2, num_chunks)
                    else:
                        return 1
            except Exception as e:
                self.logger.warning(f"システムメモリ情報取得失敗: {e}")
                return min(2, num_chunks)
    
    def _transcribe_batch(self, batch_chunks, forced_decoder_ids):
        """チャンクのバッチ処理（RTX 4080向け高度メモリ最適化 + 新機能）"""
        try:
            if len(batch_chunks) == 1:
                # 単一チャンクの場合
                inputs = self.processor(batch_chunks[0], sampling_rate=16000, return_tensors="pt")
                
                # 動的メモリプールからテンソルを取得
                if self.enable_dynamic_memory_pool:
                    input_features = self._get_memory_pool_tensor(
                        inputs.input_features.shape, 
                        inputs.input_features.dtype, 
                        self.device
                    )
                    input_features.copy_(inputs.input_features)
                else:
                    input_features = inputs.input_features.to(self.device)
                
                # GPUストリームを使用
                stream = self._get_next_stream()
                if stream is not None:
                    with torch.cuda.stream(stream):
                        with torch.no_grad():
                            predicted_ids = self.model.generate(
                                input_features,
                                forced_decoder_ids=forced_decoder_ids
                            )
                            transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
                else:
                    with torch.no_grad():
                        predicted_ids = self.model.generate(
                            input_features,
                            forced_decoder_ids=forced_decoder_ids
                        )
                        transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
                
                # 動的メモリプールにテンソルを返却
                if self.enable_dynamic_memory_pool:
                    self._return_memory_pool_tensor(input_features)
                    self._return_memory_pool_tensor(predicted_ids)
                else:
                    # 従来のメモリクリーンアップ
                    del input_features, predicted_ids
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                
                return [transcription]
            
            # 複数チャンクのバッチ処理（RTX 4080向け最適化 + 新機能）
            batch_inputs = []
            for chunk in batch_chunks:
                inputs = self.processor(chunk, sampling_rate=16000, return_tensors="pt")
                batch_inputs.append(inputs.input_features)
            
            # バッチテンソルを作成（動的メモリプール活用）
            if self.enable_dynamic_memory_pool:
                # テンソル共有最適化
                if self.enable_tensor_sharing and len(batch_inputs) > 1:
                    # 同じ形状のテンソルを共有
                    shared_shape = batch_inputs[0].shape
                    shared_tensor = self._get_memory_pool_tensor(
                        (len(batch_inputs), *shared_shape[1:]), 
                        batch_inputs[0].dtype, 
                        self.device
                    )
                    
                    for i, input_tensor in enumerate(batch_inputs):
                        shared_tensor[i] = input_tensor
                    
                    batch_features = shared_tensor
                else:
                    batch_features = torch.cat(batch_inputs, dim=0).to(self.device)
            else:
                batch_features = torch.cat(batch_inputs, dim=0).to(self.device)
            
            # 中間変数をクリア
            del batch_inputs
            
            # RTX 4080向けの高度な推論設定 + マルチストリーム処理
            stream = self._get_next_stream()
            if stream is not None:
                with torch.cuda.stream(stream):
                    with torch.no_grad():
                        # 大容量VRAMを活用した推論
                        predicted_ids = self.model.generate(
                            batch_features,
                            forced_decoder_ids=forced_decoder_ids,
                            do_sample=False,  # 決定論的生成で高速化
                            num_beams=1,      # ビームサーチを無効化して高速化
                            max_length=448    # 適切な最大長設定
                        )
                        transcriptions = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)
            else:
                with torch.no_grad():
                    # 大容量VRAMを活用した推論
                    predicted_ids = self.model.generate(
                        batch_features,
                        forced_decoder_ids=forced_decoder_ids,
                        do_sample=False,  # 決定論的生成で高速化
                        num_beams=1,      # ビームサーチを無効化して高速化
                        max_length=448    # 適切な最大長設定
                    )
                    transcriptions = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)
            
            # 高度メモリクリーンアップ + 動的メモリプール活用
            if self.enable_dynamic_memory_pool:
                self._return_memory_pool_tensor(batch_features)
                self._return_memory_pool_tensor(predicted_ids)
            else:
                del batch_features, predicted_ids
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    # RTX 4080向けの追加メモリ最適化
                    if torch.cuda.memory_allocated(0) > 12e9:  # 12GB以上使用時
                        torch.cuda.synchronize()  # GPU処理完了を待機
                        torch.cuda.empty_cache()  # 再度キャッシュクリア
            
            return transcriptions
            
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                self.logger.warning(f"メモリ不足のためシングルバッチ処理にフォールバック: {e}")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                # 単一チャンクずつ処理（改善されたエラーハンドリング）
                results = []
                for chunk in batch_chunks:
                    try:
                        single_result = self._transcribe_batch([chunk], forced_decoder_ids)
                        results.extend(single_result)
                    except Exception as chunk_error:
                        self.logger.error(f"チャンク処理中にエラー: {chunk_error}")
                        results.append("")  # 空文字でフォールバック
                return results
            else:
                raise
    
    def _transcribe_batch_async(self, batch_chunks, forced_decoder_ids):
        """非同期バッチ処理（16コア環境向け最適化 + パイプライン並列処理）"""
        if len(batch_chunks) == 1:
            return self._transcribe_batch(batch_chunks, forced_decoder_ids)
        
        try:
            # 16コア環境での最適ワーカー数計算 + パイプライン並列処理
            import psutil
            cpu_count = psutil.cpu_count()
            
            if self.enable_pipeline_parallel:
                # パイプライン並列処理: 前処理、推論、後処理を並列化
                optimal_workers = min(len(batch_chunks), min(cpu_count // 3, 12))  # 最大12ワーカー
                self.logger.debug(f"パイプライン並列処理設定: ワーカー数={optimal_workers}, CPU数={cpu_count}")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=optimal_workers) as executor:
                    # 前処理フェーズ
                    preprocessing_tasks = []
                    for chunk in batch_chunks:
                        task = executor.submit(self._preprocess_chunk_for_transcription, chunk)
                        preprocessing_tasks.append(task)
                    
                    # 前処理結果を収集（ストリーミング処理）
                    preprocessed_inputs = []
                    for task in concurrent.futures.as_completed(preprocessing_tasks):
                        try:
                            result = task.result()
                            preprocessed_inputs.append(result)
                        except Exception as e:
                            self.logger.error(f"前処理中にエラー: {e}")
                            # エラー時は空のテンソルでフォールバック
                            preprocessed_inputs.append(torch.zeros((1, 80, 3000)))
                    
                    # 推論フェーズ（GPU処理）
                    inference_results = self._transcribe_preprocessed_batch(preprocessed_inputs, forced_decoder_ids)
                    
                    # 後処理フェーズ（並列化）
                    postprocessing_tasks = []
                    for i, result in enumerate(inference_results):
                        task = executor.submit(self._postprocess_transcription, result, i)
                        postprocessing_tasks.append(task)
                    
                    # 後処理結果を収集
                    final_results = []
                    for task in concurrent.futures.as_completed(postprocessing_tasks):
                        try:
                            result = task.result()
                            final_results.append(result)
                        except Exception as e:
                            self.logger.error(f"後処理中にエラー: {e}")
                            final_results.append("")
                    
                    return final_results
            else:
                # 従来の非同期処理（後方互換性）
                optimal_workers = min(len(batch_chunks), min(cpu_count // 2, 8))  # 最大8ワーカー
                
                self.logger.debug(f"非同期処理設定: ワーカー数={optimal_workers}, CPU数={cpu_count}")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=optimal_workers) as executor:
                    # I/O集約的な前処理を並列化
                    preprocessing_tasks = []
                    for chunk in batch_chunks:
                        task = executor.submit(self._preprocess_chunk_for_transcription, chunk)
                        preprocessing_tasks.append(task)
                    
                    # 前処理結果を収集
                    preprocessed_inputs = []
                    for task in concurrent.futures.as_completed(preprocessing_tasks):
                        try:
                            result = task.result()
                            preprocessed_inputs.append(result)
                        except Exception as e:
                            self.logger.error(f"前処理中にエラー: {e}")
                            # エラー時は空のテンソルでフォールバック
                            preprocessed_inputs.append(torch.zeros((1, 80, 3000)))
                    
                    # バッチ処理で推論実行
                    return self._transcribe_preprocessed_batch(preprocessed_inputs, forced_decoder_ids)
                
        except Exception as e:
            self.logger.warning(f"非同期処理失敗、同期処理にフォールバック: {e}")
            return self._transcribe_batch(batch_chunks, forced_decoder_ids)
    
    def _postprocess_transcription(self, text, index):
        """後処理（並列化可能な処理）"""
        try:
            # 基本的な後処理
            if text and isinstance(text, str):
                # 前後の空白を削除
                text = text.strip()
                # 空文字列でない場合のみ返す
                if text:
                    return text
            return ""
        except Exception as e:
            self.logger.error(f"後処理中にエラー (index={index}): {e}")
            return ""
    
    def cleanup_memory_pool(self):
        """動的メモリプールのクリーンアップ"""
        if self.enable_dynamic_memory_pool:
            self._memory_pool.clear()
            self._tensor_cache.clear()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            self.logger.info("動的メモリプールをクリーンアップしました")
    
    def __del__(self):
        """デストラクタ: メモリの適切な解放"""
        try:
            self.cleanup_memory_pool()
        except:
            pass  # デストラクタでのエラーは無視
    
    async def _async_transcribe_chunks(self, batch_chunks, forced_decoder_ids):
        """チャンクの非同期処理"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(batch_chunks), 4)) as executor:
            # I/O集約的な前処理を並列化
            preprocessing_tasks = []
            for chunk in batch_chunks:
                task = executor.submit(self._preprocess_chunk_for_transcription, chunk)
                preprocessing_tasks.append(task)
            
            # 前処理結果を収集
            processed_inputs = []
            for task in concurrent.futures.as_completed(preprocessing_tasks):
                processed_inputs.append(task.result())
            
            # GPU処理は同期的に実行（GPUは並列化困難）
            return self._transcribe_preprocessed_batch(processed_inputs, forced_decoder_ids)
    
    def _preprocess_chunk_for_transcription(self, chunk):
        """チャンクの前処理（CPU集約的処理を分離）"""
        inputs = self.processor(chunk, sampling_rate=16000, return_tensors="pt")
        return inputs.input_features
    
    def _transcribe_preprocessed_batch(self, preprocessed_inputs, forced_decoder_ids):
        """前処理済みバッチの文字起こし"""
        try:
            # バッチテンソルを作成
            batch_features = torch.cat(preprocessed_inputs, dim=0).to(self.device)
            
            with torch.no_grad():
                predicted_ids = self.model.generate(
                    batch_features,
                    forced_decoder_ids=forced_decoder_ids
                )
                transcriptions = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)
            
            # メモリクリーンアップ
            del batch_features, predicted_ids
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            return transcriptions
            
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                self.logger.warning(f"バッチ処理でメモリ不足、単一処理にフォールバック")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                # 単一チャンクずつ処理
                results = []
                for input_features in preprocessed_inputs:
                    try:
                        input_features = input_features.to(self.device)
                        with torch.no_grad():
                            predicted_ids = self.model.generate(
                                input_features,
                                forced_decoder_ids=forced_decoder_ids
                            )
                            transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
                        results.append(transcription)
                        del input_features, predicted_ids
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception as chunk_error:
                        self.logger.error(f"単一チャンク処理中にエラー: {chunk_error}")
                        results.append("")  # 空文字でフォールバック
                return results
            else:
                self.logger.error(f"前処理済みバッチ処理中にエラー: {e}")
                raise

    def _format_segment_for_output(self, segment_text: str, segment_start_time_str: str, segment_end_time_str: str) -> List[str]:
        """セグメントを出力形式にフォーマット"""
        if not self.nlp or not SPACY_AVAILABLE:
            return [f"[{segment_start_time_str} -> {segment_end_time_str}] {segment_text.strip()}"]
        
        output_lines_for_segment = []
        is_first_line_of_segment = True
        
        try:
            doc = self.nlp(segment_text)  # GiNZAで解析
            for sent in doc.sents:
                lines_from_sentence = self._split_sentence_into_formatted_lines(
                    sent,
                    self.STRICT_PUNCTUATIONS,
                    self.STRONG_SENTENCE_ENDINGS_WITHOUT_PUNCT,
                    getattr(self.config, 'max_line_length', self.DEFAULT_MAX_LINE_LENGTH)
                )
                for line_content in lines_from_sentence:
                    if not line_content.strip():
                        continue
                    if is_first_line_of_segment:
                        formatted_line = f"[{segment_start_time_str} -> {segment_end_time_str}] {line_content}"
                        is_first_line_of_segment = False
                    else:
                        timestamp_placeholder_len = len(f"[{segment_start_time_str} -> {segment_end_time_str}] ")
                        padding = " " * timestamp_placeholder_len
                        formatted_line = f"{padding}{line_content}"
                    output_lines_for_segment.append(formatted_line)
            
            if not output_lines_for_segment and segment_text.strip():
                output_lines_for_segment.append(f"[{segment_start_time_str} -> {segment_end_time_str}] {segment_text.strip()}")
                
        except Exception as e_format:
            self.logger.error(f"言語学的フォーマット中にエラー: {e_format}", exc_info=True)
            output_lines_for_segment = [f"[{segment_start_time_str} -> {segment_end_time_str}] {segment_text.strip()}"]
        
        return output_lines_for_segment

    def _split_sentence_into_formatted_lines(self, sent: Span, strict_punctuations: List[str], strong_sentence_endings: List[str], max_line_length: int) -> List[str]:
        """文を適切な長さの行に分割"""
        output_lines = []
        current_line_buffer = ""
        tokens = list(sent)
        
        for i, token in enumerate(tokens):
            token_text = token.text
            
            # 行長制限チェック
            if current_line_buffer.strip() and \
               (len(current_line_buffer + token_text) > max_line_length) and \
               not self._is_linguistic_break_trigger(token, tokens, i, current_line_buffer, max_line_length, strict_punctuations, strong_sentence_endings, check_for_token_itself=True):
                output_lines.append(current_line_buffer.strip())
                current_line_buffer = token_text
            else:
                current_line_buffer += token_text
            
            # 言語学的改行トリガーチェック
            if self._is_linguistic_break_trigger(token, tokens, i, current_line_buffer, max_line_length, strict_punctuations, strong_sentence_endings, check_for_token_itself=False):
                if current_line_buffer.strip():
                    output_lines.append(current_line_buffer.strip())
                    current_line_buffer = ""
        
        # 残りのバッファを処理
        if current_line_buffer.strip():
            output_lines.append(current_line_buffer.strip())
        
        # 空の場合は元の文を返す
        if not output_lines and sent.text.strip():
            output_lines.append(sent.text.strip())
        
        return [line for line in output_lines if line]

    def _is_linguistic_break_trigger(self, token: Any, tokens: List[Any], token_idx: int, current_line_buffer: str, max_line_length: int, strict_punctuations: List[str], strong_sentence_endings: List[str], check_for_token_itself: bool) -> bool:
        """言語学的な改行トリガーを判定"""
        next_token = tokens[token_idx + 1] if token_idx + 1 < len(tokens) else None
        
        if check_for_token_itself:
            if token.text in strict_punctuations:
                return True
            if token.text in strong_sentence_endings:
                if not next_token or next_token.text not in strict_punctuations:
                    return True
            return False
        
        # 句読点での改行
        if token.text in strict_punctuations:
            return True
        
        # 文末表現での改行
        if token.text in strong_sentence_endings:
            if not next_token or next_token.text not in strict_punctuations:
                return True
        
        # 読点での改行（行が長い場合）
        if token.text == "、" and len(current_line_buffer.strip()) > max_line_length * 0.6:
            return True
        
        # 最後のトークン
        if token_idx == len(tokens) - 1:
            return True
        
        return False
    
    def _format_timestamp(self, seconds: float) -> str:
        """タイムスタンプをフォーマット
        
        Args:
            seconds: 秒数
            
        Returns:
            フォーマットされたタイムスタンプ文字列
        """
        if self.timestamp_format == "elapsed":
            # 経過時間形式 (00:00:00)
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
        elif self.timestamp_format == "absolute":
            # 絶対時刻形式（録音開始時刻からの計算）
            import time
            if hasattr(self, '_recording_start_time') and self._recording_start_time:
                actual_time = self._recording_start_time + seconds
                return f"[{time.strftime('%H:%M:%S', time.localtime(actual_time))}]"
            elif self._start_time:
                actual_time = self._start_time + seconds
                return f"[{time.strftime('%H:%M:%S', time.localtime(actual_time))}]"
            else:
                # フォールバック
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = int(seconds % 60)
                return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
        elif self.timestamp_format == "relative":
            # 相対時間形式（秒数）
            return f"[{seconds:.1f}s]"
        else:
            # デフォルトは経過時間
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    def _add_timestamps_to_text(self, text: str, start_seconds: float) -> str:
        """テキストにタイムスタンプを適切に追加
        
        Args:
            text: 入力テキスト
            start_seconds: 開始時刻（秒）
            
        Returns:
            タイムスタンプが追加されたテキスト
        """
        if not text or not text.strip():
            return ""
        
        # 既存のタイムスタンプを正しく処理
        import re
        timestamp_pattern = r'\[\d{2}:\d{2}:\d{2}\]'
        
        # テキストを行に分割
        lines = text.split('\n')
        timestamped_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 行内のすべてのタイムスタンプを抽出
            timestamps = re.findall(timestamp_pattern, line)
            if not timestamps:
                # タイムスタンプがない場合は推定時刻で追加
                line_timestamp = self._format_timestamp(start_seconds + len(timestamped_lines) * 30)
                timestamped_lines.append(f"{line_timestamp} {line}")
                continue
            
            # タイムスタンプ以外のテキストを抽出
            content = re.sub(timestamp_pattern, '', line)
            content = re.sub(r'\s+', ' ', content).strip()  # 複数の空白を単一の空白に
            
            if content:
                # 最初のタイムスタンプを行頭に配置
                timestamped_lines.append(f"{timestamps[0]} {content}")
            else:
                # 内容がない場合は最初のタイムスタンプのみ
                timestamped_lines.append(timestamps[0])
        
        return '\n'.join(timestamped_lines)
    
    def _get_recording_start_time(self, audio_path: str) -> Optional[float]:
        """音声ファイルのメタデータから録音開始時刻を取得
        
        Args:
            audio_path: 音声ファイルのパス
            
        Returns:
            録音開始時刻のタイムスタンプ（エポック秒）、取得できない場合はNone
        """
        try:
            from mutagen import File
            import time
            import os
            import re
            from datetime import datetime
            
            self.logger.debug(f"録音時刻取得開始: {audio_path}")
            
            # メタデータから録音時刻を取得
            audio_file = File(audio_path, easy=True)
            
            if audio_file is not None:
                self.logger.debug(f"メタデータ取得成功: {dict(audio_file)}")
                
                # titleタグから録音時刻を取得（例: 250627_1453）
                if hasattr(audio_file, 'get') and audio_file.get('title'):
                    title_text = audio_file.get('title')[0]
                    self.logger.debug(f"titleタグ: {title_text}")
                    # 250627_1453形式を解析
                    match = re.match(r'(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})', title_text)
                    if match:
                        year, month, day, hour, minute = match.groups()
                        # 20xx年として解釈
                        full_year = 2000 + int(year)
                        recording_time = time.struct_time((full_year, int(month), int(day), 
                                                         int(hour), int(minute), 0, 0, 0, -1))
                        timestamp = time.mktime(recording_time)
                        self.logger.debug(f"titleから録音時刻取得: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}")
                        return timestamp
                    else:
                        self.logger.debug(f"titleタグの形式が一致しません: {title_text}")
                else:
                    self.logger.debug("titleタグが見つかりません")
                
                # GEOB:IcdRInfoから録音時刻を取得（例: 2025-06-27T14:53:24）
                if hasattr(audio_file, 'get') and audio_file.get('GEOB:IcdRInfo'):
                    geob_data = audio_file.get('GEOB:IcdRInfo')
                    self.logger.debug(f"GEOB:IcdRInfo: {geob_data}")
                    if hasattr(geob_data, 'data'):
                        data_str = str(geob_data.data)
                        self.logger.debug(f"GEOBデータ: {data_str}")
                        # ISO形式の日時を検索
                        iso_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', data_str)
                        if iso_match:
                            iso_time_str = iso_match.group(1)
                            self.logger.debug(f"ISO時刻文字列: {iso_time_str}")
                            try:
                                dt = datetime.fromisoformat(iso_time_str)
                                timestamp = time.mktime(dt.timetuple())
                                self.logger.debug(f"GEOBから録音時刻取得: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}")
                                return timestamp
                            except ValueError as e:
                                self.logger.debug(f"ISO時刻解析エラー: {e}")
                
                # ファイルの作成時刻をフォールバックとして使用
                file_stat = os.stat(audio_path)
                timestamp = file_stat.st_ctime
                self.logger.debug(f"フォールバック: ファイル作成時刻 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}")
                return timestamp
            else:
                self.logger.debug("メタデータ取得失敗")
            
            return None
        except ImportError as e:
            self.logger.warning(f"mutagenライブラリが見つかりません: {e}")
            return None
        except Exception as e:
            self.logger.error(f"録音時刻取得エラー: {e}")
            return None
    
    def _ensure_timestamps_at_line_start(self, text: str) -> str:
        """タイムスタンプが確実に行頭に配置されるようにテキストを整形
        
        Args:
            text: 入力テキスト
            
        Returns:
            タイムスタンプが行頭に配置された整形済みテキスト
        """
        if not text:
            return text
        
        import re
        
        # 既存のタイムスタンプパターンを検出
        timestamp_pattern = r'\[\d{2}:\d{2}:\d{2}\]'
        
        # 各行を処理
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 行内のすべてのタイムスタンプを抽出
            timestamps = re.findall(timestamp_pattern, line)
            if not timestamps:
                # タイムスタンプがない場合はそのまま
                lines.append(line)
                continue
            
            # タイムスタンプ以外のテキストを抽出
            content = re.sub(timestamp_pattern, '', line)
            content = re.sub(r'\s+', ' ', content).strip()  # 複数の空白を単一の空白に
            
            if content:
                # 最初のタイムスタンプを行頭に配置
                lines.append(f"{timestamps[0]} {content}")
            else:
                # 内容がない場合は最初のタイムスタンプのみ
                lines.append(timestamps[0])
        
        return '\n'.join(lines)
    
    def test_timestamp_formatting(self) -> str:
        """テスト用メソッド - タイムスタンプ機能のテスト
        
        Returns:
            テスト完了メッセージ
        """
        
        # テストケース
        test_cases = [
            # ケース1: 通常のテキスト（タイムスタンプ追加）
            ("こんにちは。今日は良い天気ですね。", 0),
            
            # ケース2: 複数行のテキスト
            ("こんにちは。\n今日は良い天気ですね。\n散歩に行きましょう。", 30),
            
            # ケース3: 既にタイムスタンプが含まれている問題のあるテキスト
            ("チェッチキット[00:05:00] ごめん[00:05:30]\nお[00:06:00]\nお疲れさまで[00:06:30]\nごめん[00:07:00]", 0),
            
            # ケース4: 空行を含むテキスト
            ("こんにちは。\n\n今日は良い天気ですね。\n\n", 60),
        ]
        
        self.logger.info("=== タイムスタンプ機能テスト ===")
        
        for i, (test_text, start_seconds) in enumerate(test_cases, 1):
            self.logger.info(f"\n--- テストケース {i} ---")
            self.logger.info(f"開始時刻: {start_seconds}秒")
            self.logger.info("入力テキスト:")
            for line in test_text.split('\n'):
                self.logger.info(f"  {line}")
            
            # タイムスタンプ追加テスト
            self.logger.info("\nタイムスタンプ追加後:")
            timestamped_text = self._add_timestamps_to_text(test_text, start_seconds)
            for line in timestamped_text.split('\n'):
                self.logger.info(f"  {line}")
            
            # タイムスタンプ位置修正テスト
            self.logger.info("\n位置修正後:")
            corrected_text = self._ensure_timestamps_at_line_start(timestamped_text)
            for line in corrected_text.split('\n'):
                self.logger.info(f"  {line}")
            self.logger.info("---")
        
        self.logger.info("========================================")
        
        # 実際の問題例の修正テスト
        self.logger.info("\n=== 実際の問題例修正テスト ===")
        problem_cases = [
            "チェッチキット[00:05:00] ごめん[00:05:30]\nお[00:06:00]\nお疲れさまで[00:06:30]\nごめん[00:07:00]",
            "[00:07:30]\n前回どんな話をしたかというと[00:08:00]\nなるほど、実装9時、9月になりますから",
            "はい[00:04:30]\nチェッチキット[00:05:00] ごめん[00:05:30]\nお[00:06:00]",
            # ユーザーが提供した実際の問題例
            """[00:00:00]
はい[00:00:30] ごめん[00:01:00]
お[00:01:30]
チェッチョコ[00:02:00]
はい[00:02:30]
ごちそう[00:03:00]
ごちそう[00:03:30]
ごめん[00:04:00]
はい[00:04:30]
お[00:05:00]
チェッチキット[00:05:30] ごめん[00:06:00]
ごめん[00:06:30]
まず目的設定シートの内容のすり合わせが1つありますと、あとは雑貨の内容ですね、案件のことでもそれ以外でもちょっとコミュニケーションの場にできればなというところで、このワンオンを開催させてもらってますと、今回、目標設定させてもらいたんですかね。
[00:07:00]
お疲れさまで[00:07:30]
前回どんな話をしたかというと[00:08:00]
ちょっとこれも一旦消してもらった方がいいみたいなことでしたっけ
確かそうですよねって書いてもらったんですね
はいはいはいはいはいちょっとちょっとこれも一旦してもいいですか[00:08:30]
なるほど、実装9時、9月になりますから、その調整が空いてくると思います。
[00:09:00]
これ今今、今、コンティーやってるお仕事の一覧になると思うんですけど、上のやつもそういうか、これ以外に何かあるんでしたっけ?
[00:09:30]
いいですね11日までにこれを完了させなきゃいけないみたいなのか11日までにこれを完了しなきゃいけないんでしょうか11日までまでにこれまでにこれを完了しなきゃいけないんでしたっけ?
[00:10:00]
これ深夜の作業になるんでしたっけ?
本番は深夜ですよね。
じゃあなんかその作業が終わったらしばらくしばらくはいりませんね。
[00:10:30]
完全性と最終性を確認する[00:11:00]
成果物ってごめんなさい何になるんですか?
手順書と実行結果のエビデンスみたいなのを取るってことですか?
[00:11:30]
7月7月第1週間は3週間後ぐらいですかあともうあとは作業業待つのみみたいな感じなんですかまだまだ検査用末のみみたいな感じなんですかまだまだ検査用のコマンド書いています[00:12:00]
一貫性がともたれている状態ってこれ何を整理して何の整理でしたっけ?
何を整理していますか?
[00:12:30]
週1で打ち合わせが持てるのでその時に終盤環境のワーフのワーフの移行については[00:13:00]
切り替え日はもっと前ですね。"""
        ]
        
        for i, problem_text in enumerate(problem_cases, 1):
            self.logger.info(f"\n--- 問題例 {i} ---")
            self.logger.info("修正前:")
            for line in problem_text.split('\n'):
                self.logger.info(f"  {line}")
            self.logger.info("\n修正後:")
            corrected = self._ensure_timestamps_at_line_start(problem_text)
            for line in corrected.split('\n'):
                self.logger.info(f"  {line}")
        
        self.logger.info("========================================")
        return "テスト完了" 