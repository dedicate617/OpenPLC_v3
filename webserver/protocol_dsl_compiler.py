#!/usr/bin/env python3
"""Compile Protocol DSL session JSON into compact IR for C++ runtime.

Design intent:
- Parsing/validation remains in Python (easy iteration and grammar tooling)
- Runtime communication loop stays in C++ for performance
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

TOKEN_FIELD_RE = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_\[\]\.]*):(.*)\}$")
TOKEN_CHECKSUM_RE = re.compile(r"^\{(CRC16_MODBUS|LRC_ASCII|XOR8|SUM8)\}$")
HEX_BYTE_RE = re.compile(r"^(?:0x)?[0-9A-Fa-f]{2}$")


def _compile_template(template: str) -> List[Dict[str, Any]]:
    ir: List[Dict[str, Any]] = []
    for t in template.strip().split():
        if t in {"CR", "LF", "CRLF"}:
            ir.append({"op": "term", "value": t})
            continue
        m = TOKEN_CHECKSUM_RE.match(t)
        if m:
            ir.append({"op": "checksum", "algo": m.group(1)})
            continue
        m = TOKEN_FIELD_RE.match(t)
        if m:
            field = m.group(1)
            ftype_full = m.group(2)
            ftype = ftype_full.split(",", 1)[0].strip()
            ir.append({"op": "field", "field": field, "type": ftype, "raw_type": ftype_full})
            continue
        if t.startswith('"') and t.endswith('"'):
            ir.append({"op": "ascii", "value": t[1:-1]})
            continue
        if HEX_BYTE_RE.fullmatch(t):
            ir.append({"op": "byte", "value": int(t, 16)})
            continue
        if t in {",", ";", "|"}:
            ir.append({"op": "ascii", "value": t})
            continue
        raise ValueError(f"unsupported token in template: {t}")
    return ir


def compile_session(session: Dict[str, Any]) -> Dict[str, Any]:
    required = ["version", "session_name", "protocol_kind", "transport", "tx", "rx", "bindings"]
    missing = [k for k in required if k not in session]
    if missing:
        raise ValueError(f"missing required keys: {missing}")
    if "template" not in session["tx"] or "template" not in session["rx"]:
        raise ValueError("tx.template and rx.template are required")

    return {
        "ir_version": 1,
        "session_name": session["session_name"],
        "protocol_kind": session["protocol_kind"],
        "transport": session["transport"],
        "match": session.get("match", {}),
        "runtime": session.get("runtime", {}),
        "bindings": session.get("bindings", []),
        "tx_ir": _compile_template(session["tx"]["template"]),
        "rx_ir": _compile_template(session["rx"]["template"]),
    }


def compile_file(session_path: Path, output_path: Path) -> None:
    session = json.loads(session_path.read_text(encoding="utf-8"))
    compiled = compile_session(session)
    output_path.write_text(json.dumps(compiled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compile Protocol DSL JSON to compiled IR JSON")
    parser.add_argument("session", type=Path, help="Path to DSL session json")
    parser.add_argument("output", type=Path, help="Path to output compiled IR json")
    args = parser.parse_args()

    compile_file(args.session, args.output)
    print(f"compiled: {args.session} -> {args.output}")
