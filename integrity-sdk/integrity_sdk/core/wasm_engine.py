"""In-process policy evaluation: a signed pack's Rego, compiled to WebAssembly by OPA itself.

Why this exists
---------------
`OpaClient` evaluates a pack by talking to an OPA *server*: one more daemon to start, supervise,
version and keep from being clobbered by another gate's pack (the 2026-10-24 outage). This client
evaluates the same decision in the gate's own process, so there is no daemon, no port and no
"OPA unreachable". It deliberately mirrors `OpaClient`'s surface (`install`, `query`, `decide`,
`installed_pack_hash`) and raises the same `OpaError`, so a gate's failure handling is unchanged.

Where the WebAssembly comes from
--------------------------------
Not from a Rego reimplementation (rego-cpp/`regopy` could not even load `packs/bcc`). The module is
produced by `opa build -t wasm`, i.e. by OPA's own compiler, at pack-build time (`wasm_build.py`), and
is shipped **inside the signed pack** as `policy.wasm`. `pack_hash` already covers every file in the
pack, so the signature covers the wasm exactly as it covers the Rego, and a device runs bytes that were
verified, never a compile it did itself.

Failure postures (stated per module, as this repo requires)
-----------------------------------------------------------
* **Fail closed.** Anything unexpected -- no wasm in the pack, a module that will not load, a trap, an
  `opa_abort`, an unsupported builtin call, malformed output -- raises `OpaError`; `decide` turns that
  into the pack's deny via `decision.resolve(..., evaluator_error=...)`. Nothing here can allow.
* **Builtins are an allowlist.** The module declares which builtins it needs from the host
  (`builtins()` export). Only `sprintf`, and only the forms reproduced exactly below, is implemented; a
  pack that needs another builtin is refused at install (`WASM_UNSUPPORTED_BUILTIN`) instead of
  evaluating it approximately.
* **No shared state between evaluations.** Each query uses a fresh instance, so one input cannot
  influence the next and there is no heap to leak or corrupt.

Equivalence with OPA is *tested*, not assumed: `tests/unit/test_core_wasm_engine.py` runs this client and
a real OPA server over the same corpus and fails on any difference.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, Mapping, Optional

try:
    from wasmtime import Engine, FuncType, Limits, Linker, Memory, MemoryType, Module, Store, Trap, ValType, WasmtimeError
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError("integrity_sdk.core.wasm_engine needs wasmtime: pip install 'integrity-sdk[wasm]'") from exc

from .decision import ENFORCE, NO_MATCH, Decision, resolve
from .opa import OpaError, entrypoint_path
from .packs import WASM_FILE, LoadedPack  # WASM_FILE re-exported for callers that import it from here

_PAGE = 65536
# Resource ceilings so a hostile input or policy cannot exhaust the gate.
_MAX_INPUT_BYTES = 1 << 20


class _Abort(Exception):
    pass


def _go_sprintf(fmt: str, args: list) -> str:
    """The subset of OPA's sprintf this repo's policies use, reproduced exactly.

    `%v`/`%s` of a string, `%v`/`%d` of an integer, and `%%`. Anything else (floats, bools, arrays,
    other verbs) raises: OPA formats those with Rego/Go rules this client does not copy, and an
    approximate message inside an authorization gate is worse than a refusal.
    """
    out, i, n = [], 0, 0
    while i < len(fmt):
        c = fmt[i]
        if c != "%":
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= len(fmt):
            raise _Abort("sprintf: trailing %")
        verb = fmt[i]
        i += 1
        if verb == "%":
            out.append("%")
            continue
        if n >= len(args):
            raise _Abort("sprintf: too few arguments")
        arg = args[n]
        n += 1
        if isinstance(arg, bool):
            raise _Abort("sprintf: bool arguments are not supported")
        if verb in ("v", "s") and isinstance(arg, str):
            out.append(arg)
        elif verb in ("v", "d") and isinstance(arg, int):
            out.append(str(arg))
        else:
            raise _Abort(f"sprintf: unsupported %{verb} for {type(arg).__name__}")
    if n != len(args):
        raise _Abort("sprintf: too many arguments")
    return "".join(out)


_HOST_BUILTINS: Dict[str, Callable[..., Any]] = {"sprintf": _go_sprintf}


class _Compiled:
    """A pack's module, compiled once and checked against the builtin allowlist."""

    def __init__(self, wasm: bytes, entrypoint: str):
        self.engine = Engine()
        try:
            self.module = Module(self.engine, wasm)
        except (WasmtimeError, ValueError) as exc:
            raise OpaError("WASM_LOAD_FAILED", str(exc)) from exc
        self.entrypoint_name = entrypoint_path(entrypoint)
        # Probe once: which builtins does the module want from the host, and is our entrypoint in it?
        inst = _Instance(self)
        try:
            self.builtin_names = {int(v): k for k, v in inst.read_json(inst.x["builtins"](inst.store)).items()}
            entrypoints = inst.read_json(inst.x["entrypoints"](inst.store))
        except (_Abort, WasmtimeError, Trap, ValueError, AttributeError) as exc:
            raise OpaError("WASM_LOAD_FAILED", f"module does not expose the OPA ABI: {exc}") from exc
        unsupported = sorted(set(self.builtin_names.values()) - set(_HOST_BUILTINS))
        if unsupported:
            raise OpaError("WASM_UNSUPPORTED_BUILTIN", f"pack needs host builtins this client does not implement: {unsupported}")
        if self.entrypoint_name not in entrypoints:
            raise OpaError("WASM_LOAD_FAILED", f"module has no entrypoint {self.entrypoint_name!r}; has {sorted(entrypoints)}")
        self.entrypoint_id = int(entrypoints[self.entrypoint_name])


