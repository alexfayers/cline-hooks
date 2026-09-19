# Contributing

## Setup

```bash
uv sync
```

## Checks

```bash
just          # lint, type-check, test (the default recipe)
just lint     # ruff check --fix + ruff format
just type-check  # mypy src/ tests/ (strict)
just test     # pytest
just test-cov # pytest with coverage report
```

Run these before opening a PR - there is no CI pipeline, so this is the only gate.

## Commit messages

Single-line, conventional-commit style: `type: short description`, no body.
Common types used in this repo: `feat`, `fix`, `refactor`, `docs`, `style`, `chore`.

## Pull requests

`main` is protected - it can't be pushed to directly. Push your branch and open
a PR; squash or rebase merge only.

Adding a frontend or plugin? See the README's "Adding a frontend" and
"Plugins" sections first.

## PR titles and descriptions

- Title in conventional-commit format (`type: subject`).
- Description as bullet points, not paragraphs.
- State WHAT changed and WHY, not HOW.
- No restating the diff, no process commentary, no filler.
