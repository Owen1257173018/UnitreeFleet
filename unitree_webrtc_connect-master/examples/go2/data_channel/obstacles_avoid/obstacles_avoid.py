"""Obstacle-avoidance example — toggle on/off, query state, and drive with WASD.

Movement uses `rt/wirelesscontroller` (simulated joystick); when avoidance is
on, the obstacle-avoid service intercepts these and applies safety filtering.

All toggle/query requests go to RTC_TOPIC["OBSTACLES_AVOID"]
(= rt/api/obstacles_avoid/request); api_ids in OBSTACLES_AVOID_API.
"""

import asyncio
import json
import logging
import os
import sys
import termios
import tty

from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, OBSTACLES_AVOID_API

logging.basicConfig(level=logging.FATAL)

ROBOT_IP = os.environ.get("UNITREE_ROBOT_IP", "192.168.8.181")

MOVE_DURATION = 0.5    # seconds to send commands per keypress
MOVE_INTERVAL = 0.02   # 50 Hz publish rate

#                   label          (lx,    ly,   rx)
KEY_MAP = {
    "w":      ("forward",       ( 0.0,  0.9,  0.0)),
    "\x1b[A": ("forward",       ( 0.0,  0.9,  0.0)),
    "s":      ("backward",      ( 0.0, -0.9,  0.0)),
    "\x1b[B": ("backward",      ( 0.0, -0.9,  0.0)),
    "a":      ("strafe left",   (-0.9,  0.0,  0.0)),
    "\x1b[D": ("strafe left",   (-0.9,  0.0,  0.0)),
    "d":      ("strafe right",  ( 0.9,  0.0,  0.0)),
    "\x1b[C": ("strafe right",  ( 0.9,  0.0,  0.0)),
    "j":      ("turn left",     ( 0.0,  0.0,  0.9)),
    "l":      ("turn right",    ( 0.0,  0.0, -0.9)),
    " ":      ("stop",          None),
}


def get_key():
    """Read a single keypress (blocking). Returns the key character(s)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            ch3 = sys.stdin.read(1)
            return ch + ch2 + ch3
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def publish_wireless_controller(pub_sub, lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0):
    pub_sub.publish_without_callback(
        RTC_TOPIC["WIRELESS_CONTROLLER"],
        {"lx": lx, "ly": ly, "rx": rx, "ry": ry, "keys": keys},
    )


async def drive_loop(pub_sub):
    print("\n  Drive mode — use keys to move:")
    print("    W / Up    = forward       S / Down  = backward")
    print("    A / Left  = strafe left   D / Right = strafe right")
    print("    J = turn left             L = turn right")
    print("    Space = stop              Q / Esc = exit drive mode\n")

    while True:
        key = await asyncio.to_thread(get_key)

        if key in ("q", "\x1b"):
            publish_wireless_controller(pub_sub)
            print("\n  Exited drive mode.")
            break

        if key not in KEY_MAP:
            continue

        label, joystick = KEY_MAP[key]

        if joystick is None:
            publish_wireless_controller(pub_sub)
            print(f"\r  [{label}] stopped                          ", end="", flush=True)
            continue

        lx, ly, rx = joystick

        # Publish wireless controller at 50 Hz for MOVE_DURATION
        t = 0.0
        while t < MOVE_DURATION:
            publish_wireless_controller(pub_sub, lx=lx, ly=ly, rx=rx)
            await asyncio.sleep(MOVE_INTERVAL)
            t += MOVE_INTERVAL

        # Stop after burst
        publish_wireless_controller(pub_sub)

        print(f"\r  [{label}] lx={lx:.1f} ly={ly:.1f} rx={rx:.1f}              ", end="", flush=True)


async def switch_set(conn, enable: bool):
    response = await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC["OBSTACLES_AVOID"],
        {"api_id": OBSTACLES_AVOID_API["SWITCH_SET"], "parameter": {"enable": enable}},
    )
    return response.get("data", {}).get("header", {}).get("status", {}).get("code", -1)


async def switch_get(conn):
    """Returns (code, enabled) where enabled is True/False/None."""
    response = await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC["OBSTACLES_AVOID"],
        {"api_id": OBSTACLES_AVOID_API["SWITCH_GET"]},
    )
    code = response.get("data", {}).get("header", {}).get("status", {}).get("code", -1)
    data = response.get("data", {}).get("data", "")
    if code == 0 and data:
        try:
            return code, json.loads(data).get("enable")
        except Exception:
            return code, None
    return code, None


async def main():
    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ROBOT_IP)
    await conn.connect()

    print("\nObstacle avoidance — pick a command:")
    print("  1: Enable")
    print("  2: Disable")
    print("  3: Query current state")
    print("  4: Drive (WASD / arrows / j,l to turn — space=stop, q=exit)")
    print("  q: Quit")

    while True:
        raw = await asyncio.to_thread(input, "\nCommand: ")
        raw = raw.strip().lower()
        if raw == "q":
            break
        if raw == "1":
            code = await switch_set(conn, True)
            print(f"  Enabled  (code={code})")
        elif raw == "2":
            code = await switch_set(conn, False)
            print(f"  Disabled (code={code})")
        elif raw == "3":
            code, enabled = await switch_get(conn)
            state = "enabled" if enabled else ("disabled" if enabled is False else "?")
            print(f"  State: {state}  (code={code})")
        elif raw == "4":
            await drive_loop(conn.datachannel.pub_sub)
        else:
            print("Invalid input")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting")
        sys.exit(0)
