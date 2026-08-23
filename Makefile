.PHONY: test lint eval eval-real corpus mcp install

install:
	pip install -e ".[dev,claude,mcp]"

test:
	python -m pytest tests -q

lint:
	ruff check src evals tests

# Runs with no API key and no network. This is what CI runs.
eval:
	python evals/harness.py --extractor stub --split heldout --out evals/results

# Requires ANTHROPIC_API_KEY.
eval-real:
	python evals/harness.py --extractor claude --split heldout --out evals/results

ab:
	python evals/ab_demo.py

corpus:
	python -c "import sys;sys.path.insert(0,'src');from fde.generate import build_corpus;\
	d=build_corpus(n=3);print(d[0].text);print('---absent:',d[0].absent_fields)"

mcp:
	python -m fde.mcp_server
