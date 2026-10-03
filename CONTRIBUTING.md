# Contributing to transcribe_audio

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (依存関係管理)
- CUDA-capable GPU (実際の文字起こしには推奨。テストの実行には不要)
- Google Drive API の認証ファイル(Drive 連携を試すときだけ。テストには不要)

### Development Setup
```bash
# Clone the repository
git clone https://github.com/abem/tc.git
cd tc

# Install dependencies (uv が .venv を自動作成、dev group 含む)
uv sync

# Run tests
uv run python -m pytest tests -q
```

## 📋 Development Guidelines

### Code Style
- Follow PEP 8
- Run ruff for linting: `uv run ruff check .` (設定は `pyproject.toml` の `[tool.ruff]` / `[tool.ruff.lint]`。規則は pyflakes 相当の `F` のみ)
- 自動整形ツール(formatter)と型チェッカーは導入していない。既存コードの書式に合わせる

### Architecture Principles
- **Use core/ unified system** for new features
- **Preserve legacy compatibility** when possible
- **Follow the existing engine structure** (`TranscriptionEngine` を継承し、`core/engine_factory.py` の `create_engine` がモデル名で Nemotron / Qwen3-ASR / Whisper のエンジンを選ぶ。`UnifiedTranscriber` はそれを呼ぶファサード)
- **Test-driven development** - write tests first

