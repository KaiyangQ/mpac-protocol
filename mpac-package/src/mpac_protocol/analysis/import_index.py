"""Reverse-import scanner for cross-file dependency-breakage detection.

Given a set of *target files* (what a participant intends to modify) and
the *project's Python source*, return the other files whose static imports
reach any symbol defined in a target. Callers then pin this set into
``Scope.extensions["impact"]`` before announcing the intent; the coordinator
reports a ``dependency_breakage`` conflict when another participant's edits
land on a file in someone else's impact set.

The scanner is source-agnostic: it operates on a ``Mapping[path, content]``
so the same code works for filesystem projects (MCP/CLI, Claude Code) and
for database-backed projects (MPAC web-app, where files live in the
``ProjectFile`` table). Two thin adapters are provided — see
:func:`scan_reverse_deps_from_dir` and :func:`collect_python_sources_from_dir`.

Design notes
------------
* **Analyzer at the announce layer, not in core coordinator detection.**
  Computed at the layer that sees the source (local FS for MCP, DB for the
  web-app), emitted as ``scope.extensions.impact`` on the announce envelope.
* **Static analysis only.** ``importlib.import_module`` / ``__import__``
  targets are invisible. Consistent with pyright/ruff; we accepted this
  tradeoff when scoping v0.2.1.
* **One level of reverse dependency.** No transitive closure. If A → B → C
  and we're editing C, we flag B. Editing C doesn't flag A. Revisit in 0.3+
  if real usage shows the one-hop rule missing too many conflicts.
* **Fail soft.** Any per-file error (syntax, encoding, I/O) is swallowed —
  a broken file in the project must never break conflict detection.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Set, Tuple, Union

# Sentinel for "this file imports target module but we can't pin symbols"
# (bare ``import X`` or ``from X import *``). Distinct from an empty list
# which would mean "file imports nothing from target" (impossible for it
# to be in impact then).
_WILDCARD = None  # type: ignore


# Directories we never descend into when scanning the filesystem. Virtualenvs,
# build output, vendored deps, tool caches — parsing them wastes time and
# pollutes the impact set with noise.
_SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".hg", ".svn",
    "venv", ".venv", "env", ".env",
    "dist", "build", ".tox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "site-packages", ".eggs",
}


_RELATIVE_IMPORT_RE = re.compile(r"^(\.+)(.*)$")


# ── Path / module conversion ────────────────────────────────────────────

def _normalize_rel(path: str) -> str:
    """Turn any path into project-root-relative POSIX form.

    Callers pass a mix of ``./foo.py``, ``foo/bar.py``, ``\\foo\\bar.py``.
    We standardize to forward slashes and strip leading ``./`` so the
    mapping lookups are reliable across OSes.
    """
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _path_to_module(rel_path: str) -> Optional[str]:
    """Convert a project-relative .py path to a dotted module name.

    Returns None for non-python files. ``__init__.py`` collapses to the
    package name (``pkg/sub/__init__.py`` → ``pkg.sub``).
    """
    if not rel_path.endswith(".py"):
        return None
    stem = rel_path[:-3]  # strip .py
    parts = [p for p in stem.split("/") if p]
    if not parts:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def _extract_imports_detailed(
    source: str,
    filename: str = "<unknown>",
) -> List[Tuple[str, Optional[List[str]], bool]]:
    """Parse ``source`` into a list of ``(module, symbols_or_None)`` tuples.

    Returns tuples of ``(module, symbols, is_speculative)``:

    * ``module`` — the dotted module name being imported (or a relative
      path prefixed with leading dots, resolved later by the caller).
    * ``symbols`` — list of symbol names (ORIGINAL names, not ``as``
      aliases) for ``from X import a, b as c`` → ``["a", "b"]``. ``None``
      when we can't pin which symbols are used — covers
      ``from X import *`` and the conservative path for ``import X``
      when attribute-chain resolution sees a bare use of the alias.
    * ``is_speculative`` — True only for v0.2.4's ``from pkg import mod``
      attribute-chain entries, where we guessed that ``mod`` is a
      submodule and followed ``mod.attr`` uses. Speculative entries
      match only via EXACT module equality in the scan loop; they must
      never trigger the "submodule of target package" wildcard branch,
      which is reserved for real ``import pkg.sub`` statements.

    v0.2.3 adds attribute-chain resolution: for plain ``import X`` (and
    ``import X as Y``), we walk subsequent attribute accesses like
    ``X.foo()``. If every reference to the alias is a ``.attr`` access,
    we emit those attributes as the concrete symbol set. Any bare
    reference (``x = utils``, ``return utils``, ``isinstance(m, utils)``)
    collapses back to wildcard — we can't tell what the module got
    reassigned to. ``import pkg.sub`` is always wildcard; disambiguating
    whether ``pkg.sub.foo()`` means ``pkg.sub`` module or its ``.sub``
    attribute requires resolving the module graph, out of scope for now.

    Absolute and relative imports both go through this function; relative
    ones (``from ..pkg import y``) keep their leading dots so the caller
    resolves them via :func:`_resolve_relative`.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        # ValueError covers null-byte-in-source on some platforms.
        return []

    out: List[Tuple[str, Optional[List[str]], bool]] = []

    # alias_name (what the file binds locally) → module_name (the actual
    # dotted import target). Used for the attribute-chain pass below.
    # We only populate for ``import X`` / ``import X as Y`` without dots
    # in the target — ``import pkg.sub`` stays wildcard up-front.
    alias_to_module: Dict[str, str] = {}
    # Aliases added *speculatively* from ``from pkg import mod`` (v0.2.4).
    # Flow with these differs in two places:
    #   1. If attribute-chain resolution taints the alias (bare reference)
    #      or finds no usage, we drop rather than emitting wildcard —
    #      the legacy ``(pkg, [mod])`` emit above already covers the
    #      file-level hit.
    #   2. When we DO emit (clean attr-chain usage), the tuple is tagged
    #      ``is_speculative=True`` so the scan loop accepts it only via
    #      exact target-module match — never via the "submodule of target
    #      package" branch (which is for real ``import pkg.sub``).
    speculative_aliases: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if "." in module:
                    # ``import pkg.sub`` — submodule semantics are ambiguous
                    # without the module graph. Stay conservative.
                    out.append((module, _WILDCARD, False))
                    continue
                local_name = alias.asname or alias.name
                alias_to_module[local_name] = module
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            mod = node.module or ""
            qualified = "." * level + mod
            has_star = any(a.name == "*" for a in node.names)
            if has_star:
                out.append((qualified, _WILDCARD, False))
            else:
                symbols = [a.name for a in node.names]
                out.append((qualified, symbols, False))
                # v0.2.4: ``from pkg import mod`` is the most common
                # Python idiom for pulling in a submodule, and writers
                # then reach through it as ``mod.attr()``. Up through
                # 0.2.3 this bound ``mod`` only as a plain name, so the
                # attribute-chain pass below never saw ``mod.attr``
                # — the importer was invisible to the scanner when the
                # target module was ``pkg/mod.py``.
                #
                # Fix: speculatively register each imported name as a
                # submodule alias (``{mod}.{name}``). If the guess is
                # wrong (the name is actually a function/class, not a
                # submodule), the attribute-chain pass may still emit
                # ``(pkg.name, [...])``, but no target module will match
                # it at scan time and it drops silently. The legacy
                # ``(pkg, [name])`` emit above is untouched, so the
                # ``from pkg import fn`` + plain ``fn()`` path keeps its
                # exact pre-0.2.4 behavior.
                #
                # Absolute-only: relative imports (``from . import x``)
                # need importer-path resolution before they can be
                # turned into a dotted alias. Out of scope for 0.2.4;
                # tracked in backlog.
                if level == 0 and mod:
                    for a in node.names:
                        if a.name == "*":
                            continue
                        local_name = a.asname or a.name
                        # Don't clobber an existing ``import X``
                        # binding — that one has an exact resolution
                        # and should win.
                        if local_name not in alias_to_module:
                            alias_to_module[local_name] = f"{mod}.{a.name}"
                            speculative_aliases.add(local_name)

    # Attribute-chain pass: for each plain ``import X`` binding we didn't
    # resolve above, try to prove every use is ``X.attr``; if so, collect
    # attrs and emit as a precise symbol list. One bare use anywhere in
    # the file → wildcard.
    if alias_to_module:
        resolved_pairs = _resolve_attribute_chains(
            tree, alias_to_module, speculative_aliases
        )
        out.extend(resolved_pairs)

    return out


