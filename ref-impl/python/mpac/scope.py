"""Scope overlap detection for MPAC."""
from typing import List
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
