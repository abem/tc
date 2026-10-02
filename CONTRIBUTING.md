# Contributing to transcribe_audio

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (依存関係管理)
- CUDA-capable GPU (recommended)
- Google Drive API credentials

### Development Setup
```bash
# Clone the repository
git clone https://github.com/yourusername/transcribe_audio.git
cd transcribe_audio

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
- **Follow the existing engine structure** (`TranscriptionEngine` を継承し、`UnifiedTranscriber` がモデル名でエンジンを選択する)
- **Test-driven development** - write tests first

### Important Rules (べからず集)
- **NEVER delete .venv/** - production environment (uv が管理)
- **NEVER commit credentials.json or token.pickle**
- **Check CLAUDE.md** before making significant changes
- **Use UnifiedConfig** (`core/config.py`) for configuration (旧 `AppConfig` は廃止済み)

## 🔄 Contribution Workflow

### 1. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

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

### 4. Submit Pull Request
- Use the PR template
- Include tests for new features
- Update documentation as needed
- Ensure CI passes

## 🧪 Testing

### Running Tests
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
```python
# Example test structure
from core.config import TranscriptionConfig
from core.transcription_interface import WhisperTranscriptionEngine


def test_transcription_engine():
    """Test transcription engine with mock audio."""
    # Arrange
    config = TranscriptionConfig(model="test-model", language="ja")
    engine = WhisperTranscriptionEngine(config)
    
    # Act
    result = engine.transcribe("test_audio.wav")
    
    # Assert
    assert result.text is not None
    assert len(result.segments) > 0
```

## 📚 Documentation

### Required Documentation Updates
- Update README.md for new features
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
- README.md contributors section
- CHANGELOG.md for significant contributions
- GitHub contributors graph

Thank you for contributing to transcribe_audio! 🎉