"""Compare canonical bytes: Python vs what the Oracle Rust code would produce.

Reads the wire JSON payload from /tmp/debug_wire.json, simulates what the
oracle does (parse with serde_json, reconstruct signable, canonicalize),
and compares with Python's canonical bytes."""
import json
import subprocess
from pathlib import Path

# Read the wire payload
wire = Path("/tmp/debug_wire.json").read_text()
payload = json.loads(wire)

# Remove signature to get signable
signable = {k: v for k, v in payload.items() if k != "signature"}

# Python canonical
from integrity_sdk import bcc
py_canonical = bcc.canonical_json_bytes(signable)
print(f"Python canonical: {len(py_canonical)} bytes")

# Now simulate what serde_json does:
# 1. Parse the wire JSON into serde_json::Value
# 2. Extract the signable fields
# 3. Run canonical_json_bytes (sorted keys + ASCII escaping)
#
# The key difference: serde_json::to_value for floats uses Ryu,
# which may produce DIFFERENT decimal representations than Python.
#
# Let's check by re-serializing through json.loads (which uses Python's parser)
# and then through a subprocess that uses serde_json

# First check: what does Python's json.dumps produce for the same data?
# This is what Python signs over:
py_str = py_canonical.decode('utf-8')

# Now: simulate serde_json by re-serializing each float through a known
# representation
# Actually, the simplest test: just check if the wire payload, when parsed
# and re-serialized with sort_keys+separators, matches py_canonical
wire_parsed = json.loads(wire)
del wire_parsed["signature"]

# Re-canonicalize
re_canonical = json.dumps(wire_parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

print(f"Re-canonical:     {len(re_canonical)} bytes")
print(f"Match: {py_canonical == re_canonical}")

if py_canonical != re_canonical:
    for i in range(min(len(py_canonical), len(re_canonical))):
        if py_canonical[i] != re_canonical[i]:
            print(f"DIFF at byte {i}:")
            ctx = 50
            print(f"  Python:  ...{py_canonical[max(0,i-ctx):i+ctx].decode('utf-8', errors='replace')}...")
            print(f"  Re-can:  ...{re_canonical[max(0,i-ctx):i+ctx].decode('utf-8', errors='replace')}...")
            break

# The REAL test: check what happens to the floats specifically
# Parse the canonical JSON and look at float formatting
import re
# Find all numbers in the canonical JSON
py_nums = re.findall(r'(?<=[,:{\[])(-?\d+\.?\d*(?:[eE][+-]?\d+)?)', py_str)
print(f"\nNumbers in canonical: {len(py_nums)}")

# Check: does the float 0.0 round-trip to 0.0 in serde_json?
# serde_json serializes 0.0 as 0.0, same as Python. Good.
# But what about 1.0? serde_json uses 1.0, Python uses 1.0. Good.
# What about 1785381700.0706544?
# Ryu: 1.7853817000706544e9 or 1785381700.0706544? Ryu prefers shortest.
# Let's check by looking at serde_json source...
# Actually, serde_json by default uses to_string() for f64 which uses Ryu
# and produces the shortest representation.
# Python 3.1+ also uses the shortest representation (David Gay's algorithm).
# They should agree for most cases.

# BUT: there's a CRUCIAL difference. When requests.post(json=payload) serializes,
# it uses json.dumps(payload) with default settings. json.dumps by default
# does NOT use ensure_ascii=True (it's False by default).
# So if the payload contains non-ASCII chars, they'll be sent as raw UTF-8.
# Then serde_json parses them as UTF-8 strings. Then canonical_json_bytes
# re-serializes with AsciiEscapingFormatter which escapes non-ASCII to \uXXXX.
# But Python's canonical used ensure_ascii=True which also escapes to \uXXXX.
# So they should match... UNLESS the way requests serializes differs.

# Wait - requests uses json.dumps(payload) which by default uses ensure_ascii=True!
# Actually no - let me check.
print("\n--- requests default json serialization ---")
import requests.models
# Check the default encoder
print(f"requests uses json module with default settings")
# requests.post(json=...) calls json.dumps(data) directly

# The actual requests source code does:
# body = complexjson.dumps(json, allow_nan=False)
# where complexjson is just json
# So it uses json.dumps(payload, allow_nan=False)
# json.dumps defaults: ensure_ascii=True, sort_keys=False, separators=(', ', ': ')
# Wait - json.dumps defaults separators to (', ', ': ') which ADDS SPACES!
# That means the wire JSON has spaces that the canonical JSON doesn't.
# But that's fine because serde_json ignores whitespace when parsing.

# I think the issue might be something very simple: an integer vs float mismatch.
# Python's json.dumps serializes 1.0 as "1.0" but serde_json might parse "1.0"
# as 1.0 (float) while it would parse "1" as 1 (integer).
# When the oracle reconstructs the signable with serde_json::json!(),
# the derived_signals values are f64 fields, so they stay as f64.
# But otel_spans is Vec<serde_json::Value>, so serde_json decides the type.

# Let me check: does serde_json serialize f64 1.0 differently than Python?
# serde_json: 1.0 -> "1.0" (Ryu)
# Python:     1.0 -> "1.0" (json.dumps)
# OK they match.

# Let me check: what about derived_signals?
# Oracle struct: entropy: f64, grounding: f64, sacrifice: f64, compliance: f64
# The derived dict from Python has entropy=1.0, grounding=1.0
# But it might also have sacrifice=0.0, compliance=0.0
# Wait - the 5-line test derives from a batch. Let me check the derived values.

print("\n--- Derived signals in the signable ---")
print(json.dumps(signable["derived_signals"], indent=2))
print("\n--- Schema version ---")
print(f"schema_version: {signable['schema_version']} (type: {type(signable['schema_version']).__name__})")