def _resolve_attribute_chains(
    tree: ast.AST,
    alias_to_module: Dict[str, str],
    speculative_aliases: Set[str],
) -> List[Tuple[str, Optional[List[str]], bool]]:
    """Walk ``tree`` and for each alias in ``alias_to_module`` decide:

    * All references are attribute-base (``alias.attr``) → emit
      ``(module, sorted([attr1, attr2, ...]))``.
    * At least one bare reference (``x = alias``, ``return alias``, etc.)
      → emit ``(module, None)``.
    * No references at all (import unused) → also ``(module, None)`` —
      the file technically still imports the module, so treat the whole
      module as potentially touched.

    This pass is pure read-only; we never mutate the AST permanently
    (parent pointers are set only on a shallow copy of what we walked).
    """
    # Temporarily set ``_mpac_parent`` on each node so we can look up who
    # owns each Name without re-traversing. We use a custom attribute so
    # we don't collide with anything ast's own logic expects.
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child._mpac_parent = parent  # type: ignore[attr-defined]

    attrs_by_alias: Dict[str, Set[str]] = {a: set() for a in alias_to_module}
    wildcarded: Set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Name):
            continue
        if node.id not in alias_to_module:
            continue
        parent = getattr(node, "_mpac_parent", None)
        # ``alias.attr`` — parent is Attribute and our Name IS its ``value``
        if isinstance(parent, ast.Attribute) and parent.value is node:
            attrs_by_alias[node.id].add(parent.attr)
        else:
            # Bare reference: could be reassignment, return value,
            # argument to a function, etc. Conservatively bail on
            # attribute-chain precision for this alias.
            wildcarded.add(node.id)

    out: List[Tuple[str, Optional[List[str]], bool]] = []
    for alias, module in alias_to_module.items():
        is_speculative = alias in speculative_aliases
        if alias in wildcarded or not attrs_by_alias[alias]:
            # Fallback: either bare use OR import was unused (can't rule
            # out future dynamic access in the same file).
            #
            # Speculative aliases from ``from pkg import mod`` must NOT
            # emit anything here: the legacy ``(pkg, [mod])`` emit
            # already captured the file-level hit correctly, and any
            # additional ``(pkg.mod, None)`` entry could either
            # (a) not match any target (harmless but wasted work) or
            # (b) match the "submodule of target package" branch at
            # scan time when the target is ``pkg/__init__.py``,
            # overwriting a precise pkg-level symbol result with None.
            # Dropping here matches the pre-0.2.4 behavior for tainted
            # from-imports — no regression, just no precision gain.
            if is_speculative:
                continue
            out.append((module, _WILDCARD, False))
        else:
            out.append((module, sorted(attrs_by_alias[alias]), is_speculative))
    return out


