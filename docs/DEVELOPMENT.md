# Development

Use Python 3.12 or later. Install with `python -m pip install -e '.[dev]'`. Run `pytest`, `ruff check .`, and `python -m narrative --help`. Source is under `src/narrative`; tests live outside source; examples are original synthetic data. No credentials are needed for tests.

Core changes require tests for a real invariant or failure case. Analyses must retain evidence IDs and identify proxies. Imported text is data, never code. Review canon transitions, cache invalidation and budget exhaustion for every related change. Use feature branches and small commits; do not commit local databases, credentials, caches or generated temporary files.
