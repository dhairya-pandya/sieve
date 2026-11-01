PY ?= .venv/bin/python
WASM = contract/redswarm_escrow.wasm

.PHONY: test test-all demo contract

test:
	$(PY) -m pytest -q -m 'not slow'
	@if command -v cargo >/dev/null 2>&1; then cd contract && cargo test; else echo "cargo not found: skipping contract tests"; fi

test-all:
	$(PY) -m pytest -q

demo:
	$(PY) -m redswarm.demo.run_demo

contract:
	cd contract && cargo build --target wasm32-unknown-unknown --release
	cp contract/target/wasm32-unknown-unknown/release/redswarm_escrow.wasm $(WASM)
