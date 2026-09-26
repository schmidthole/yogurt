PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
SHELL_FILES := generator/entrypoint.sh radio/init/prepare $(wildcard radio/services/*/run)
SHFMT := go run mvdan.cc/sh/v3/cmd/shfmt@v3.11.0

.PHONY: setup fmt test test-audio integration radio generator ace-runtime
setup:
	uv sync --group dev

fmt:
	$(RUFF) format generator tests
	$(RUFF) check --fix generator tests
	gofmt -w radio
	$(SHFMT) -w $(SHELL_FILES)

test:
	$(RUFF) check generator tests
	$(RUFF) format --check generator tests
	$(PYTHON) -m unittest discover -s tests -v
	go test -race ./...

radio:
	docker build --target radio -t yogurt-radio .

ace-runtime:
	docker build --platform linux/amd64 -t yogurt-acestep:ca1e85fe9430179831e6bc6be790c332190a3866 https://github.com/ace-step/ACE-Step-1.5.git\#ca1e85fe9430179831e6bc6be790c332190a3866

generator:
	docker build --platform linux/amd64 --target generator -t yogurt-generator .

integration: radio
	$(PYTHON) tests/integration/radio.py

test-audio:
	docker build --target generator-test -t yogurt-generator-test .
	docker run --rm yogurt-generator-test
