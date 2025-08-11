# Requirements Structure

This directory contains organized dependency files for different use cases:

## File Structure

- **base.txt**: Core production dependencies required for running the application
- **dev.txt**: Development dependencies including testing and code quality tools (includes base.txt)
- **monitoring.txt**: Optional performance monitoring and profiling tools (includes base.txt)  
- **ci.txt**: Minimal dependencies for CI/CD pipelines

## Installation

### Production Environment
```bash
pip install -r requirements/base.txt
```

### Development Environment
```bash
pip install -r requirements/dev.txt
```

### With Monitoring Features
```bash
pip install -r requirements/monitoring.txt
```

### CI/CD Environment
```bash
pip install -r requirements/ci.txt
```

## Version Management

- We use semantic versioning with flexible ranges (>=X.Y.Z,<X+1.0.0)
- This allows automatic patch and minor updates while preventing breaking changes
- For production deployments, consider using pip-tools to generate pinned versions

## Migration from Old Structure

The old requirements files are preserved for reference:
- requirements.txt → Use requirements/base.txt
- requirements-minimal.txt → Merged into requirements/base.txt
- requirements-monitoring.txt → Use requirements/monitoring.txt
- requirements-ci.txt → Use requirements/ci.txt