### Important Rules (べからず集)
- **NEVER delete .venv/** - production environment (uv が管理)
- **NEVER commit credentials.json or token.pickle**
- **Check CLAUDE.md** before making significant changes (ブランチの更新順序や main の扱いなど、禁止事項はそちらが正本)
- **Use UnifiedConfig** (`core/config.py`) for configuration (旧 `AppConfig` は廃止済み)

## 🔄 Contribution Workflow

### 1. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
# ドキュメントだけの変更は docs/、リファクタリングは refactor/
```

ブランチの更新順序は **feature → dev → main** です。dev は本番(tc-prod)が追従する統合ブランチで、
dev の更新は本番コードの更新になります。main の更新はユーザーの明示的な指示があるときだけ行います。
feature から dev と main を別々に更新してはいけません(詳細は `CLAUDE.md`)。

### 2. Development Process
1. Write tests first (TDD approach)
2. Implement feature using core/ unified system
3. Ensure all tests pass: `uv run python -m pytest tests -q`
4. Run lint check:
   ```bash
   uv run ruff check .
   ```

### 3. Commit Guidelines
```bash
# Format: type: description
git commit -m "feat: add new CLI loader with Rich UI"
git commit -m "fix: resolve Google Drive authentication issue"
git commit -m "docs: update API documentation"
git commit -m "test: add unit tests for transcription engine"
```

### 4. Submit Pull Request / 統合
- PR の向け先は `dev`(`main` ではない)。`main` への反映は、dev の統合後にユーザーの指示で行う
- Include tests for new features
- Update documentation as needed
- Ensure CI passes(`.github/workflows/ci.yml`: `uv run ruff check .` と `uv run python -m pytest tests -q`)
- feature → dev → main の統合とその後の WebUI 再起動は `scripts/release_dev_main.sh` で行う。
  使い方・止まる条件・復旧は [docs/system-docs/release_operations.md](docs/system-docs/release_operations.md) を参照

## 🧪 Testing

### Running Tests
テストは GPU・ネットワーク・Google Drive 認証なしで動きます(モデルや外部呼び出しはモックされる)。
CI は GPU のない `ubuntu-latest` で同じコマンド(`uv run python -m pytest tests -q`)を実行しています。
手元では `CUDA_VISIBLE_DEVICES=""`(GPU を見えなくした状態)で `tests/test_docs_consistency.py` 以外の全件が通ることを確認しました
(2026-10-04、606 件)。GPU のないマシンそのものでの実行は未確認です。
```bash
# All tests
uv run python -m pytest tests -q

# Specific test file
uv run python -m pytest tests/test_core_config.py -q

# With coverage
uv run python -m pytest tests --cov=core --cov=handlers -q
```

### Test Categories
- **Unit tests**: Individual component testing
- **Integration tests**: Component interaction testing
- **E2E tests**: Full workflow testing

### Writing Tests
エンジンは実モデルを読み込むため、テストでは `create_engine` を差し替えます
(`tests/test_core_transcription_interface.py` などと同じ方式)。テスト名は `test_<振る舞い>` にします。

```python
from unittest.mock import MagicMock, patch

from core.config import TranscriptionConfig
from core.transcription_interface import UnifiedTranscriber
from core.transcription_types import TranscriptionResult, TranscriptionSegment


def test_transcribe_returns_engine_result():
    # Arrange: エンジンを差し替える(実モデルは読み込まない)
    fake_engine = MagicMock()
    fake_engine.transcribe.return_value = TranscriptionResult(
        text="こんにちは",
        segments=[TranscriptionSegment(start=0.0, end=1.0, text="こんにちは")],
        language="ja",
        duration=1.0,
        processing_time=0.1,
        model_name="fake-model",
    )
    config = TranscriptionConfig(model="fake-model", language="ja", device="cpu")
    with patch("core.transcription_interface.create_engine", return_value=fake_engine):
        transcriber = UnifiedTranscriber(config)

        # Act
        result = transcriber.transcribe("dummy.wav")

    # Assert
    assert result.text == "こんにちは"
    assert len(result.segments) == 1
```

詳しい構成と規約は [DEVELOPMENT.md](DEVELOPMENT.md) と
[docs/developer-guides/coding_standards.md](docs/developer-guides/coding_standards.md) を参照してください。

## 📚 Documentation

### Required Documentation Updates
- Update README.md for new features
- 利用者に見える挙動を変えるときは `docs/spec/00-project-spec.md`(正本)も更新する
- Add docstrings to new functions/classes
- Update docs/developer-guides/API.md for API changes

### Documentation Style
```python
def transcribe_audio(audio_path: str, language: str = "ja") -> TranscriptionResult:
    """
    Transcribe audio file to text.
    
    Args:
        audio_path: Path to audio file
        language: Language code ("ja" or "en")
        
    Returns:
        TranscriptionResult with text and metadata
        
    Raises:
        FileNotFoundError: If audio file doesn't exist
        RuntimeError: If transcription fails
        
    Example:
        >>> result = transcribe_audio("speech.wav", "ja")
        >>> print(result.text)
    """
```

## 🔒 Security

### Security Considerations
- Never commit API keys or credentials
- Keep authentication files out of git (`credentials.json` / `token.pickle` は `.gitignore` 済み)
- Follow secure coding practices
- Report security issues privately

### Credential Management
Google Drive の認証ファイルは、`handlers/gdrive_auth.py` の `get_drive_service()` が既定でカレントディレクトリの
`credentials.json` / `token.pickle` を読み書きする(`handlers/gdrive.py` の `GDriveClient` は引数なしで呼ぶ)。
どちらもコミットしない。

## 🐛 Bug Reports

### Before Reporting
1. Check existing issues
2. Try the latest version
3. Read troubleshooting docs

### Issue Template
```
**Bug Description**
Clear description of the issue

**Steps to Reproduce**
1. Step one
2. Step two
3. Expected vs actual behavior

**Environment**
- OS: Ubuntu 20.04
- Python: 3.12
- GPU: RTX 4080
- CUDA: 13.0

**Logs**
Include relevant log output
```

## 🎯 Feature Requests

### Feature Request Template
```
**Feature Description**
What feature would you like to see?

**Use Case**
Why is this feature useful?

**Proposed Implementation**
How should this be implemented?

**Alternatives**
What alternatives have you considered?
```

## 📞 Getting Help

- **Documentation**: Check docs/ directory
- **Discussions**: Use GitHub Discussions
- **Issues**: Report bugs and feature requests
- **Code Review**: All PRs are reviewed

## 🏆 Recognition

Contributors will be recognized in:
- CHANGELOG.md for significant contributions
- GitHub contributors graph

Thank you for contributing to transcribe_audio! 🎉