# Validation for 0.1.0

Executed locally on Windows with Python 3.13.16 on 2026-10-24:

- 32 unittest cases passed, including a gettext runtime compilation check proving
  that a fuzzy translation falls back to the original source string.
- Coverage.py measured 94% combined statement/branch coverage.
- Ruff lint and format checks passed.
- Both source distribution and wheel built successfully; the wheel was installed
  in a new temporary virtual environment outside the source checkout. The actual
  regression fixture exited 1, the repaired fixture exited 0, and uninstall passed.
- pip-audit checked the only runtime dependency, polib 1.2.0, and found no known
  vulnerabilities at check time. That result is time-bound, not a security guarantee.
- Manual review covered identity matching, plural completeness, bounded reads and
  findings, content-free diagnostics, license compatibility and read-only inputs.

The initial negative-input tests exposed acceptance of repeated nplurals fields.
The parser now rejects that ambiguity; the reproducer remains in the suite.
CI independently runs tests and isolated installs on Linux, Windows and macOS.
Its authoritative outcomes are available on the repository's Actions page.
