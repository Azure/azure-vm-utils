file(GLOB PYTHON_SOURCES */*.py)

add_custom_target(
    python-autoformat
    COMMAND isort ${PYTHON_SOURCES}
    COMMAND black ${PYTHON_SOURCES}
    COMMAND autoflake -r --in-place --remove-unused-variables --remove-all-unused-imports --ignore-init-module-imports ${PYTHON_SOURCES}
    COMMENT "Running autoformatting tools"
)

add_custom_target(
    python-lint
    COMMAND isort --check-only ${PYTHON_SOURCES}
    COMMAND black --check --diff ${PYTHON_SOURCES}
    COMMAND mypy --ignore-missing-imports ${PYTHON_SOURCES}
    COMMAND flake8 --ignore=W503,E501,E402 ${PYTHON_SOURCES}
    COMMAND pylint ${PYTHON_SOURCES}
    COMMENT "Running Python lint checks and formatting checks"
)
