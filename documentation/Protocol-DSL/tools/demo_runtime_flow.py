#!/usr/bin/env python3
"""Demonstration for end-to-end Protocol DSL runtime flow.

Flow:
1) Load & validate DSL session JSON using schema.
2) Build TX frame from PLC image + bindings.
3) Simulate slave RX frame (good and bad CRC).
4) Parse RX frame and write back PLC values.
5) Print alarm state for operational visibility.
"""

from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from webserver.protocol_dsl_runtime import create_runtime, crc16_modbus, DSLRuntimeError


def main() -> None:
    repo = REPO
    schema = repo / "documentation/Protocol-DSL/protocol-dsl-v0.1.schema.json"
    session = repo / "documentation/Protocol-DSL/examples/example-binary-meter-read.json"

    plc_image = {
        "%QW100": 1,  # device address
    }

    runtime = create_runtime(session, schema, plc_image=plc_image)

    tx = runtime.build_tx()
    print("[TX frame]", tx.hex())

    # Simulate one successful response:
    # 68 [ADDR=01] 91 [DATA=0x012c 0x00fa] [CRC16]
    rx_body = bytes.fromhex("68 01 91 01 2c 00 fa")
    rx_crc = crc16_modbus(rx_body).to_bytes(2, "little")
    rx_ok = rx_body + rx_crc

    parsed = runtime.parse_rx(rx_ok)
    print("[RX parsed]", parsed)
    print("[PLC image]", runtime.plc_image)
    print("[Alarm state after OK]", runtime.alarm)

    # Simulate checksum error
    rx_bad = rx_body + b"\x00\x00"
    try:
        runtime.parse_rx(rx_bad)
    except DSLRuntimeError as exc:
        print("[RX bad] parse error:", exc)
    print("[Alarm state after bad CRC]", runtime.alarm)


if __name__ == "__main__":
    main()
