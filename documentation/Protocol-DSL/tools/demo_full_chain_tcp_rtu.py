#!/usr/bin/env python3
"""End-to-end free-port demo for both TCP and RTU(serial).

Demonstrates: DSL -> runtime build_tx -> transport send/recv -> parse_rx -> PLC map.
"""

from __future__ import annotations

import json
import os
import pty
import socket
import tempfile
import threading
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from webserver.protocol_dsl_runtime import create_runtime, crc16_modbus


def make_response(addr: int = 1) -> bytes:
    body = bytes.fromhex(f"68 {addr:02x} 91 01 2c 00 fa")
    return body + crc16_modbus(body).to_bytes(2, "little")


def run_tcp_slave(port: int, stop_evt: threading.Event) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    srv.settimeout(0.2)
    try:
        while not stop_evt.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                req = conn.recv(256)
                if req:
                    conn.sendall(make_response(1))
    finally:
        srv.close()


def run_rtu_slave(master_fd: int, stop_evt: threading.Event) -> None:
    while not stop_evt.is_set():
        try:
            req = os.read(master_fd, 256)
        except BlockingIOError:
            continue
        except OSError:
            break
        if req:
            try:
                os.write(master_fd, make_response(1))
            except OSError:
                break


def build_runtime_with_transport(transport_cfg: dict):
    schema = REPO / "documentation/Protocol-DSL/protocol-dsl-v0.1.schema.json"
    src = REPO / "documentation/Protocol-DSL/examples/example-binary-meter-read.json"
    session = json.loads(src.read_text(encoding="utf-8"))
    session["transport"] = transport_cfg

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(session, f)
        temp_path = Path(f.name)

    try:
        return create_runtime(temp_path, schema, plc_image={"%QW100": 1})
    finally:
        temp_path.unlink(missing_ok=True)


def demo_tcp() -> None:
    stop_evt = threading.Event()
    port = 15021
    th = threading.Thread(target=run_tcp_slave, args=(port, stop_evt), daemon=True)
    th.start()

    rt = build_runtime_with_transport({"type": "tcp_client", "tcp": {"host": "127.0.0.1", "port": port}})
    out = rt.run_cycle()
    stop_evt.set()
    print("[TCP] TX", out["tx"].hex())
    print("[TCP] RX", out["rx"].hex())
    print("[TCP] PLC", rt.plc_image)
    print("[TCP] Alarm", rt.alarm)


def demo_rtu() -> None:
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    stop_evt = threading.Event()
    th = threading.Thread(target=run_rtu_slave, args=(master_fd, stop_evt), daemon=True)
    th.start()

    rt = build_runtime_with_transport(
        {
            "type": "serial",
            "serial": {
                "port": slave_path,
                "baud": 9600,
                "parity": "N",
                "data_bits": 8,
                "stop_bits": 1,
            },
        }
    )
    out = rt.run_cycle()
    stop_evt.set()
    os.close(master_fd)
    os.close(slave_fd)

    print("[RTU] TX", out["tx"].hex())
    print("[RTU] RX", out["rx"].hex())
    print("[RTU] PLC", rt.plc_image)
    print("[RTU] Alarm", rt.alarm)


if __name__ == "__main__":
    demo_tcp()
    demo_rtu()