def _extract_imports(source: str, filename: str = "<unknown>") -> List[str]:
    """Legacy wrapper — module names only. Kept so older callers keep
    working; new code should use :func:`_extract_imports_detailed`."""
    return [t[0] for t in _extract_imports_detailed(source, filename)]


def _resolve_relative(rel_import: str, importer_rel_path: str) -> Optional[str]:
    """Turn ``..pkg.sub`` (seen in ``importer_rel_path``) into an absolute
    dotted module name.

    Returns None if the relative path escapes the project root.
    """
    m = _RELATIVE_IMPORT_RE.match(rel_import)
    if not m or not m.group(1):
        return rel_import  # not actually relative

    dots = len(m.group(1))
    rest = m.group(2)

    # Parent directory of the importing file = its package.
    importer_parts = [p for p in importer_rel_path.split("/") if p and p != "."]
    # Drop the filename itself (last segment).
    pkg_parts = importer_parts[:-1] if importer_parts else []

    # ``from . import x`` ⇒ same package, pops 0 dirs;
    # ``from .. import x`` ⇒ pops 1 dir; etc.
    pops = dots - 1
    if pops > len(pkg_parts):
        return None
    if pops:
        pkg_parts = pkg_parts[:-pops]

    combined = list(pkg_parts)
    if rest:
        combined.extend(rest.split("."))
    return ".".join(combined) if combined else None


# ── Core scanner (source-agnostic) ──────────────────────────────────────

