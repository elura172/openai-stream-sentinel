# Reproducing release 0.2.0

The source tag, `uv.lock`, pinned CI action revisions, and recorded checks define
this release. Runtime dependencies are locked; test tools are in the dev group.
This is a GitHub release, not a PyPI publication.

## Test the source tag

```bash
git checkout v0.2.0
uv sync --locked
uv run --no-sync pytest -q
```

CI uses uv 0.9.3 with Python 3.12, 3.13, and 3.14 on Linux. The integration tests
bind an ephemeral loopback port and use only a dummy API key. No API account is
required. Artifacts are retained by GitHub Actions according to repository retention settings.

## Build and verify installation

From the tagged checkout, with an empty `dist/` directory:

```bash
uv build --no-sources
uv export --locked --no-dev --no-emit-project --output-file dist/requirements-runtime.txt
bash scripts/check_distributions.sh
python3 scripts/hash_release.py
```

The smoke script creates temporary environments, installs the locked runtime
requirements, then installs and invokes the wheel and source distribution in
turn. The build backend version is pinned in `pyproject.toml`. It exercises the
installed CLI, rather than relying on editable source imports.

## Verify downloaded assets

Put the release assets in one directory, then use `sha256sum -c SHA256SUMS` on
Linux or `shasum -a 256 -c SHA256SUMS` on macOS. Checksums establish that the
assets match the published release files; they do not prove root causes or
runtime performance.

To install the wheel with the release's runtime versions:

```bash
uv venv .venv-release --python 3.13
uv pip sync --python .venv-release/bin/python requirements-runtime.txt
uv pip install --python .venv-release/bin/python --no-deps openai_stream_sentinel-0.2.0-py3-none-any.whl
.venv-release/bin/sentinel run --scenario healthy
```

The runtime lock is cross-platform; the shell smoke script targets POSIX systems.
No claim of bit-identical reports is made: incident identifiers, timestamps, and
measured local intervals change. Reports in `docs/evidence/` are explicitly
labeled snapshots, including the original defective behavior.
