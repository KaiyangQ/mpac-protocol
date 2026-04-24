"""Scope overlap detection for MPAC.

Two kinds of conflicts live here:

* ``scope_overlap`` — the classical case where two scopes claim overlapping
  resources (same file, same entity, same task). SPEC.md §15.2.1.1 defines
  this as a MUST: ``file_set`` overlap is *iff* resources intersect.
* ``scope_dependency_conflict`` — the cross-file case where no resources
  overlap but one scope's edits reach into the other's via an import.
  Reported with category ``dependency_breakage`` (SPEC.md §17.5 already
  lists this category).

  - **v0.2.1**: file-level precision — if A's edited file is imported by
    any file B is editing, conflict.
  - **v0.2.2 (this release)**: symbol-level precision when both sides
    supply enough info. If A declares ``affects_symbols`` (the specific
    names being changed) and the importer's symbol list (computed by the
    analyzer into ``impact_symbols``) doesn't intersect it, no conflict.
    Any missing info on either side falls back to the v0.2.1 file-level
    behaviour — no false negatives from the precision upgrade.
"""
from typing import Any, Dict, List, Optional
import re

from .models import Scope


def normalize_path(path: str) -> str:
    """Normalize a file path for comparison.

    Steps:
    1. Remove leading ./
    2. Collapse multiple slashes (//)
    3. Remove trailing slashes

    Args:
        path: File path to normalize

    Returns:
        Normalized path
    """
    # Remove leading ./
    if path.startswith("./"):
        path = path[2:]

    # Collapse multiple slashes
    path = re.sub(r'/+', '/', path)

    # Remove trailing slash (except for root /)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return path


def scope_overlap(a: Scope, b: Scope) -> bool:
    """Detect if two scopes overlap.

    Args:
        a: First scope
        b: Second scope

    Returns:
        True if scopes overlap, False otherwise
    """
    # Different scope kinds: conservative assumption of overlap
    if a.kind != b.kind:
        return True

    # Same kind: check for intersection based on field names
    if a.kind == "file_set":
        # Normalize all paths and check for intersection
        a_items = {normalize_path(item) for item in (a.resources or [])}
        b_items = {normalize_path(item) for item in (b.resources or [])}
        return len(a_items & b_items) > 0

    elif a.kind == "entity_set":
        # Exact string matching for entity sets
        a_items = set(a.entities or [])
        b_items = set(b.entities or [])
        return len(a_items & b_items) > 0

    elif a.kind == "task_set":
        # Exact string matching for task sets
        a_items = set(a.task_ids or [])
        b_items = set(b.task_ids or [])
        return len(a_items & b_items) > 0

    else:
        # Unknown scope kind: conservative True
        return True


def _scope_impact(scope: Scope) -> List[str]:
    """Pull the (possibly empty) cross-file impact list from a scope.

    The impact set lives under ``scope.extensions["impact"]`` by convention
    (see SPEC.md §15.2 extensions escape hatch). We validate shape here so
    junk or legacy payloads degrade to "no impact info" rather than crash.
    """
    if not scope.extensions:
        return []
    impact = scope.extensions.get("impact")
    if not isinstance(impact, list):
        return []
    return [x for x in impact if isinstance(x, str)]


def _scope_affects_symbols(scope: Scope) -> Optional[List[str]]:
    """Pull the agent-declared symbol set (0.2.2+).

    Returns None when the agent DID NOT declare specific symbols — this is
    the "assume everything" signal that triggers file-level fallback in
    dependency detection. An empty list is treated the same as None
    (nothing to match against → defer to file-level).
    """
    if not scope.extensions:
        return None
    raw = scope.extensions.get("affects_symbols")
    if not isinstance(raw, list):
        return None
    cleaned = [x for x in raw if isinstance(x, str) and x]
    return cleaned or None


def _scope_impact_symbols(scope: Scope, importer: str) -> Optional[List[str]]:
    """Pull the scanner-computed symbol list for a specific importer file.

    Returns:
        - A list of fully-qualified symbol names the importer actually uses.
        - ``None`` meaning "wildcard / can't determine" — callers must treat
          as "any symbol could be affected" and fall back to file-level.
        - Also ``None`` when ``impact_symbols`` is absent entirely (0.2.1
          client → 0.2.2 coordinator path).
    """
    if not scope.extensions:
        return None
    raw = scope.extensions.get("impact_symbols")
    if not isinstance(raw, dict):
        return None
    value = raw.get(importer)
    if value is None:
        # Two cases: key present with None (explicit wildcard) OR key absent.
        # Distinguish by checking membership.
        if importer in raw:
            return None  # explicit wildcard
        return None  # absent — caller should still treat as wildcard (safer)
    if not isinstance(value, list):
        return None
    return [s for s in value if isinstance(s, str)]


def _symbols_actually_clash(
    editor_scope: Scope,
    importer_file: str,
) -> bool:
    """Given that ``importer_file`` imports from ``editor_scope``'s files,
    decide whether the editor's planned changes actually affect a symbol
    the importer uses.

    Returns True (= "this IS a conflict") when:
      * the editor didn't declare ``affects_symbols`` (assume they touch
        everything), OR
      * the scanner couldn't pin importer's symbols (wildcard import), OR
      * the sets intersect — at least one symbol is both edited and used.

    Returns False only when both sides have concrete symbol sets AND they
    are disjoint. That's the precision win.
    """
    affects = _scope_affects_symbols(editor_scope)
    if affects is None:
        return True  # editor didn't declare → file-level fallback

    used = _scope_impact_symbols(editor_scope, importer_file)
    if used is None:
        return True  # wildcard or missing → file-level fallback

    return bool(set(affects) & set(used))