def scan_reverse_deps_detailed(
    target_files: Iterable[str],
    project_files: Mapping[str, str],
) -> Dict[str, Optional[List[str]]]:
    """Return a per-file map of which symbols each importer uses.

    For every file in ``project_files`` that statically imports from a
    target, the value is one of:

    * a **sorted, deduped list of fully-qualified symbol names** (e.g.
      ``["utils.foo", "utils.Bar"]``) — the symbols the importer pulled
      out of target modules. Symbol qualification uses the target's
      dotted module path.
    * ``None`` (wildcard) — the importer did ``import target`` or
      ``from target import *``; any symbol could be in play, so callers
      must treat this as "conflict conservatively".

    This is the 0.2.2 enrichment over :func:`scan_reverse_deps` (which
    only returns the set of importer files). Both live in the same
    analyzer because computing symbols is almost free once we're walking
    the AST anyway.
    """
    targets_norm: Set[str] = {_normalize_rel(t) for t in target_files}
    # Map target module → canonical module name used for symbol qualification
    target_modules: Dict[str, str] = {}
    for t in targets_norm:
        m = _path_to_module(t)
        if m:
            target_modules[m] = m
    if not target_modules:
        return {}

    # Importer file → set of qualified symbols (or None for wildcard)
    raw: Dict[str, Optional[Set[str]]] = {}

    for raw_path, content in project_files.items():
        rel = _normalize_rel(raw_path)
        if not rel.endswith(".py"):
            continue
        if rel in targets_norm:
            continue

        for imp_mod, imp_symbols, is_speculative in _extract_imports_detailed(
            content, filename=rel,
        ):
            resolved = (
                _resolve_relative(imp_mod, rel)
                if imp_mod.startswith(".")
                else imp_mod
            )
            if not resolved:
                continue

            # Does this import hit any target module?
            for tmod in target_modules:
                # Exact module match.
                if resolved == tmod:
                    hit_module = tmod
                # Submodule of a target package (target is pkg/__init__.py).
                # Only real ``import pkg.sub`` statements are allowed to
                # trigger this; speculative entries from
                # ``from pkg import mod`` are rejected here because the
                # legacy ``(pkg, [mod])`` tuple from the SAME import
                # statement has already been counted for the pkg-level
                # target, and a wildcard here would overwrite that
                # precise result.
                elif resolved.startswith(tmod + ".") and not is_speculative:
                    hit_module = tmod
                    # Treat "from pkg.sub import x" as accessing both the
                    # submodule and the name — wildcard for the package
                    # since we can't tell what x is without following the
                    # module graph.
                    # For v0.2.2 we keep it simple: flag wildcard.
                    raw[rel] = None
                    break
                else:
                    continue

                # Record symbols for this match.
                existing = raw.get(rel)
                if existing is None and rel in raw:
                    # already wildcard — nothing else to do; wildcard wins
                    break

                if imp_symbols is None:
                    # bare import or star → wildcard
                    raw[rel] = None
                else:
                    if existing is None and rel not in raw:
                        existing = set()
                    qualified = {f"{hit_module}.{s}" for s in imp_symbols}
                    # merge
                    if existing is None:
                        # Only reachable when rel is genuinely absent; the
                        # "already wildcard" case breaks out above.
                        raw[rel] = qualified
                    else:
                        existing.update(qualified)
                        raw[rel] = existing
                break  # only one target can match per import stmt

    # Freeze: sort lists, keep None for wildcards.
    out: Dict[str, Optional[List[str]]] = {}
    for rel, syms in raw.items():
        if syms is None:
            out[rel] = None
        else:
            out[rel] = sorted(syms)
    return out


def scan_reverse_deps(
    target_files: Iterable[str],
    project_files: Mapping[str, str],
) -> List[str]:
    """Return the files in ``project_files`` that statically import any
    symbol defined in ``target_files``.

    Thin wrapper over :func:`scan_reverse_deps_detailed` kept for
    0.2.1 callers — discards symbol info and returns just the file set.
    """
    return sorted(scan_reverse_deps_detailed(target_files, project_files).keys())


# ── Filesystem adapter ──────────────────────────────────────────────────

def collect_python_sources_from_dir(project_root: str) -> Dict[str, str]:
    """Walk ``project_root`` and return a ``{rel_path: content}`` map of
    every .py file outside the standard skip list.

    Useful as the ``project_files`` argument to :func:`scan_reverse_deps`
    for callers that have the project on local disk (MCP / CLI).
    """
    root = Path(project_root)
    if not root.is_dir():
        return {}
    root_resolved = root.resolve()

    out: Dict[str, str] = {}
    for py_file in root.rglob("*.py"):
        try:
            rel = py_file.resolve().relative_to(root_resolved)
        except (ValueError, OSError):
            continue
        if any(
            part in _SKIP_DIRS or (part.startswith(".") and part != ".")
            for part in rel.parts
        ):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out[str(rel).replace(os.sep, "/")] = content
    return out


def scan_reverse_deps_from_dir(
    target_files: Iterable[str],
    project_root: str,
) -> List[str]:
    """Filesystem convenience wrapper around :func:`scan_reverse_deps`.

    Target paths may be absolute or relative to ``project_root``; absolute
    paths are rebased to project-relative before matching.
    """
    root = Path(project_root)
    if not root.is_dir():
        return []
    root_resolved = root.resolve()

    targets_rel: List[str] = []
    for f in target_files:
        p = Path(f)
        if p.is_absolute():
            try:
                rel = p.resolve().relative_to(root_resolved)
                targets_rel.append(str(rel).replace(os.sep, "/"))
            except (ValueError, OSError):
                continue
        else:
            targets_rel.append(_normalize_rel(f))

    sources = collect_python_sources_from_dir(project_root)
    return scan_reverse_deps(targets_rel, sources)
