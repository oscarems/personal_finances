from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

_repo_root = Path(__file__).resolve().parent.parent
_src_pkg = _repo_root / "src" / "finance_app"
if _src_pkg.exists():
    __path__.append(str(_src_pkg))
