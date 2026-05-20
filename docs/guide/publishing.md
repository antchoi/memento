# Publishing Memento to PyPI

Memento's Python distribution name is `memento-lifecycle`. The installed import package and console command remain `memento`:

```bash
python -m pip install memento-lifecycle
memento doctor --json
```

The plain `memento` package name is already taken on PyPI, so do not change `[project].name` back to `memento` for public publishing.

## Release checklist

1. Start from a clean release branch on `main`.
2. Confirm `pyproject.toml` metadata and version.
3. Run tests, lint, compile, doctor, and sample smoke.
4. Build `sdist` and wheel.
5. Run `twine check`.
6. Upload to TestPyPI first.
7. Install from TestPyPI in a fresh virtualenv and run smoke checks.
8. Publish to PyPI.
9. Install from PyPI in a fresh virtualenv and run smoke checks.
10. Create a GitHub release/tag.

## Versioning rule

PyPI does not allow re-uploading the same filename/version. Every public upload must use a new version:

```toml
[project]
version = "0.1.1"
```

If an upload is broken, fix the issue and publish a new version. Do not rely on deleting and replacing an existing version.

## Local release build

Install release tooling:

```bash
python -m pip install -e '.[dev,release]'
```

Run the release gate:

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
PYTHONPATH=src python -m memento.cli doctor --json
PYTHONPATH=src python -m memento.cli sample-smoke --workspace /tmp/memento-release-smoke --json
```

Build and check artifacts:

```bash
rm -rf dist build *.egg-info src/*.egg-info
python -m build
twine check dist/*
```

Expected artifacts:

```text
dist/memento_lifecycle-<version>-py3-none-any.whl
dist/memento_lifecycle-<version>.tar.gz
```

## TestPyPI upload

Create a TestPyPI account and token at <https://test.pypi.org/>. Then:

```bash
twine upload --repository testpypi dist/*
```

Install from TestPyPI in a fresh environment:

```bash
python3 -m venv /tmp/memento-testpypi-venv
source /tmp/memento-testpypi-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  memento-lifecycle
memento doctor --json
memento sample-smoke --workspace /tmp/memento-testpypi-smoke --json
```

## PyPI upload

Create a PyPI account and token at <https://pypi.org/>. Then:

```bash
twine upload dist/*
```

Install from PyPI in a fresh environment:

```bash
python3 -m venv /tmp/memento-pypi-venv
source /tmp/memento-pypi-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install memento-lifecycle
memento doctor --json
memento sample-smoke --workspace /tmp/memento-pypi-smoke --json
```

## Recommended: GitHub Actions trusted publishing

The repository includes `.github/workflows/publish.yml` for PyPI Trusted Publishing.

### PyPI project setup

After the first project exists on PyPI, configure a trusted publisher:

- PyPI project: `memento-lifecycle`
- Owner: `antchoi`
- Repository: `memento`
- Workflow filename: `publish.yml`
- Environment: `pypi`

The workflow uses OIDC (`id-token: write`) and does not require storing a PyPI API token in GitHub Secrets.

### First upload caveat

Trusted Publishing usually requires the PyPI project to exist. For the first release, either:

1. create a pending publisher on PyPI with the exact repo/workflow/environment values, then run the GitHub workflow; or
2. do one manual `twine upload dist/*` with an account-scoped PyPI token, then switch to Trusted Publishing for future releases.

### GitHub release flow

1. Update `version` in `pyproject.toml`.
2. Commit and push.
3. Create a GitHub Release for `v<version>`.
4. The `Publish Python package` workflow runs on `release.published`.
5. Confirm PyPI contains the new version.
6. Fresh-install and smoke-test from PyPI.

Manual workflow dispatch is also enabled for maintainers. Use it only when the current commit has the intended release version.

## Token handling

If using `twine` manually, prefer keyring or `.pypirc` with restricted file permissions:

```ini
[pypi]
username = __token__
password = pypi-...

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-...
```

```bash
chmod 600 ~/.pypirc
```

Do not commit tokens, `.pypirc`, or generated `dist/` artifacts.
