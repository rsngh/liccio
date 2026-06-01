# Local development

```bash
uv sync --all-extras
uv run acp --help
uv run acp demo bugfix      # full loop, no API keys
uv run pytest -q            # unit + integration + e2e + long
uv run ruff check . && uv run mypy src
```
The `uv` venv is isolated; the shared conda env is never modified.
