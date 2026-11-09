PY ?= .venv/bin/python
WASM = contract/sieve.wasm

.PHONY: setup test test-all contract

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q -e '.[dev]'

test:
	$(PY) -m pytest -q
	@if command -v cargo >/dev/null 2>&1; then cd contract && cargo test -q; else echo "cargo not found: skipping contract tests"; fi

test-all:
	$(PY) -m pytest -q -m ''

contract:
	cd contract && cargo build --target wasm32-unknown-unknown --release
	cp contract/target/wasm32-unknown-unknown/release/sieve.wasm $(WASM)
