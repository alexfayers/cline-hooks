@_default: lint type-check test

@_uv:
    uv -V 2> /dev/null || { echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'; exit 1;}

lint: _uv
    uv run ruff check --fix --show-fixes src/ tests/
    uv run ruff format src/ tests/

lint-check: _uv
    uv run ruff check src/ tests/

type-check: _uv
    uv run mypy src/ tests/

@_pnpm:
    pnpm install --frozen-lockfile --silent

ts-lint: _pnpm
    pnpm exec biome check src/cline_hooks/frontends/pi/extension.ts

ts-type-check: _pnpm
    pnpm exec tsc -p tsconfig.json

test: _uv
    uv run pytest -vv --nf

test-cov: _uv
    uv run coverage run -m pytest -vv --nf -s
    uv run coverage report --show-missing
