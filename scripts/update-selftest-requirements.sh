#!/bin/bash

set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

for version in 3.10 3.8; do
    output="test-requirements-frozen.txt"
    if [[ "$version" == "3.8" ]]; then
        output="test-requirements-frozen-py38.txt"
    fi

    docker run --rm \
        --mount "type=bind,src=$project_dir/selftest,dst=/selftest,readonly" \
        "python:$version-slim" sh -ec '
            python -m venv /tmp/venv
            /tmp/venv/bin/python -m pip install --disable-pip-version-check \
                -r /selftest/test-requirements.txt >&2
            /tmp/venv/bin/python -m pip freeze
        ' > "$tmp_dir/$output"
done

for output in test-requirements-frozen.txt test-requirements-frozen-py38.txt; do
    cat "$tmp_dir/$output" > "$project_dir/selftest/$output"
done
