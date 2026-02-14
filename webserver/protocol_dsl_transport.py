#!/usr/bin/env python3
"""Transport layer for Protocol DSL runtime (TCP + RTU serial)."""

from __future__ import annotations

import os
import select
import socket
import termios
from dataclasses import dataclass
from typing import Dict, Any


class TransportError(Exception):
    pass


@dataclass
class TransportClient:
    timeout_ms: int = 500

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def send(self, data: bytes) -> int:
        raise NotImplementedError

    def receive(self, max_bytes: int = 4096) -> bytes:
        raise NotImplementedError


@dataclass
class TcpClient(TransportClient):
    host: str = "127.0.0.1"
    port: int = 502
    sock: socket.socket | None = None

    def open(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout_ms / 1000.0)
        self.sock.connect((self.host, self.port))

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def send(self, data: bytes) -> int:
        if self.sock is None:
            raise TransportError("tcp socket not opened")
        return self.sock.send(data)

    def receive(self, max_bytes: int = 4096) -> bytes:
        if self.sock is None:
            raise TransportError("tcp socket not opened")
        return self.sock.recv(max_bytes)


@dataclass
class SerialClient(TransportClient):
    port: str = "/dev/ttyUSB0"
    baud: int = 9600
    parity: str = "N"
    data_bits: int = 8
    stop_bits: int = 1
    fd: int = -1

    def _baud_const(self) -> int:
        table = {
            1200: termios.B1200,
            2400: termios.B2400,
            4800: termios.B4800,
            9600: termios.B9600,
            19200: termios.B19200,
            38400: termios.B38400,
            57600: termios.B57600,
            115200: termios.B115200,
        }
        if self.baud not in table:
            raise TransportError(f"unsupported baud rate: {self.baud}")
        return table[self.baud]

    def open(self) -> None:
        self.fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)

        # iflag, oflag, cflag, lflag
        attrs[0] = 0
        attrs[1] = 0
        attrs[3] = 0

        cflag = termios.CREAD | termios.CLOCAL
        cflag |= self._baud_const()

        # data bits
        cflag &= ~termios.CSIZE
        if self.data_bits == 7:
            cflag |= termios.CS7
        else:
            cflag |= termios.CS8

        # parity
        if self.parity == "E":
            cflag |= termios.PARENB
            cflag &= ~termios.PARODD
        elif self.parity == "O":
            cflag |= termios.PARENB
            cflag |= termios.PARODD
        else:
            cflag &= ~termios.PARENB

        # stop bits
        if self.stop_bits == 2:
            cflag |= termios.CSTOPB
        else:
            cflag &= ~termios.CSTOPB

        attrs[2] = cflag
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def send(self, data: bytes) -> int:
        if self.fd < 0:
            raise TransportError("serial port not opened")
        return os.write(self.fd, data)

    def receive(self, max_bytes: int = 4096) -> bytes:
        if self.fd < 0:
            raise TransportError("serial port not opened")
        timeout_s = self.timeout_ms / 1000.0
        r, _, _ = select.select([self.fd], [], [], timeout_s)
        if not r:
            return b""
        return os.read(self.fd, max_bytes)


def build_transport(transport_cfg: Dict[str, Any], timeout_ms: int) -> TransportClient:
    tp = transport_cfg.get("type")
    if tp == "tcp_client":
        tcp = transport_cfg.get("tcp", {})
        return TcpClient(timeout_ms=timeout_ms, host=tcp.get("host", "127.0.0.1"), port=int(tcp.get("port", 502)))
    if tp == "serial":
        ser = transport_cfg.get("serial", {})
        return SerialClient(
            timeout_ms=timeout_ms,
            port=ser.get("port", "/dev/ttyUSB0"),
            baud=int(ser.get("baud", 9600)),
            parity=ser.get("parity", "N"),
            data_bits=int(ser.get("data_bits", 8)),
            stop_bits=int(ser.get("stop_bits", 1)),
        )
    raise TransportError(f"unsupported transport type: {tp}")
