# Contributing to Goose

Thank you for your interest in contributing to Goose! This document provides guidelines and information for contributors.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Goose-Core.git
   cd Goose-Core
   ```
3. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```
4. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Running Tests

```bash
pytest tests/ -v --cov=goose
```

### Linting

```bash
ruff check src/ tests/
ruff format src/ tests/
```

### Type Checking

```bash
mypy src/goose --strict
```

## Writing Plugins

Goose uses a plugin architecture for flight analysis. See [docs/writing-plugins.md](docs/writing-plugins.md) for the full guide.

### Plugin Requirements

Plugins must:
- Inherit from `goose.plugins.base.Plugin`
- Implement the `analyze(flight, config)` method
- Return a list of `Finding` objects
- Work fully offline (no network calls)
- Handle missing data gracefully

### Plugin Development Workflow

1. **Create your plugin** in `src/goose/plugins/`:
   ```python
   from goose.plugins.base import Plugin, Finding, Severity
   
   class MyPlugin(Plugin):
       name = "my_plugin"
       version = "1.0.0"
       description = "Your plugin description"
       
       def analyze(self, flight, config):
           findings = []
           # Your analysis logic here
           return findings
   ```

2. **Write unit tests** in `tests/plugins/test_my_plugin.py`:
   ```python
   import pytest
   from goose.plugins.my_plugin import MyPlugin
   
   def test_detects_issue(sample_flight_with_issue):
       plugin = MyPlugin()
       findings = plugin.analyze(sample_flight_with_issue, {})
       assert len(findings) > 0
   ```

3. **Test with real logs**: Use actual flight logs from `tests/data/` to validate behavior

4. **Document your plugin**: Add a section to [docs/writing-plugins.md](docs/writing-plugins.md) with:
   - Purpose and scope
   - Configuration parameters
   - Interpretation guide

### Testing Plugins

Run plugin-specific tests:
```bash
pytest tests/plugins/test_my_plugin.py -v
```

Run all plugin tests:
```bash
pytest tests/plugins/ -v --cov=goose.plugins
```

Ensure your plugin:
- Handles missing or invalid data without crashing
- Produces consistent results for the same input
- Completes analysis in reasonable time (< 5 seconds for typical logs)

## Pull Request Process

1. Ensure all tests pass and linting is clean
2. Update documentation if adding new features
3. Write tests for new functionality
4. Use conventional commit messages:
   - `feat: add new feature`
   - `fix: fix a bug`
   - `docs: update documentation`
   - `test: add or update tests`
   - `chore: maintenance tasks`
5. Open a PR against the `dev` branch

## Code Style

- Follow PEP 8 (enforced by ruff)
- Use type annotations for all public functions
- Keep functions focused and small
- Prefer clarity over cleverness

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include log format, Python version, and OS in bug reports
- Attach (or describe) the flight log that triggered the issue

## Deployment & Release Process

### Version Bumping

Update the version in:
- `src/goose/__init__.py` (if it exists)
- `pyproject.toml` or `setup.py`
- Create a git tag: `git tag v1.0.0`

### Building a Release

```bash
# Install build tools
pip install build twine

# Build distribution
python -m build

# Upload to PyPI
python -m twine upload dist/*
```

### Release Checklist

- [ ] All tests pass (`pytest` with coverage)
- [ ] No linting issues (`ruff check`)
- [ ] Documentation is up to date
- [ ] Changelog is updated
- [ ] Version number bumped
- [ ] Git tag created
- [ ] Package published to PyPI

### Publishing Documentation

Documentation is published automatically from the `docs/` directory. Update `.md` files for changes to appear on the live site.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
