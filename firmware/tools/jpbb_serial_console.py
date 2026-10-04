#!/usr/bin/env python3
"""Small macOS/Linux USB CDC console for JPBB firmware.

Uses only the Python standard library.  Input is line based; Ctrl-C exits.
"""

from __future__ import annotations

import argparse
import glob
import os
import select
import sys
import termios
import time


DEFAULT_GLOBS = ("/dev/cu.usbmodem*", "/dev/ttyACM*")
BAUD = termios.B115200


def find_port(explicit: str | None) -> str:
    if explicit:
        return explicit

    ports = sorted(
        {
            port
            for pattern in DEFAULT_GLOBS
            for port in glob.glob(pattern)
        }
    )
    if not ports:
        raise SystemExit(
            "USB CDCポートが見つかりません。J6接続とStep 2以降の起動を確認してください。"
        )
    if len(ports) > 1:
        choices = "\n".join(f"  {port}" for port in ports)
        raise SystemExit(
            "複数のUSB CDCポートがあります。--portで1つ指定してください:\n"
            f"{choices}"
        )
    return ports[0]


def configure_port(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = BAUD
    attrs[5] = BAUD
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def write_line(fd: int, line: str) -> None:
    os.write(fd, (line.rstrip("\r\n") + "\r\n").encode("ascii"))


def run_console(
    port: str,
    heartbeat: bool,
    interval: float,
    repeat_set: bool,
    command_interval: float,
) -> None:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_port(fd)
        print(f"接続: {port}（終了は Ctrl-C）")
        if heartbeat:
            print(f"HEARTBEATを{interval:.2f}秒間隔で自動送信します。")
        if repeat_set:
            print(
                "入力したSET値をSTREAMとして"
                f"{command_interval:.2f}秒間隔で再送します。"
            )
        print("> ", end="", flush=True)

        next_heartbeat = time.monotonic()
        next_command = time.monotonic()
        last_set: tuple[int, int] | None = None
        while True:
            now = time.monotonic()
            if heartbeat and now >= next_heartbeat:
                write_line(fd, "HEARTBEAT")
                next_heartbeat = now + interval
            if repeat_set and last_set is not None and now >= next_command:
                write_line(fd, f"STREAM {last_set[0]} {last_set[1]}")
                next_command = now + command_interval

            timeout = 0.1
            if heartbeat:
                timeout = max(0.0, min(timeout, next_heartbeat - now))
            if repeat_set and last_set is not None:
                timeout = max(0.0, min(timeout, next_command - now))

            readable, _, _ = select.select([fd, sys.stdin], [], [], timeout)
            if fd in readable:
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    data = b""
                if data:
                    text = data.decode("utf-8", errors="replace")
                    print(f"\r{text}", end="")
                    if text.endswith(("\n", "\r")):
                        print("> ", end="", flush=True)

            if sys.stdin in readable:
                line = sys.stdin.readline()
                if line == "":
                    return
                if line.strip():
                    write_line(fd, line)
                    fields = line.strip().upper().split()
                    if len(fields) == 3 and fields[0] == "SET":
                        try:
                            servo_us = int(fields[1])
                            esc_us = int(fields[2])
                        except ValueError:
                            pass
                        else:
                            if 1000 <= servo_us <= 2000 and 1000 <= esc_us <= 2000:
                                last_set = (servo_us, esc_us)
                                next_command = time.monotonic() + command_interval
                print("> ", end="", flush=True)
    finally:
        os.close(fd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="JPBB USB CDCコンソール（外部Pythonパッケージ不要）"
    )
    parser.add_argument("--port", help="例: /dev/cu.usbmodem1101")
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        help="Step 6/7/8用にHEARTBEATを自動送信する",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.25,
        help="HEARTBEAT間隔（秒、既定0.25）",
    )
    parser.add_argument(
        "--repeat-set",
        action="store_true",
        help="最後に入力したSET値をStep 7/8へ継続送信する",
    )
    parser.add_argument(
        "--command-interval",
        type=float,
        default=0.10,
        help="SET値のSTREAM再送間隔（秒、既定0.10）",
    )
    args = parser.parse_args()
    if not 0.05 <= args.interval < 0.5:
        parser.error("--intervalは0.05以上0.5未満にしてください")
    if not 0.02 <= args.command_interval < 0.2:
        parser.error("--command-intervalは0.02以上0.2未満にしてください")
    return args


def main() -> int:
    args = parse_args()
    port = find_port(args.port)
    try:
        run_console(
            port,
            args.heartbeat,
            args.interval,
            args.repeat_set,
            args.command_interval,
        )
    except KeyboardInterrupt:
        print("\n終了しました。")
    except OSError as exc:
        print(f"\nポートを開けません: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