def compute_dependency_detail(a: Scope, b: Scope) -> Dict[str, Any]:
    """Compute a human-readable breakdown of a dependency-breakage conflict.

    Returns a dict with up to two directional entries:

    * ``ab``: what ``a``'s edits reach in ``b``'s resources — each entry
      is ``{"file": <b-file>, "symbols": [...] | None}`` where
      ``symbols`` is the intersection of ``a.affects_symbols`` and what
      ``b-file`` imports from ``a``. ``None`` signals "file-level only"
      (wildcard or missing declarations).
    * ``ba``: symmetric, ``b``'s edits reaching ``a``.

    Empty dict when nothing to report (should not normally happen once
    the caller has confirmed a dep conflict; returned defensively).

    The UI consumes this to render "Alice editing utils.foo affects your
    main.py" instead of the generic "dependency conflict" banner.
    """
    if a.kind != "file_set" or b.kind != "file_set":
        return {}

    a_resources = {normalize_path(r) for r in (a.resources or [])}
    b_resources = {normalize_path(r) for r in (b.resources or [])}
    a_impact = {normalize_path(r) for r in _scope_impact(a)}
    b_impact = {normalize_path(r) for r in _scope_impact(b)}

    detail: Dict[str, Any] = {}
    ab = _direction_detail(a, a_impact & b_resources)
    if ab:
        detail["ab"] = ab
    ba = _direction_detail(b, b_impact & a_resources)
    if ba:
        detail["ba"] = ba
    return detail


def _direction_detail(
    editor_scope: Scope,
    affected_files: set,
) -> List[Dict[str, Any]]:
    """For the given editor scope and the set of consumer files they
    touch, return one entry per file with the clashing-symbol intersection
    (or ``None`` if this direction degrades to file-level precision)."""
    if not affected_files:
        return []
    affects = _scope_affects_symbols(editor_scope)
    entries: List[Dict[str, Any]] = []
    for f in sorted(affected_files):
        if affects is None:
            entries.append({"file": f, "symbols": None})
            continue
        used = _scope_impact_symbols(editor_scope, f)
        if used is None:
            # Importer wildcard (``import X`` with bare use) — even with
            # ``affects_symbols`` we can't pin which symbols actually
            # clash, so report file-level.
            entries.append({"file": f, "symbols": None})
        else:
            clashing = sorted(set(affects) & set(used))
            entries.append({"file": f, "symbols": clashing or None})
    return entries


def scope_dependency_conflict(a: Scope, b: Scope) -> bool:
    """Detect a cross-file dependency conflict between two ``file_set`` scopes.

    Two checks run, both symmetric:

    1. For each file in ``a.extensions.impact`` ∩ ``b.resources``:
       does ``a``'s declared ``affects_symbols`` (if any) overlap the set
       of symbols the importer uses (``a.extensions.impact_symbols``)?
    2. Symmetric: ``b.extensions.impact`` ∩ ``a.resources`` with ``b``'s
       symbol declarations.

    When either side lacks symbol info, that side degrades to v0.2.1
    file-level — an import-reachable file is always flagged. So the
    v0.2.2 upgrade only ever *removes* false positives; it never misses
    a conflict the old rule would have caught.

    This function intentionally does NOT flag classic same-file overlap —
    ``scope_overlap`` owns that case. Caller (``coordinator``) checks
    overlap first, only falls through here on disjoint resources.
    """
    if a.kind != "file_set" or b.kind != "file_set":
        return False

    a_resources = {normalize_path(r) for r in (a.resources or [])}
    b_resources = {normalize_path(r) for r in (b.resources or [])}
    a_impact = {normalize_path(r) for r in _scope_impact(a)}
    b_impact = {normalize_path(r) for r in _scope_impact(b)}

    # Direction 1: a's edits reach a file b is claiming
    for f in a_impact & b_resources:
        if _symbols_actually_clash(a, f):
            return True

    # Direction 2: b's edits reach a file a is claiming
    for f in b_impact & a_resources:
        if _symbols_actually_clash(b, f):
            return True

    return False


def scope_contains(container: Scope, test: Scope) -> bool:
    """Check if *test* scope is fully contained within *container* scope.

    Returns True when every item in *test* also appears in *container*.
    For different scope kinds: conservative True (assume contained).
    """
    if container.kind != test.kind:
        return True  # Conservative

    if container.kind == "file_set":
        c_items = {normalize_path(r) for r in (container.resources or [])}
        t_items = {normalize_path(r) for r in (test.resources or [])}
        return t_items.issubset(c_items)

    elif container.kind == "entity_set":
        return set(test.entities or []).issubset(set(container.entities or []))

    elif container.kind == "task_set":
        return set(test.task_ids or []).issubset(set(container.task_ids or []))

    return True  # Unknown kind: conservative
