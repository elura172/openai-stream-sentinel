#!/usr/bin/env bash
set -euo pipefail
release_tmp=$(mktemp -d)
trap 'rm -rf "$release_tmp"' EXIT
for artifact in dist/*.whl dist/*.tar.gz; do
  package_env="$release_tmp/$(basename "$artifact")"
  uv venv "$package_env" --python 3.13
  uv pip sync --python "$package_env/bin/python" dist/requirements-runtime.txt
  uv pip install --python "$package_env/bin/python" --no-deps "$artifact"
  "$package_env/bin/python" -c 'from openai_stream_sentinel import __version__; assert __version__ == "0.2.0"'
  "$package_env/bin/sentinel" run --scenario healthy --out "$package_env/smoke.md"
done
