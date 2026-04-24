"""Static-analysis helpers that let MPAC clients enrich an announced scope
with cross-file dependency information before handing it to a coordinator.

Currently Python-only; each new language should land as a sibling module
with the same ``scan_reverse_deps`` shape so callers can dispatch by file
extension without rewriting the announce path.
"""

from .import_index import (
    collect_python_sources_from_dir,
    scan_reverse_deps,
    scan_reverse_deps_detailed,
    scan_reverse_deps_from_dir,
)

__all__ = [
    "collect_python_sources_from_dir",
    "scan_reverse_deps",
    "scan_reverse_deps_detailed",
    "scan_reverse_deps_from_dir",
]
