.PHONY: tests
tests:
	python -m isort tests lpt
	python -m black tests lpt
	autoflake -r --in-place --remove-unused-variables --remove-all-unused-imports --ignore-init-module-imports .
	python -m mypy tests lpt
	#pyright tests lpt
	python -m flake8 tests lpt --ignore=W503,E501
	python -m pylint lpt
	python -m pytest -xvvs tests

.PHONY: test-azure
test-azure:
	LPT_TEST_AZURE_IMAGES=1 python -m pytest -xrvvs tests/integration/test_azure.py -n 32 2>&1 | tee test-azure.log

.PHONY: sync
sync: tests
	git commit -a -m sync
	git push origin HEAD:main

.PHONY: force-sync
force-sync:
	git commit -a -m sync || true
	git push origin HEAD:main