class _Instance:
    def __init__(self, compiled: _Compiled):
        self.c = compiled
        self.store = Store(compiled.engine)
        linker = Linker(compiled.engine)
        self.memory = Memory(self.store, MemoryType(Limits(2, None)))
        linker.define(self.store, "env", "memory", self.memory)

        def abort(addr: int) -> None:
            raise _Abort(f"opa_abort: {self._cstr(addr)}")

        linker.define_func("env", "opa_abort", FuncType([ValType.i32()], []), abort)
        for arity in range(5):
            linker.define_func(
                "env", f"opa_builtin{arity}",
                FuncType([ValType.i32()] * (arity + 2), [ValType.i32()]),
                self._make_builtin(),
            )
        self.x = linker.instantiate(self.store, compiled.module).exports(self.store)

    # -- memory helpers --------------------------------------------------------------------
    def _cstr(self, addr: int) -> str:
        buf = bytearray()
        while True:
            chunk = self.memory.read(self.store, addr + len(buf), addr + len(buf) + 1)
            if chunk[0] == 0:
                return buf.decode("utf-8", "replace")
            buf.append(chunk[0])
            if len(buf) > _MAX_INPUT_BYTES:
                raise _Abort("unterminated string in module memory")

    def read_json(self, value_addr: int) -> Any:
        return json.loads(self._cstr(self.x["opa_json_dump"](self.store, value_addr)))

    def write_json(self, obj: Any) -> int:
        raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(raw) > _MAX_INPUT_BYTES:
            raise _Abort("input too large")
        addr = self.x["opa_malloc"](self.store, len(raw))
        self.memory.write(self.store, raw, addr)
        value = self.x["opa_json_parse"](self.store, addr, len(raw))
        if value == 0:
            raise _Abort("module could not parse the input JSON")
        return value

    def _make_builtin(self) -> Callable[..., int]:
        def call(builtin_id: int, _ctx: int, *arg_addrs: int) -> int:
            name = self.c.builtin_names.get(builtin_id)
            fn = _HOST_BUILTINS.get(name or "")
            if fn is None:
                raise _Abort(f"module called unimplemented builtin id {builtin_id}")
            return self.write_json(fn(*[self.read_json(a) for a in arg_addrs]))

        return call

    # -- evaluation ------------------------------------------------------------------------
    def evaluate(self, opa_input: Mapping[str, Any]) -> Any:
        ctx = self.x["opa_eval_ctx_new"](self.store)
        self.x["opa_eval_ctx_set_input"](self.store, ctx, self.write_json(dict(opa_input)))
        self.x["opa_eval_ctx_set_data"](self.store, ctx, self.write_json({}))
        self.x["opa_eval_ctx_set_entrypoint"](self.store, ctx, self.c.entrypoint_id)
        status = self.x["eval"](self.store, ctx)
        if status != 0:
            raise _Abort(f"eval returned status {status}")
        results = self.read_json(self.x["opa_eval_ctx_get_result"](self.store, ctx))
        if not isinstance(results, list):
            raise OpaError("OPA_MALFORMED_RESPONSE", "module returned a non-list result set")
        if not results:
            return NO_MATCH
        first = results[0]
        if not isinstance(first, dict) or "result" not in first:
            raise OpaError("OPA_MALFORMED_RESPONSE", "module result has no 'result'")
        return first["result"]


class WasmPolicyClient:
    """Drop-in for `OpaClient` that evaluates in-process. See the module docstring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._installed_pack_hash: Optional[str] = None
        self._compiled: Optional[_Compiled] = None

    @property
    def installed_pack_hash(self) -> Optional[str]:
        return self._installed_pack_hash

    def install(self, pack: LoadedPack) -> None:
        """Compile the pack's verified `policy.wasm`, or raise `OpaError` (recording no installed pack)."""
        with self._lock:
            self._installed_pack_hash = None
            self._compiled = None
            wasm = pack.files.get(WASM_FILE)
            if wasm is None:
                raise OpaError("WASM_MISSING", f"the pack has no {WASM_FILE}; build it with wasm_build.build_pack_wasm before signing")
            self._compiled = _Compiled(wasm, pack.entrypoint)
            self._installed_pack_hash = pack.pack_hash

    def query(self, pack: LoadedPack, opa_input: Mapping[str, Any]) -> Any:
        """Raw entrypoint result, or `NO_MATCH` when undefined. Raises `OpaError` on any failure."""
        compiled = self._compiled
        if compiled is None or self._installed_pack_hash != pack.pack_hash:
            raise OpaError("PACK_NOT_INSTALLED", "the pack being enforced is not the one installed")
        try:
            return _Instance(compiled).evaluate(opa_input)
        except OpaError:
            raise
        except (_Abort, WasmtimeError, Trap) as exc:
            raise OpaError("WASM_EVAL_ERROR", str(exc)) from exc
        except (TypeError, ValueError):
            raise

    def decide(
        self,
        pack: Optional[LoadedPack],
        event_class: str,
        opa_input: Mapping[str, Any],
        *,
        mode: str = ENFORCE,
    ) -> Decision:
        """Evaluate and resolve under the decision contract. Never raises for policy/evaluator failures."""
        if pack is None:
            return resolve(event_class, None, event_defaults=None, mode=mode)
        with self._lock:
            try:
                result = self.query(pack, opa_input)
            except (OpaError, OSError, ValueError, TypeError) as exc:
                return resolve(
                    event_class, None, event_defaults=pack.event_defaults, mode=mode,
                    pack_hash=pack.pack_hash, evaluator_error=exc,
                )
        return resolve(event_class, result, event_defaults=pack.event_defaults, mode=mode, pack_hash=pack.pack_hash)
