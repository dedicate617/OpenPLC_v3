#!/usr/bin/env python3
"""Legacy Python reference runtime for Protocol DSL (v0.1).

NOTE: production free-port runtime has been moved to C++ in
`webserver/core/protocol_dsl_runtime.h/.cpp`.

This module remains as a development/reference fallback for local testing of the DSL introduced in
`documentation/Protocol-DSL`:
- load/validate session JSON
- build TX frame from template + bindings + PLC image
- parse RX frame to PLC image
- produce realtime alarm flags for comm/checksum errors
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from webserver.protocol_dsl_transport import build_transport, TransportError


class DSLRuntimeError(Exception):
    pass


TOKEN_FIELD_RE = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_\[\]\.]*):(.*)\}$")
TOKEN_CHECKSUM_RE = re.compile(r"^\{(CRC16_MODBUS|LRC_ASCII|XOR8|SUM8)\}$")


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return int(float(value))
    raise DSLRuntimeError(f"cannot convert {value!r} to int")


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def lrc_ascii(data: bytes) -> int:
    lrc = 0
    for b in data:
        lrc = (lrc + b) & 0xFF
    lrc = ((-lrc) & 0xFF)
    return lrc


def xor8(data: bytes) -> int:
    x = 0
    for b in data:
        x ^= b
    return x & 0xFF


def sum8(data: bytes) -> int:
    return sum(data) & 0xFF


@dataclass
class AlarmState:
    comm_disconnected: bool = False
    comm_error: bool = False
    checksum_error: bool = False
    last_error_text: str = ""


@dataclass
class SessionRuntime:
    config: Dict[str, Any]
    plc_image: Dict[str, Any] = field(default_factory=dict)
    values: Dict[str, Any] = field(default_factory=dict)
    alarm: AlarmState = field(default_factory=AlarmState)

    def _tokens(self, template: str) -> List[str]:
        return template.strip().split()

    def _resolve_binding_value(self, field: str, direction: str) -> Any:
        for b in self.config.get("bindings", []):
            if b.get("field") != field:
                continue
            if b.get("direction") == "const":
                return b.get("value")
            if direction == "tx" and b.get("direction") == "plc_to_proto":
                return self.plc_image.get(b.get("source"), 0)
            if direction == "rx" and b.get("direction") == "proto_to_plc":
                return self.values.get(field)
        return self.values.get(field, 0)

    def _store_rx_binding(self, field: str, value: Any) -> None:
        self.values[field] = value
        for b in self.config.get("bindings", []):
            if b.get("field") == field and b.get("direction") == "proto_to_plc":
                target = b.get("target")
                if target:
                    self.plc_image[target] = value

    def _store_rx_array_bindings(self, field: str, raw: bytes) -> None:
        for b in self.config.get("bindings", []):
            bf = str(b.get("field", ""))
            if not bf.startswith(f"{field}[") or not bf.endswith("]"):
                continue
            if b.get("direction") != "proto_to_plc":
                continue
            idx_text = bf[len(field) + 1 : -1]
            if not idx_text.isdigit():
                continue
            i = int(idx_text)
            cast = b.get("cast", "u8")
            if cast in ("u16be", "s16be"):
                start, step = i * 2, 2
                chunk = raw[start:start + step]
                if len(chunk) != step:
                    continue
                val = int.from_bytes(chunk, "big", signed=cast.startswith("s"))
            elif cast in ("u16le", "s16le"):
                start, step = i * 2, 2
                chunk = raw[start:start + step]
                if len(chunk) != step:
                    continue
                val = int.from_bytes(chunk, "little", signed=cast.startswith("s"))
            else:
                if i >= len(raw):
                    continue
                val = raw[i]
            self.values[bf] = val
            target = b.get("target")
            if target:
                self.plc_image[target] = val

    def _eval_expr(self, expr: str) -> int:
        safe = expr
        # Replace len(NAME)
        for name, value in self.values.items():
            if isinstance(value, (bytes, bytearray)):
                safe = safe.replace(f"len({name})", str(len(value)))
        # Replace simple names
        for name, value in self.values.items():
            if isinstance(value, (bytes, bytearray)):
                continue
            safe = re.sub(rf"\b{re.escape(name)}\b", str(_to_int(value)), safe)
        if not re.fullmatch(r"[0-9+\-*/() ]+", safe):
            raise DSLRuntimeError(f"unsafe expression: {expr}")
        return int(eval(safe, {"__builtins__": {}}, {}))

    def _encode_numeric(self, typ: str, value: Any) -> bytes:
        n = _to_int(value)
        table = {
            "u8": (1, False, "big"),
            "s8": (1, True, "big"),
            "u16be": (2, False, "big"),
            "u16le": (2, False, "little"),
            "s16be": (2, True, "big"),
            "s16le": (2, True, "little"),
            "u32be": (4, False, "big"),
            "u32le": (4, False, "little"),
            "s32be": (4, True, "big"),
            "s32le": (4, True, "little"),
        }
        if typ not in table:
            raise DSLRuntimeError(f"unsupported numeric type: {typ}")
        size, signed, order = table[typ]
        return int(n).to_bytes(size, byteorder=order, signed=signed)

    def _decode_numeric(self, typ: str, data: bytes) -> int:
        table = {
            "u8": (1, False, "big"),
            "s8": (1, True, "big"),
            "u16be": (2, False, "big"),
            "u16le": (2, False, "little"),
            "s16be": (2, True, "big"),
            "s16le": (2, True, "little"),
            "u32be": (4, False, "big"),
            "u32le": (4, False, "little"),
            "s32be": (4, True, "big"),
            "s32le": (4, True, "little"),
        }
        if typ not in table:
            raise DSLRuntimeError(f"unsupported numeric type: {typ}")
        size, signed, order = table[typ]
        if len(data) != size:
            raise DSLRuntimeError(f"size mismatch for {typ}: got {len(data)}, need {size}")
        return int.from_bytes(data, byteorder=order, signed=signed)

    def _encode_field(self, field: str, field_type: str) -> bytes:
        value = self._resolve_binding_value(field, "tx")
        self.values[field] = value
        # options may follow after comma
        field_type = field_type.split(",", 1)[0].strip()
        if field_type.startswith("bytes(") and field_type.endswith(")"):
            expr = field_type[6:-1]
            n = self._eval_expr(expr)
            if isinstance(value, (bytes, bytearray)):
                raw = bytes(value)
                if len(raw) != n:
                    raw = raw[:n].ljust(n, b"\x00")
                return raw
            return bytes([_to_int(value) & 0xFF] * n)
        if field_type.startswith("string(") and field_type.endswith(")"):
            n = _to_int(field_type[7:-1])
            return str(value).encode("ascii", "ignore")[:n].ljust(n, b" ")
        return self._encode_numeric(field_type, value)

    def _decode_field(self, field_type: str, data: bytes) -> Any:
        field_type = field_type.split(",", 1)[0].strip()
        if field_type.startswith("bytes("):
            return data
        if field_type.startswith("string("):
            return data.decode("ascii", "ignore").rstrip()
        return self._decode_numeric(field_type, data)

    def build_tx(self) -> bytes:
        tokens = self._tokens(self.config["tx"]["template"])
        out = bytearray()
        checksum_kind = None
        for t in tokens:
            if t in {"CR", "LF", "CRLF"}:
                out.extend({"CR": b"\r", "LF": b"\n", "CRLF": b"\r\n"}[t])
                continue
            if TOKEN_CHECKSUM_RE.match(t):
                checksum_kind = TOKEN_CHECKSUM_RE.match(t).group(1)
                continue
            m = TOKEN_FIELD_RE.match(t)
            if m:
                out.extend(self._encode_field(m.group(1), m.group(2)))
                continue
            if t.startswith('"') and t.endswith('"'):
                out.extend(t[1:-1].encode("ascii"))
                continue
            if re.fullmatch(r"(?:0x)?[0-9A-Fa-f]{2}", t):
                out.append(int(t, 16))
                continue
            if t in {",", ";", "|"}:
                out.extend(t.encode("ascii"))
                continue
            raise DSLRuntimeError(f"unsupported token in TX: {t}")

        if checksum_kind:
            body = bytes(out)
            if checksum_kind == "CRC16_MODBUS":
                crc = crc16_modbus(body)
                out.extend(crc.to_bytes(2, "little"))
            elif checksum_kind == "LRC_ASCII":
                out.extend(f"{lrc_ascii(body):02X}".encode("ascii"))
            elif checksum_kind == "XOR8":
                out.extend(f"{xor8(body):02X}".encode("ascii"))
            elif checksum_kind == "SUM8":
                out.extend(f"{sum8(body):02X}".encode("ascii"))

        return bytes(out)

    def parse_rx(self, payload: bytes) -> Dict[str, Any]:
        self.alarm.comm_error = False
        self.alarm.last_error_text = ""

        tokens = self._tokens(self.config["rx"]["template"])
        idx = 0
        parsed: Dict[str, Any] = {}
        checksum_kind = None
        checksum_pos = None

        try:
            for t in tokens:
                if TOKEN_CHECKSUM_RE.match(t):
                    checksum_kind = TOKEN_CHECKSUM_RE.match(t).group(1)
                    checksum_pos = idx
                    break
                if t in {"CR", "LF", "CRLF"}:
                    lit = {"CR": b"\r", "LF": b"\n", "CRLF": b"\r\n"}[t]
                    if payload[idx:idx + len(lit)] != lit:
                        raise DSLRuntimeError("terminator mismatch")
                    idx += len(lit)
                    continue
                m = TOKEN_FIELD_RE.match(t)
                if m:
                    field, ftype = m.group(1), m.group(2).split(",", 1)[0].strip()
                    if ftype.startswith("bytes(") and ftype.endswith(")"):
                        n = self._eval_expr(ftype[6:-1])
                        raw = payload[idx:idx + n]
                        if len(raw) != n:
                            raise DSLRuntimeError(f"short payload on field {field}")
                        idx += n
                        val = self._decode_field(ftype, raw)
                        self._store_rx_array_bindings(field, raw)
                    elif ftype.startswith("string(") and ftype.endswith(")"):
                        n = _to_int(ftype[7:-1])
                        raw = payload[idx:idx + n]
                        if len(raw) != n:
                            raise DSLRuntimeError(f"short payload on field {field}")
                        idx += n
                        val = self._decode_field(ftype, raw)
                        self._store_rx_array_bindings(field, raw)
                    else:
                        size = {"u8": 1, "s8": 1, "u16be": 2, "u16le": 2, "s16be": 2, "s16le": 2,
                                "u32be": 4, "u32le": 4, "s32be": 4, "s32le": 4}[ftype]
                        raw = payload[idx:idx + size]
                        if len(raw) != size:
                            raise DSLRuntimeError(f"short payload on field {field}")
                        idx += size
                        val = self._decode_field(ftype, raw)
                        self._store_rx_array_bindings(field, raw)
                    parsed[field] = val
                    self.values[field] = val
                    self._store_rx_binding(field, val)
                    continue

                if t.startswith('"') and t.endswith('"'):
                    lit = t[1:-1].encode("ascii")
                    if payload[idx:idx + len(lit)] != lit:
                        raise DSLRuntimeError(f"literal mismatch: {t}")
                    idx += len(lit)
                    continue
                if re.fullmatch(r"(?:0x)?[0-9A-Fa-f]{2}", t):
                    b = int(t, 16)
                    if idx >= len(payload) or payload[idx] != b:
                        raise DSLRuntimeError(f"byte mismatch: {t}")
                    idx += 1
                    continue
                if t in {",", ";", "|"}:
                    if idx >= len(payload) or payload[idx:idx + 1] != t.encode("ascii"):
                        raise DSLRuntimeError(f"delimiter mismatch: {t}")
                    idx += 1
                    continue

                raise DSLRuntimeError(f"unsupported token in RX: {t}")

            if checksum_kind:
                if checksum_kind == "CRC16_MODBUS":
                    if len(payload) < idx + 2:
                        raise DSLRuntimeError("missing CRC bytes")
                    got = int.from_bytes(payload[idx:idx + 2], "little")
                    want = crc16_modbus(payload[:idx])
                    if got != want:
                        self.alarm.checksum_error = True
                        self.alarm.comm_error = True
                        self.alarm.last_error_text = f"CRC mismatch got=0x{got:04X} want=0x{want:04X}"
                        raise DSLRuntimeError(self.alarm.last_error_text)
                    self.alarm.checksum_error = False
                    idx += 2

            return parsed
        except DSLRuntimeError as exc:
            self.alarm.comm_error = True
            if not self.alarm.last_error_text:
                self.alarm.last_error_text = str(exc)
            raise


    def run_cycle(self, max_rx_bytes: int = 4096) -> Dict[str, Any]:
        timeout_ms = int(self.config.get("match", {}).get("timeout_ms", 500))
        transport = build_transport(self.config.get("transport", {}), timeout_ms=timeout_ms)
        tx = self.build_tx()

        try:
            transport.open()
            sent = transport.send(tx)
            rx = transport.receive(max_rx_bytes)
            if not rx:
                self.alarm.comm_error = True
                self.alarm.last_error_text = "receive timeout"
                raise DSLRuntimeError("receive timeout")
            parsed = self.parse_rx(rx)
            return {
                "tx": tx,
                "tx_len": sent,
                "rx": rx,
                "parsed": parsed,
                "alarm": self.alarm,
            }
        except (TransportError, OSError) as exc:
            self.alarm.comm_disconnected = True
            self.alarm.comm_error = True
            self.alarm.last_error_text = str(exc)
            raise DSLRuntimeError(str(exc)) from exc
        finally:
            try:
                transport.close()
            except Exception:
                pass

def load_session(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def validate_session_schema(session: Dict[str, Any], schema_path: str | Path) -> Tuple[bool, str]:
    # Optional dependency use if available; fallback to basic required-field checks.
    try:
        import jsonschema  # type: ignore

        with open(schema_path, "r", encoding="utf-8") as fp:
            schema = json.load(fp)
        jsonschema.validate(instance=session, schema=schema)
        return True, "ok(jsonschema)"
    except ModuleNotFoundError:
        required = ["version", "session_name", "protocol_kind", "transport", "tx", "rx", "bindings"]
        missing = [k for k in required if k not in session]
        if missing:
            return False, f"missing fields: {missing}"
        if "template" not in session.get("tx", {}) or "template" not in session.get("rx", {}):
            return False, "missing tx.template or rx.template"
        return True, "ok(basic-validation)"


def create_runtime(session_path: str | Path, schema_path: str | Path, plc_image: Optional[Dict[str, Any]] = None) -> SessionRuntime:
    session = load_session(session_path)
    ok, msg = validate_session_schema(session, schema_path)
    if not ok:
        raise DSLRuntimeError(f"schema validation failed: {msg}")
    return SessionRuntime(config=session, plc_image=plc_image or {})
