#!/bin/bash
# Run full cross-language interop test: Python ↔ TypeScript
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  MPAC v0.1.4 Cross-Language Interop Test"
echo "============================================"
echo ""

# Step 1: Ensure TS is built
echo "Step 1: Building TypeScript..."
cd ../typescript && npm run build 2>&1 | tail -1
cd "$SCRIPT_DIR"
echo ""

# Step 2: Generate Python messages
echo "Step 2: Generating Python messages..."
python3 generate_messages_py.py
echo ""

# Step 3: Process Python messages through TS coordinator + generate TS messages
echo "Step 3: Processing through TypeScript coordinator..."
node process_messages_ts.mjs
echo ""

# Step 4: Process TS messages through Python coordinator
echo "Step 4: Processing TS messages through Python coordinator..."
python3 consume_ts_messages.py
echo ""

echo "============================================"
echo "  Interop test complete"
echo "============================================"
