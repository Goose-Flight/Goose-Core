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

Plugins must:
- Inherit from `goose.plugins.base.Plugin`
- Implement the `analyze(flight, config)` method
- Return a list of `Finding` objects
- Work fully offline (no network calls)
- Handle missing data gracefully

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

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
