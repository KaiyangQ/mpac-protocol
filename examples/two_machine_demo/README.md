# Two-Machine MPAC Demo

A minimal end-to-end example of two people on two different computers
collaborating through MPAC. Each side runs one Claude-backed agent; the
host machine also runs the coordinator and shares a directory of source
files; the guest joins over WebSocket.

This is the example to read first if you want to feel what MPAC actually
does — *intent → conflict → resolution → commit* — without wading through
the reference-implementation demos.

## What you get

- **Host side** (`host/run.py`): runs the MPAC coordinator + a local
  agent named Alice. Shares a directory (default `host/workspace/`) with
  every guest that joins.
- **Guest side** (`guest/run.py`): runs a local agent named Bob and
  connects to the host's coordinator. Bob sees the same files Alice
  sees, in real time.
- **Sample workspace** (`host/workspace/api.py`, `auth.py`, `utils.py`):
  three small Python files with intentional bugs, used as the shared
  state. Replace this with any directory you actually care about.

The coordinator does **not** bundle any "shared code" with the MPAC
package. Whatever directory you point `--workspace` at becomes the
shared workspace. The MPAC pip package contains only the protocol
runtime (coordinator, agent, state machines, schemas) — your project
files stay on your disk.

## Prerequisites

- Python 3.9+ on both machines
- An Anthropic API key on each machine
  (https://console.anthropic.com/settings/keys)
- Either:
  - **LAN mode**: both machines on the same WiFi / LAN, **or**
  - **Internet mode**: an [ngrok](https://ngrok.com/) account (or any
    similar tunnel) on the host machine

## Install (on both machines)

From inside the cloned repository:

```bash
pip install ./mpac-package
```

Or, when the package is on PyPI:

```bash
pip install mpac_protocol
```

## Configure (on both machines)

Each side needs its own `config.json` with an Anthropic API key. Both
sides ship a `config.example.json` you can copy:

```bash
# on the host
cd examples/two_machine_demo/host
cp config.example.json config.json
$EDITOR config.json     # paste your sk-ant-... key

# on the guest (different machine)
cd examples/two_machine_demo/guest
cp config.example.json config.json
$EDITOR config.json     # paste your sk-ant-... key
```

`config.json` is gitignored so your key won't be committed by accident.

## Run — LAN mode (same WiFi)

**Host machine:**

```bash
cd examples/two_machine_demo/host
python run.py
```

You will see something like:

```
+----------------------------------------------------+
| Share this with the guest:                         |
|                                                    |
|   ws://192.168.1.42:8766                           |
|                                                    |
| They run:                                          |
|   python run.py ws://192.168.1.42:8766             |
+----------------------------------------------------+
```

Send the `ws://...` line to the guest in chat / Slack / SMS.

**Guest machine:**

```bash
cd examples/two_machine_demo/guest
python run.py ws://192.168.1.42:8766    # the URI from the host
```

That's it. Both sides are now in the same MPAC session. Type `help` in
either prompt to see the commands.

## Run — Internet mode (different networks)

If the two machines are not on the same network (one home, one office,
one on a hotel WiFi), the host needs to expose the WebSocket port to
the Internet. The simplest way is ngrok:

```bash
# on the host, in a separate terminal
ngrok http 8766
```

ngrok prints a public URL like `https://xxxx.ngrok-free.dev`. Convert
that to a WebSocket URL by changing the scheme: `wss://xxxx.ngrok-free.dev`.
Send that to the guest:

```bash
# on the guest
python run.py wss://xxxx.ngrok-free.dev
```

The host's `python run.py` does **not** need any changes — ngrok just
forwards traffic to the local port.

## Use a different directory as the shared workspace

The default `--workspace` is `host/workspace/` (the three sample bug
files). To share an arbitrary directory of your own:

```bash
cd examples/two_machine_demo/host
python run.py --workspace ~/my_project
```

The host loader walks the directory recursively and skips:

- VCS metadata (`.git`, `.hg`, `.svn`)
- Build / cache directories (`__pycache__`, `.pytest_cache`,
  `node_modules`, `.venv`, `venv`, `dist`, `build`, `.next`, …)
- IDE configs (`.idea`, `.vscode`)
- OS cruft (`.DS_Store`, `Thumbs.db`)
- Binary files (anything that doesn't decode as UTF-8)

So pointing it at a real working repo is safe — you won't accidentally
share `.git/` packs or `node_modules/`. To customize the ignore lists,
import `MPACServer` directly and pass `ignore_dirs` / `ignore_files` to
`FileStore.load_directory`; see `mpac-package/src/mpac_protocol/server.py`.

## What you'll see in the prompt

Once both sides are connected, the prompt shows the shared workspace:

```
+------------------------------------------------------+
| Workspace (3 files)                                  |
+------------------------------------------------------+
| auth.py            1765 bytes  sha256:76ad893bc...   |
| api.py             1363 bytes  sha256:07d0460dc...   |
| utils.py            918 bytes  sha256:e1c4bb95d...   |
+------------------------------------------------------+
```

Useful commands (type `help` for the full list):

| Command | Effect |
|---|---|
| `view auth.py` | Read the current shared content of a file |
| `task Fix the bug in auth.py` | Hand a task to your local agent |
| `quit` | Leave the session |

When you give a task, your local agent will:

1. Read the file from the coordinator
2. Call Claude to draft a fix
3. Show you the diff
4. Announce its intent to MPAC (so the other agent can see what's
   coming)
5. Commit the change with optimistic concurrency control

If the other agent is touching an overlapping scope, you'll see a
`CONFLICT_REPORT` show up in real time and both agents will negotiate
through structured `CONFLICT_ACK` messages before either commits.

## Where the session output lands

When the host quits, the final state of the shared workspace and the
full message transcript are saved to `host/output/`:

- `host/output/<filename>` — the final content of every shared file,
  reconstructed from the in-memory `FileStore`
- `host/output/transcript.json` — every MPAC envelope that flowed
  through the coordinator, in causal order

The transcript is the same format the reference-implementation demos
use, so you can drop it into the same analysis tools.

## Troubleshooting

**`ERROR: cannot connect to ws://...`** — Either the host hasn't started
yet, you copied the URL wrong, or a firewall is blocking the port.
Check that the host's terminal still shows "Coordinator running" and
that you're using the exact URI it printed. On corporate WiFi, port
8766 is sometimes blocked — try ngrok mode instead.

**`ERROR: anthropic.api_key is empty`** — You forgot to copy
`config.example.json` to `config.json`, or you saved the file without
filling in the key. The key starts with `sk-ant-`.

**`Skipped (binary): ...` warnings on the host** — Expected. The host
loader skips anything that isn't UTF-8 text. If you want a binary file
to be shared, convert it to text first (e.g. base64).

**`pip install mpac_protocol` fails** — Make sure you're inside the
repo and the path is right (`pip install ./mpac-package` from the repo
root). On systems where `pip` points at Python 2, use `pip3` or
`python3 -m pip`.
