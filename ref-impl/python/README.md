# MPAC Python Reference Implementation (FROZEN — v0.1.13)

> **This directory is a frozen reference implementation snapshot.**
> It mirrors MPAC v0.1.13 as published in the paper and is paired with
> the TypeScript reference implementation in [`../typescript/`](../typescript/)
> for language-neutral cross-validation. **This code is NOT updated
> with subsequent fixes** to the live Python runtime.

For the live, pip-installable Python runtime — which includes the
reference coordinator plus `MPACServer`, `MPACAgent`, and any post-
v0.1.13 patches — see [`mpac-package/`](../../mpac-package/) and
`pip install mpac`.

## Why both exist

- **`ref-impl/python/`** (this directory) — frozen at v0.1.13, paired
  with `ref-impl/typescript/` for language-neutral validation in the
  paper. Core modules here are byte-identical to the v0.1.13 tag at
  the time the paper was written.
- **`mpac-package/`** — active development; published on PyPI as
  `mpac`; contains the ongoing runtime with `MPACServer` extensions,
  `MPACAgent` high-level workflows, and bug fixes accumulated after
  v0.1.13.

If you want to **run** the protocol, use `mpac-package/`.
If you want to **audit** the version that the paper describes, use
this directory.

## Structure

- `mpac/` — 7 core modules: coordinator, models, participant, state
  machines, envelope, scope, watermark
- `tests/` — 13 test files, 122 test cases covering the frozen runtime

## Installation (for auditing only)

```bash
cd ref-impl/python
pip install -e .
pytest tests/
```

This installs the package as `mpac-ref-py` (not `mpac`) so it won't
collide with the live `mpac-package/` runtime if both are on your
Python path.
