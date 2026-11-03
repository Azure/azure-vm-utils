#!/bin/bash

set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

output="test-requirements-frozen.txt"

docker run --rm \
    --mount "type=bind,src=$project_dir/selftest,dst=/selftest,readonly" \
    "python:3.10-slim" sh -ec '
        python -m venv /tmp/venv
        /tmp/venv/bin/python -m pip install --disable-pip-version-check \
            -r /selftest/test-requirements.txt >&2
        /tmp/venv/bin/python -m pip freeze
    ' > "$tmp_dir/$output"

cat "$tmp_dir/$output" > "$project_dir/selftest/$output"
