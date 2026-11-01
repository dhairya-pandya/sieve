PY ?= .venv/bin/python
WASM = contract/redswarm_escrow.wasm

.PHONY: test demo contract

test:
	$(PY) -m pytest -q
	@if command -v cargo >/dev/null 2>&1; then cd contract && cargo test; else echo "cargo not found: skipping contract tests"; fi

demo:
	@echo "demo not implemented yet (Task 9)"

contract:
	cd contract && cargo build --target wasm32-unknown-unknown --release
	cp contract/target/wasm32-unknown-unknown/release/redswarm_escrow.wasm $(WASM)
