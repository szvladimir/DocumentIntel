PYTHON=python

.PHONY: test
test:
	PYTHONPATH=. $(PYTHON) -m pytest -q
