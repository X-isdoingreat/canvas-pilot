# SPDX-License-Identifier: AGPL-3.0-or-later
"""src package — Canvas Pilot framework code.

Namespace extension: after the 2026-05-14 anonymization relocation,
several modules live in `_private/src/` (canvas_submit_origin,
pdf_metadata, zybooks_pdf, ...) to keep them out of the public mirror.
The __path__ append below makes them importable as `src.*` without any
PYTHONPATH gymnastics, so existing call sites like
`from src import canvas_submit_origin as cso` keep working.
"""
from pathlib import Path as _Path

_priv = _Path(__file__).resolve().parent.parent / "_private" / "src"
if _priv.is_dir():
    _p = str(_priv)
    if _p not in __path__:
        __path__.append(_p)
del _Path, _priv
