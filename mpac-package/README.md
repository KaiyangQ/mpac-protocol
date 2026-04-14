# mpac-protocol

[![arXiv](https://img.shields.io/badge/arXiv-2604.09744-b31b1b.svg)](https://arxiv.org/abs/2604.09744)

**Multi-Principal Agent Coordination Protocol — Python reference runtime.**

📄 **Paper:** [MPAC: A Multi-Principal Agent Coordination Protocol for Interoperable Multi-Agent Collaboration](https://arxiv.org/abs/2604.09744) (arXiv:2604.09744)

When multiple AI agents — each serving a different person, team, or
organization — need to work together over shared state, existing
protocols come up short. MCP standardizes how one agent invokes tools;
A2A standardizes how one orchestrator delegates to its own workers;
neither covers what happens when two agents from *different* principals
meet as peers over a shared repository, a shared itinerary, a shared
contract draft, or any other piece of state that neither principal
controls alone.

**MPAC** is the application-layer protocol that fills that gap. It
defines how agents declare intent before acting, how the coordinator
surfaces overlap as structured conflicts, how those conflicts get
resolved with explicit governance authority, and how every consequential
action carries causal context for after-the-fact audit across
organizational boundaries.

This package is the Python reference runtime: a WebSocket coordinator,
an interactive Claude-backed agent, and the full protocol state machine
from the specification.

## Install

```bash
pip install mpac-protocol
```

Python 3.9+ required. The package depends on `websockets` and
`anthropic`; bring your own Anthropic API key.

## Minimal example

Host side — start a coordinator that shares any directory on your
machine:

```python
import asyncio
from mpac_protocol import MPACServer

async def main():
    server = MPACServer(
        session_id="collab-session-001",
        host="0.0.0.0",
        port=8766,
        workspace_dir="/path/to/any/directory/you/want/to/share",
    )
    await server.run()

asyncio.run(main())
```

The loader walks `workspace_dir` recursively and safely skips VCS
metadata (`.git`, `.hg`), build caches (`__pycache__`, `node_modules`,
`.venv`, `dist`, `build`, …), IDE configs, OS cruft, and binary files.
Whatever text files remain become the shared workspace. The pip package
does **not** bundle any workspace files of its own.

Guest side — connect an interactive agent to someone else's
coordinator:

```python
import asyncio
from mpac_protocol import MPACAgent

async def main():
    agent = MPACAgent(
        name="Bob",
        api_key="sk-ant-...",
        model="claude-sonnet-4-6",
        role_description="Collaborative AI agent operated by Bob",
        roles=["contributor"],       # optional: owner, arbiter, contributor
        principal_id="agent:Bob",    # optional: custom identity
    )
    await agent.connect("ws://192.168.1.42:8766", "collab-session-001")
    await agent.run_interactive()
    await agent.close()

asyncio.run(main())
```

## Two-machine worked example

A complete, copy-paste end-to-end example for two people on two
different computers lives in the repo at
[`examples/two_machine_demo/`](https://github.com/KaiyangQ/mpac-protocol/tree/main/examples/two_machine_demo).
It ships a host `run.py`, a guest `run.py`, a sample workspace with
three buggy Python files, and a README walking through both LAN mode
(same WiFi) and Internet mode (ngrok).

Clone and try it:

```bash
git clone https://github.com/KaiyangQ/mpac-protocol.git mpac
cd mpac/examples/two_machine_demo/host
cp config.example.json config.json   # add your Anthropic API key
python run.py                        # prints the WebSocket URL to share
```

## API reference

### MPACServer

```python
MPACServer(
    session_id:    str,
    host:          str  = "0.0.0.0",
    port:          int  = 8766,
    workspace_dir: str | None = None,   # directory to share; None = empty workspace
    # Optional coordinator tuning (passed via **kwargs):
    execution_model:          str   = "post_commit",   # or "pre_commit"
    compliance_profile:       str   = "core",           # or "governance"
    security_profile:         str   = "open",           # or "authenticated", "verified"
    unavailability_timeout_sec: float = 90.0,
    resolution_timeout_sec:     float = 300.0,
    intent_claim_grace_sec:     float = 0.0,
    role_policy:              dict | None = None,
)
```

Call `await server.run()` to start listening. The server loads every
text file under `workspace_dir` into an in-memory `FileStore`, skipping
VCS metadata, build caches, and binary files automatically.

### MPACAgent

```python
MPACAgent(
    name:             str,
    api_key:          str,               # Anthropic API key
    model:            str  = "claude-sonnet-4-6",
    role_description: str | None = None,
    roles:            list[str] | None = None,       # default: ["contributor"]
    principal_id:     str | None = None,              # default: "agent:{name}"
)
```

#### Connection

```python
await agent.connect(
    uri:           str,            # ws:// or wss:// — any WebSocket endpoint
    session_id:    str,
    extra_headers: dict | None = None,  # transport-specific HTTP headers
)
```

The protocol is transport-agnostic. Pass any reachable WebSocket URI —
LAN address, SSH tunnel, Cloudflare Tunnel, Tailscale, or any relay
service. Use `extra_headers` for transports that require custom HTTP
headers during the handshake.

#### High-level workflows

| Method | Description |
|--------|------------|
| `run_interactive()` | Interactive CLI: view files, give tasks, see diffs |
| `execute_task(task)` | Programmatic: intent → conflict check → fix → commit |
| `run_task(task)` | Full lifecycle: HELLO → execute_task → GOODBYE |

#### Extended protocol operations

| Method | Protocol Feature |
|--------|-----------------|
| `do_propose(intent_id, op_id, target)` | Pre-commit authorization (OP_PROPOSE) |
| `propose_and_commit(...)` | Complete pre-commit flow (propose → auth → commit) |
| `do_claim_intent(...)` | Fault recovery: take over a crashed agent's intent |
| `do_escalate_conflict(...)` | Escalate a dispute to a designated arbiter |
| `do_resolve_conflict(...)` | Arbiter renders a binding resolution |
| `do_ack_conflict(...)` | Acknowledge or dispute a conflict |
| `do_heartbeat(status)` | Maintain liveness |
| `do_update_intent(...)` | Modify intent scope or objective mid-session |

### Lower-level building blocks

If you want to embed MPAC into your own agent runtime instead of using
`MPACAgent`, the `mpac_protocol.core` module exposes:
`SessionCoordinator`, state machines, envelopes, scope objects,
watermarks, and principal models.

## Protocol specification

The full normative specification is [`SPEC.md`](https://github.com/KaiyangQ/mpac-protocol/blob/main/SPEC.md)
on the `opensource` branch — 30 sections covering all five layers
(Session, Intent, Operation, Conflict, Governance), 21 message types,
three state machines with normative transition tables, two execution
models (pre-commit / post-commit), three security profiles (open /
authenticated / verified), Lamport-clock causal watermarking,
optimistic concurrency control, and Backend Health Monitoring.

The runtime in this package is faithful to that specification and is
cross-tested against an independent TypeScript reference implementation
in the same repository (14 messages exchanged bidirectionally with
byte-identical wire format).

## Scope — protocol, not platform

MPAC defines **what agents say to each other**: intent declarations,
conflict detection, resolution negotiation, causal-context commits, and
governance authority. It does not prescribe how the underlying network
is provisioned. The reference runtime uses WebSocket as a convenient
default transport, but the coordinator can sit behind any infrastructure
you choose — a LAN socket, an SSH tunnel, a cloud relay, a mesh VPN, or
a managed WebSocket service. Networking, deployment topology, and
infrastructure automation are engineering concerns outside the protocol
boundary; MPAC intentionally stays silent on them so that implementers
are free to make their own trade-offs.

## Status

**Draft / experimental.** The protocol is at v0.1.13. This package is
at 0.1.0. Not yet stable for production interoperability — intended for
reference implementations, research prototypes, and early ecosystem
feedback.

## License

Apache-2.0. See [`LICENSE`](https://github.com/KaiyangQ/mpac-protocol/blob/main/LICENSE).

## Links

- [GitHub repository](https://github.com/KaiyangQ/mpac-protocol)
- [v0.1.13 release notes](https://github.com/KaiyangQ/mpac-protocol/releases/tag/v0.1.13)
- [Specification (SPEC.md)](https://github.com/KaiyangQ/mpac-protocol/blob/main/SPEC.md)
- [Two-machine demo](https://github.com/KaiyangQ/mpac-protocol/tree/main/examples/two_machine_demo)
- [Report an issue](https://github.com/KaiyangQ/mpac-protocol/issues)
