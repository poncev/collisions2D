"""Module entry point: ``python -m multiscale_rasterization``.

Delegates to :func:`multiscale_rasterization.cli.main`.
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
