"""panhub-cli — command-line interface for PanHub netdisk aggregator search.

See README.md for usage and the security notice about credentials.
"""

from __future__ import annotations

__all__ = ["__version__"]


def _detect_version() -> str:
    """Resolve the package version with pyproject.toml as the source of truth.

    Order of preference:
      1. Installed package metadata (pip / venv installs) — always exact.
      2. Source tree (bin/panhub symlink, `python -m panhub`) — parse the
         pyproject.toml two levels up from this file.
      3. "unknown" — only if neither works (should never happen).
    """
    try:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _version

        try:
            return _version("panhub-cli")
        except PackageNotFoundError:
            pass
    except ImportError:  # pragma: no cover - Python < 3.8
        pass

    # Source-tree fallback: src/panhub/__init__.py -> ../../pyproject.toml
    import re
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        match = re.search(
            r'^version\s*=\s*"([^"]+)"',
            pyproject.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            return match.group(1)
    except OSError:  # pragma: no cover - unreadable/missing pyproject
        pass
    return "unknown"


__version__ = _detect_version()
