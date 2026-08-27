# macOS ships python3, not python. Override to target a venv:
#   make PYTHON=.venv/bin/python test
PYTHON ?= python3

.PHONY: test lint eval eval-real corpus mcp install

install:
	$(PYTHON) -m pip install -e ".[dev,claude,mcp]"

test:
	$(PYTHON) -m pytest tests -q

lint:
	$(PYTHON) -m ruff check src evals tests

# Runs with no API key and no network. This is what CI runs.
eval:
	$(PYTHON) evals/harness.py --extractor stub --split heldout --out evals/results

# Requires ANTHROPIC_API_KEY. Sourced from .env if present (git-ignored).
eval-real:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(PYTHON) evals/harness.py --extractor claude --split heldout --out evals/results

ab:
	$(PYTHON) evals/ab_demo.py

corpus:
	$(PYTHON) -c "import sys;sys.path.insert(0,'src');from fde.generate import build_corpus;\
	d=build_corpus(n=3);print(d[0].text);print('---absent:',d[0].absent_fields)"

mcp:
	$(PYTHON) -m fde.mcp_server
