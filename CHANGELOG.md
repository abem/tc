# Changelog

このプロジェクトの、利用者と運用担当に見える変更を記録する。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に従う。

- 版番号は付けない。リポジトリに git tag は無く、`pyproject.toml` の version は 0.1.0 のまま。日付ごとに節を分け、新しい日付を上に置く。
- 日付は**コミット日**(`git log --format=%cs`)であり、main へ反映した日ではない。main へのマージ日は `git log main --merges` で確認する。
- 各行の末尾の英数字は git のコミットハッシュ、`#数字` は Redmine tc-ops(プロジェクト ID 28)のチケット番号。
- テスト・リファクタリング・文書の整備・調査の記録は、各日付の「内部の変更」にまとめる。
- 2025-08-11 より前の記録は、末尾の「履歴」にまとめて残す。

## [Unreleased]

## 2026-10-04

### Fixed

- 統合スクリプト `scripts/release_dev_main.sh` の前提チェック・実行順序・ジョブ判定を直した。最初に origin を fetch し、一致しなければ何も変更せずに止まる。一時 worktree で main へのマージと検証を済ませ、`--atomic` で push したあとに本番 dev を進める。WebUI のジョブは、ログの状態遷移とプロセスから判定する(35108af, #578)

### 内部の変更

- 文書と実装の整合を検査する `tests/test_docs_consistency.py` を追加(03137f7, #592)

## 2026-10-03

### Added

- WebUI に進捗バーと経過・残り時間を表示する。ダウンロードは yt-dlp の進捗(%)、Qwen3-ASR の長音声(300 秒超)はチャンクごと、Whisper は 30 秒チャンクごとに表示する。残り時間は進捗 3% 未満では出さない。短い音声と Nemotron は経過時間のみ表示する。CLI(`tc`、`transcribe.py`)は 10% 刻みで表示する(f7d649c, #577)
- WebUI の `output/uploads/` を 7 日、`output/queue_downloads/` を 1 日で自動整理する。新しい投入のたびに、期限を過ぎた項目を削除する。処理待ち・処理中のジョブのファイルは消さない(9ead68f, e5f6a80, #578)
- dev から main への統合・push・WebUI 再起動を行う `scripts/release_dev_main.sh` を追加した。`--dry-run` で確認のみ行える(9539a05)

### Changed

- `transcribe.py` と WebUI も、タイムスタンプ付与が有効で区間情報があるとき、保存するテキストに `[MM:SS] ` を付ける(`tc` と同じ)。保存・アップロード・履歴の記録・一時音声の削除は、3 つの入口で共通の処理(`finalize_transcription`)になった(ebcfa57, 155b2ab, #567)
- `transcribe.py` で、Google Drive からダウンロードした音声も、処理の成功・失敗にかかわらず終了時に削除する。`tc` は削除に失敗しても処理結果を失敗にせず、警告のみとする。ローカルの入力ファイルは削除しない(ebcfa57, #567)
- yt-dlp が見つからないとき、`pip install` による自動インストールをやめた。`uv sync` を案内して停止する。検出は PATH、現在の Python と同じ `bin/`、`.venv/bin/yt-dlp` の順(cd777f1, #567)
- Google Drive の認証モジュールをルートの `config.py` から `handlers/gdrive_auth.py` へ移した。`OAUTHLIB_INSECURE_TRANSPORT` は、対話的な再認証に入るときだけ設定する(896f889, #567)

### Fixed

- WebUI で同名のファイルを続けてアップロードしても、先のファイルを上書きしない。保存先は `output/uploads/<一意>/<ファイル名>` になった(a8f5eb9, #578)
- yt-dlp の呼び出しにタイムアウトを追加した。メタデータの取得は 60 秒、ソケットは 30 秒、ダウンロードは出力が 300 秒途絶えると中断する。WebUI の「解決中」が止まって見える原因の候補だった(30099cc, #550)

### Security

- WebUI のアップロードのファイル名を安全化し、`output/uploads/` の外へ書き込めないようにした(aec733c, #578)
- ログとキュー表示に、アップロード名・URL・動画タイトルを 1 行にして出すようにした。yt-dlp のエラー文も 1 行にする(b683834, b14d654, #578)

### 内部の変更

- `core/transcription_interface.py` を、型・Whisper・Qwen3・整形・ファサードに分割(da03ddb, #567)
- `core/history.py`(履歴 DB の検索・件数・削除)、`core/housekeeping.py`、`core/progress.py` を新設(b0e9d00, e5f6a80, f7d649c)
- `import core` でログを初期化しないようにし、`setup_logging()` を `tc`・`transcribe.py`・`webui.py` の `main()` で呼ぶ(ae7e3b9, #567)
- プロジェクト仕様 `docs/spec/00-project-spec.md` を新設(e7ad0a7, #567)

## 2026-10-02

### Changed

- CI を uv + ruff + pytest で作り直した(`.github/workflows/ci.yml`)。テストを実行していなかった 4 本の workflow を削除した(e2e6c42, #567)
- 設定しても結果が変わらない項目を削除した。`TranscriptionConfig` の 22 フィールド(`beam_size`、`temperature` など)と、`config/config.yaml` の `whisper.chunk_size` `beam_size` `best_of` `temperature` `available_models` `model_history`、`gdrive.chunk_size` `credentials_file` `token_file`、`logging:` 節。エンジンの動作は変わらない(6077d30, #567)

### Removed

- 起動できず、`.venv` や `config/config.yaml` を壊しうるスクリプトを削除した: `scripts/core/setup.sh`、`scripts/core/transcribe.sh`、`scripts/tools/monitor.sh`(58697c3, #567)
- 常に失敗していたスクリプトを削除した: `scripts/pre_check.sh`、`scripts/cleanup_transcriptions.sh`(2e8a388, #567)

### Fixed

- `transcribe.py` が X(Twitter) の URL で `KeyError` になる不具合を直した(bbab283, #567)

### 内部の変更

- ruff を導入し、検出を解消(bf5a4e8, 6a7bc6e, #567)
- 参照 0 件の関数・クラス・別名を削除(ede8913, 464d6e6, #567)
- `tc`・WebUI・`core/cli_workflow`・`handlers/youtube` のテストを追加。クリーンな checkout で初回からテストが通るように修正(fa0c878, #567)
- 開発者向け文書を実在するツールに合わせた(e2502bf, 64b1b70, d216870, #567)

## 2026-09-27

### Added

- Nemotron に、350 秒を超える音声を一括で処理するストリーミング推論を追加した。失敗したときは、均等分割と無音区間への調整による処理へ戻る(5b60db1, #546)
- Nemotron の長い音声を、自動でチャンクに分割して処理する(fd51100, #546)

### Changed

- Nemotron の分割の閾値を 300 秒から 350 秒へ変更した。10 分の音声は、トークン列長の上限(5000)を超えて失敗するため。分割点は無音区間に寄せる(cb34384, #546)
- チャンクの分割を均等分割にした。短い末尾チャンクで Nemotron が空の文字列を返し、文字が欠けることがあったため。モデルのロードは 1 回になり、実測で 62.5 秒から 30.0 秒になった(7c857e9, #546)

### Fixed

- Qwen3-ASR で反復を検出したとき、チャンク全体を捨てずに、無音区間で 2 分割して再試行し、なお反復するときは反復の開始位置より前だけを残す(69d0030, #547)
- WebUI で、実際には完了した項目が「失敗」と表示されることがあった(Streamlit のモジュール再読込で、キュー項目の状態の比較が偽になる)。状態の比較を `==` に変え、`QueueItemState` を `str, Enum` にして直した(7c857e9, #548)
- pytest のログを本番の `logs/transcription.log` に書かず、`logs/transcription_test.log` に書く(7c857e9, #548)
- Nemotron のストリーミング推論で、`--language` の指定が反映されない不具合を直した(5b60db1, c4f2c5d, #546)

### 内部の変更

- Nemotron 3.5 ASR の調査・実測の記録と、Qwen3-ASR との精度比較(#549)。作業指示書・報告書として `00_レビュー依頼/` に保存(2168dba, 36f4ba5, #549)

## 2026-09-26

### Added

- 第 3 のエンジンとして NVIDIA Nemotron-3.5-ASR-Streaming を追加した。WebUI のモデル選択肢の末尾から選ぶ。既定のモデルは変わらない。隔離した仮想環境(`venv-nemotron`、`scripts/setup_nemotron_venv.sh` で作る)のサブプロセスで実行する(fbca18a, #546)

### Fixed

- WebUI の既定「自動判定」で Nemotron を使うと必ず `TypeError` で失敗する不具合と、デバイスの指定が無視される不具合を直した(e48756b, #546)

## 2026-09-10

### Added

- WebUI の変換履歴に、キーワード検索(3 文字以上。FTS5 の trigram)と、選択した履歴の Markdown まとめ出力(ダウンロード)を追加した(3943bfc, #438)

## 2026-08-05

### Added

- WebUI(Streamlit)と、変換履歴(SQLite `output/history.db`)を追加した。`tc` と `transcribe.py` も履歴に記録する(4814189, #438)
- WebUI の文字起こしジョブをキューにした。複数件を投入でき、現在のジョブが終わると自動で次を始める(逐次処理)。待ち件数・処理中の対象・完了済みを表示する(869d676, #440)
- WebUI の変換履歴に、古い履歴の一括削除を追加した。件数を確認してから削除する(削除するのは履歴の行のみ)(78e57eb)
- WebUI の起動後、最初のページロードで `qwen_asr` を import しておく。systemd の再起動直後の初回が `No module named 'qwen_asr'` で失敗する不具合の暫定の緩和策(原因は未確定)(e6712f9, #441)

### Changed

- 認識のヒント(`context`)を、長い音声の最初のチャンクにだけ渡す。無音や不明瞭な区間で、ヒントの語が発話として出力される幻覚を防ぐため。`transcribe.py` も `whisper.context_file` を読む(10e5198, #439)

### Removed

- 実装が無く、一度も動作しなかった話者分離の機能を撤去した(WebUI のチェックボックス、`DiarizationConfig`、`speaker_diarization` の設定など)(ffbe913, #442)
- 呼び出し元が無い設定 `whisper.language_models` を削除した(10e5198, #439)

### Fixed

- WebUI の変換で、一時音声ファイルが `output/` に残る不具合を直した(894137a)
- WebUI のキューで、投入した項目が消えることがある不具合と、同じ URL の重複投入が失敗する不具合を直した(574c192, c1b528c, #440)
- WebUI の完了済み一覧を、確定した時刻の新しい順にし、見出しに `#番号` と確定時刻を付けた(80324df)

### 内部の変更

- WebUI の内部サーバー構成と systemd 常駐化の文書を追加(dc11c3f, 6fa8f60)

## 2026-08-04

### Changed

- `context_hints.txt.sample` に、幻覚のリスクの注意書きを追加した(0b937d8)

## 2026-08-03

### Added

- タイムスタンプの付与(オプトイン)を追加した。Qwen3-ASR の ForcedAligner で文節ごとの時刻を取り、`include_timestamps` が真のとき `[MM:SS]` を付ける。既定は付けない。失敗したときは付けずに出力する(ea44520)

### Changed

- 文字起こしの既定の言語を、日本語の固定から自動判定へ変えた(`whisper.language` の既定が `null`)。日本語の固定で英語中心の音声を処理すると、短い無関係な日本語 1 文になる事象があったため。`--language` で明示すれば従来どおり(7bbdee8)

### Fixed

- Qwen3-ASR で、同じ文やフレーズが数十回反復して出力が壊れる事象を抑えた。反復を予防する生成パラメータを設定し、反復を検出したら同じチャンクを 1 回再試行し、なお反復すれば置換する。チャンクごとの番号・所要時間・検出言語をログに出す(e48ab45)
- チャンクの境界で単語がつながる不具合を直した(`Nicolai Tangena way`)(8cf712a)

### 内部の変更

- 実装との乖離があった文書・スクリプトの是正(ラウンド 2)、README のインストール手順を `uv sync` に統一、旧エントリポイント `tc.old` の削除、E2E テスト(dry-run)の復旧(86b65fd, ef1061d, 0a2390d, 415ccc1)

## 2026-08-02

### Added

- Qwen3-ASR に、固有名詞・専門用語のヒント(`context`)を渡せるようにした。ヒントは `config/context_hints.txt`(1 行 1 語。`#` で始まる行はコメント。`.sample` を参照)に書き、`config.yaml` の `whisper.context_file` で指定する(8849cf4, 6eb4756)
- X(旧 Twitter)の動画 URL を入力できるようにした。YouTube と同じ経路(yt-dlp)で取得する(b4527aa)

### Changed

- yt-dlp を `pyproject.toml` の依存に明示した(649d70b)

### Fixed

- `tc` で、YouTube の URL を設定すると「ファイルが見つかりません」で失敗する不具合を直した(911000f)

## 2026-07-09

### Added

- Qwen3-ASR の出力に、句点・読点などで区切る文節ごとの改行を追加した。チャンクの境界で文節が分断される問題も直した(38cb91d, efac614)

### Changed

- 既定のモデルを `Qwen/Qwen3-ASR-1.7B` に変更した。モデル名に `qwen3-asr` を含むときは Qwen3-ASR、それ以外は Whisper が自動で選ばれる(b5cd3aa)
- Qwen3-ASR の依存(`qwen-asr`)を `default-groups` に入れ、`./tc` だけで動くようにした(962413e)
- 長い音声のチャンクを、9 分から 5 分(300 秒)へ小さくした(811df63)

### Removed

- `neosophie/Qwen3-ASR-1.7B-JA`(固有名詞特化モデル)の選択肢を、同日に追加し、取り下げた。同じ音声で内容が大きく欠けたため(8025ab9, 22404a5)

### Fixed

- 長い音声(52 分など)で `CUBLAS_STATUS_INTERNAL_ERROR` になる不具合を、音声を物理的に分割して処理することで直した(78eabf9)
- チャンクが失敗したとき、無言で内容が欠ける問題を直した。結果に `[チャンクN失敗]` を入れ、`tc` と `transcribe.py` が警告を表示する(e6d78b5, fde9300)

### 内部の変更

- GPU 監視スクリプトを pynvml に移行(024c56f)

## 2026-07-08

### Added

- Qwen3-ASR のエンジンを追加し、モデル名で Whisper との間を自動で切り替える(7a7d891, ff6477d, e327d17)

### Changed

- Python を 3.9 から 3.12 に上げた。numba の `SystemError` で Whisper が動かなかったため(65fad37)
- 依存関係の管理を uv(`pyproject.toml`、`uv.lock`)に統一した。librosa と scipy の構成に移し、Google Drive 認証のパッケージを明記した(b8bf67b, 7bbd5c2)
- 警告の抑制を、`tc` と `transcribe.py` で共通にし、本物の異常を隠さないよう範囲を狭めた(1ee3e14, 8fd7f50)

### Removed

- `requirements.txt`、`requirements-minimal.txt`、`requirements/` を削除した(7bbd5c2)

### Fixed

- `transcribe.py` の shebang を uv 経由にした(6a86cea)

### 内部の変更

- pytest を dev の依存に追加し、実行できる状態に戻した(1745b35, 2887f13)
- 文書とスクリプトの `pip install`、素の `python` を uv に直した(複数のレビュー指摘への対応)
- CLAUDE.md に、参照残存調査の運用ルールを追記(8109ed4)

## 2026-03-01

### Added

- アップロード先を指定する `--folder-id`(`tc`、`transcribe.py`)と、`config.yaml` の `upload_folder_id` を追加した。優先順位は、引数、`config.yaml`、動的な検出の順(0880267)

### Changed

- プロジェクトの構造とコード品質を改善した(b5f20f8)

### Security

- 個人のメールアドレスを、一般的な表現に変更した(f5c3350)

## 2026-02-27

### Changed

- CLI の処理の流れを共通化し、ローカルの E2E ハーネスを追加した(f67f5e8)

## 2026-02-21

### Changed

- `tc` 系のコマンドの補助関数を共通化し、Google Drive へのアップロードの流れを 1 か所にまとめた(421b253, 4ad8a1e)

## 2025-11-21

### Fixed

- WSL で、OAuth 認証と numba 依存関係のエラーを直した。リサンプリングを `resampy` から `librosa` に切り替えた(b8c3983)

## 2025-09-16

### Fixed

- Transformers の警告(`forced_decoder_ids`、`attention_mask`)を直し、`numpy<2` に固定した(bbd424b)

## 2025-08-11

### Added

- uv ベースの多言語音声文字起こしシステムを構築した。`tc` コマンド、Google Drive・YouTube からの取り込みとアップロード、日英の Whisper モデルを含む(823a32e)
- GitHub の標準構成と CI の workflow を追加した(fe9704a)

### Fixed

- `tc` コマンドが、削除されたファイルを元のディレクトリから復元して動くようにした(3fc7488)

### Security

- 機密情報を除外する `.gitignore` を追加した(f22716f)。`snapshots/` も git の管理から除外した(6729cbc)

---

## 履歴(2025-08-11 より前。現在のコードと一致しない)

以降の記述は、当時のものをそのまま残している。`patterns/`、`errors.py`、`exceptions.py`、`scripts/core/`、`requirements-minimal.txt`、`tests/test_patterns.py` など、現在は存在しないファイルへの言及を含み、black・flake8・isort・mypy・Trivy などの道具も現在は使っていない。リポジトリの git 履歴は 2025-08-11 に始まるため、下の日付は git で確認できていない。旧版の移行手順(Migration Guide)と開発ガイドは、現在動かないので削除した。

### [2025.07.28] - Major Refactoring and Quality Improvements

#### Added
- **Project-wide code quality tools**: `pyproject.toml` with black, flake8, isort, mypy configuration
- **Comprehensive test suite**: `tests/test_patterns.py` for OOP pattern implementations
- **GitHub Actions CI/CD**: Automated testing, linting, security scanning, and build pipeline
- **Minimal dependencies**: `requirements-minimal.txt` with only essential packages
- **Documentation organization**: Archived outdated docs, cleaned up structure

#### Changed
- **Consolidated exception handling**: Merged `errors.py`, `exceptions.py`, and `scripts/core/exceptions.py` into single `exceptions.py`
- **Removed code duplication**: Deprecated duplicate `scripts/core/main.py` implementation
- **Updated project metadata**: Added proper package configuration in `pyproject.toml`

#### Deprecated
- `errors.py` → moved to `errors.py.deprecated`
- `scripts/core/exceptions.py` → moved to `scripts/core/exceptions.py.deprecated`
- `scripts/core/main.py` → moved to `scripts/core/main.py.deprecated`

#### Improved
- **Code quality**: Consistent formatting and linting rules across project
- **Test coverage**: Added comprehensive tests for Factory, Strategy, Command, and Observer patterns
- **Development workflow**: Automated CI/CD pipeline with security scanning
- **Dependency management**: Reduced from 210+ to ~50 essential packages
- **Documentation**: Better organization and archival of outdated content

#### Security
- Added Trivy vulnerability scanning in CI pipeline
- Improved secret detection in pre-commit workflow
- Better handling of sensitive data in configuration

### [2.0.0] - 2025-07-23

#### Major: Complete OOP Design Patterns Implementation

##### Added
- **Abstract Factory Pattern** (`patterns/factories.py`)
  - `ModelFactoryRegistry` for centralized model creation
  - `ConfigurationFactory` for flexible configuration management
  - `LanguageAwareModelSelector` for intelligent model selection
  - Language-specific optimization (Japanese: kotoba-whisper-v2.2, English: whisper-large-v3)
  
- **Strategy Pattern** (`patterns/strategies.py`)
  - `BatchSizeStrategy` with RTX 4080 specific optimizations
  - `TimestampStrategy` with multiple formatting options (elapsed, absolute, milliseconds)
  - `ProcessingStrategy` for sequential vs parallel processing
  - `StrategyRegistry` for centralized strategy management
  
- **Command Pattern** (`patterns/commands.py`)
  - Decomposed 223-line main() function into testable commands
  - `AudioProcessingPipeline` for complete workflow orchestration
  - `CommandInvoker` with automatic error handling and logging
  - Individual commands for validation, transcription, and file operations
  
- **Observer Pattern** (`patterns/observers.py`)
  - Real-time progress monitoring with console progress bars
  - `MetricsObserver` for performance data collection
  - `EventBus` for decoupled event system
  - Multiple observer types (console, file, metrics, logging)
  
- **Dependency Injection System** (`patterns/dependency_injection.py`)
  - `DIContainer` with singleton and transient service management
  - `ServiceLocator` for alternative service access
  - `@inject` decorator for automatic dependency injection
  - Flexible service configuration and testing support
  
- **Refactored Components** (`patterns/refactored_components.py`)
  - Broke down 1,212-line WhisperTranscriber God class into 6 focused components:
    - `ModelManager` - Model loading and LRU caching
    - `AudioProcessor` - Audio preprocessing and chunking
    - `MemoryManager` - GPU memory optimization
    - `BatchProcessor` - Batch processing coordination
    - `TranscriptionFormatter` - Result formatting
    - `RefactoredWhisperTranscriber` - Composed transcriber using all components
  
- **Utility Classes** (`patterns/utilities.py`)
  - `TimestampUtils` - Eliminated timestamp formatting duplication
  - `FileValidator` - Comprehensive file validation with metadata
  - `PerformanceTimer` - Operation timing with context manager
  - `TemporaryFileManager` - Safe temporary file handling
  - `ErrorHandler` - Consistent error handling across codebase
  - `TextProcessingUtils` - Text cleaning and processing utilities
  
- **Integration and Documentation**
  - Complete integration example (`patterns/integration_example.py`)
  - Comprehensive documentation (`patterns/README.md`)
  - Package initialization with convenience functions (`patterns/__init__.py`)

##### Changed
- **Architecture**: Transitioned from monolithic to modular design
- **Error Handling**: Centralized error management with consistent patterns
- **Testing**: 90% of code now has injectable dependencies for unit testing
- **Performance**: Additional optimizations through strategy pattern implementations
- **Maintainability**: Single Responsibility Principle applied throughout

##### Improved
- **Code Maintainability**: God classes decomposed into focused components
- **Testability**: Dependency injection enables comprehensive unit testing
- **Extensibility**: Strategy and Factory patterns allow easy feature additions
- **Monitoring**: Real-time progress tracking and performance metrics
- **Code Quality**: Eliminated all code duplication through utility classes

#### Performance Improvements
- **RTX 4080 Optimization**: Specialized batch size strategies for RTX 4080 GPU
- **Adaptive Processing**: Automatic GPU/CPU strategy selection
- **Memory Management**: Enhanced memory pool management and cleanup
- **Progress Monitoring**: Real-time progress bars and metrics collection

### [1.5.0] - 2025-07-10

#### Added
- Complete speaker diarization implementation using pyannote.audio v3.3.2
- Language-specific model auto-selection (Japanese: kotoba-whisper-v2.2, English: whisper-large-v3)
- Performance optimization features:
  - Model caching with LRU management (75% faster subsequent runs)
  - Batch processing (2.5-5x GPU speed improvement)
  - Async processing (10-20% overall speed improvement)
  - Progress bars with real-time updates
  - Memory usage optimization (40-55% reduction)

#### Changed
- Updated to use transformers library exclusively for Whisper models
- Enhanced GPU optimization with device-specific strategies
- Improved error handling and logging throughout

#### Fixed
- Timestamp alignment issues (100% success rate)
- Memory management for long audio files
- Google Drive integration stability

### [1.4.0] - 2025-06-15

#### Added
- HuggingFace token-based authentication for speaker diarization
- Enhanced security measures for API key management
- Comprehensive testing suite with pytest

#### Security
- Migrated from hardcoded tokens to .env file management
- Invalidated all previously committed tokens
- Added security documentation and best practices

### [1.3.0] - 2025-05-20

#### Added
- Multi-language support (Japanese and English)
- Automatic model selection based on language
- Enhanced timestamp features with multiple formats
- Google Drive integration for file operations

#### Improved
- Audio processing pipeline efficiency
- Error handling and recovery mechanisms
- Logging and debugging capabilities

### [1.2.0] - 2025-04-10

#### Added
- Basic speaker diarization functionality
- Timestamp correction and formatting
- Configuration management via YAML

#### Changed
- Refactored core transcription logic
- Enhanced audio preprocessing

### [1.1.0] - 2025-03-05

#### Added
- GPU acceleration support
- Batch processing for long audio files
- Progress tracking for transcription jobs

#### Fixed
- Memory leaks during long transcription sessions
- Audio file format compatibility issues

### [1.0.0] - 2025-02-01

#### Added
- Initial release of transcribe_audio system
- Basic Whisper integration for Japanese transcription
- Google Drive file operations
- Core logging and error handling

#### Features
- Single-language Japanese transcription
- Basic file I/O operations
- Command-line interface
- Configuration via config files
