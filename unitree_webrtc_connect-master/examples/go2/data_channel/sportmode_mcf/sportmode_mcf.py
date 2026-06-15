"""MCF sport example — every API method testable via an interactive menu.

No motion_switcher handshake: assumes the robot is already in MCF mode.
Requires Unitree firmware >= 1.1.7 (MCF was introduced in 1.1.7 and used
since).
Topic is `rt/api/sport/request` (same wire path as normal mode); MCF differs
only in the set of api_id values, hardcoded below.
"""

import asyncio
import json
import logging
import os
import random
import sys
import time

from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD_MCF

logging.basicConfig(level=logging.FATAL)

ROBOT_IP = os.environ.get("UNITREE_ROBOT_IP", "192.168.8.181")

# Menu rows: (key, "<api_id>  <description>")
MENU = [
    ("Damp",             "1001  Disable motors"),
    ("BalanceStand",     "1002  Balance stand"),
    ("StopMove",         "1003  Stop all movement"),
    ("StandUp",          "1004  Stand up"),
    ("StandDown",        "1005  Stand down"),
    ("RecoveryStand",    "1006  Recovery stand after fall"),
    ("Euler",            "1007  Set body euler (roll, pitch, yaw)"),
    ("MoveForward",      "1008  Move forward  (vx)"),
    ("MoveSideways",     "1008  Move sideways (vy)"),
    ("MoveRotate",       "1008  Move rotate   (vyaw)"),
    ("Sit",              "1009  Sit down"),
    ("RiseSit",          "1010  Rise from sit"),
    ("SpeedLevel",       "1015  Set speed level (int)"),
    ("Hello",            "1016  Hello gesture"),
    ("Stretch",          "1017  Stretch"),
    ("ContinuousGait",   "1019  Continuous gait (int flag)"),
    ("Content",          "1020  Content gesture"),
    ("Dance1",           "1022  Dance 1"),
    ("Dance2",           "1023  Dance 2"),
    ("GetSpeedLevel",    "1026  Query speed level"),
    ("SwitchJoystick",   "1027  Switch joystick (on/off)"),
    ("Pose",             "1028  Enter Pose (exit via StopMove)"),
    ("Scrape",           "1029  Scrape"),
    ("FrontFlip",        "1030  Front flip"),
    ("FrontJump",        "1031  Front jump"),
    ("FrontPounce",      "1032  Front pounce"),
    ("GetState",         "1034  Query robot state"),
    ("Heart",            "1036  Heart gesture"),
    ("StaticWalk",       "1061  Static walk (on/off)"),
    ("TrotRun",          "1062  Trot run (on/off)"),
    ("EconomicGait",     "1063  Economic gait (on/off)"),
    ("HandStand",        "2044  Hand stand (on/off)"),
    ("LeftFlip",         "2041  Left flip"),
    ("BackFlip",         "2043  Back flip"),
    ("FreeWalk",         "2045  Free walk (on/off)"),
    ("FreeBound",        "2046  Free bound (on/off)"),
    ("FreeJump",         "2047  Free jump (on/off)"),
    ("FreeAvoid",        "2048  Free avoid (on/off)"),
    ("ClassicWalk",      "2049  Classic walk (on/off)"),
    ("BackStand",        "2050  Back stand (on/off)"),
    ("CrossStep",        "2051  Cross step (on/off)"),
    ("SetAutoRecovery",  "2054  Set auto recovery (on/off)"),
    ("GetAutoRecovery",  "2055  Query auto recovery"),
    ("LeadFollow",       "2056  Lead follow (on/off)"),
    ("SwitchAvoidMode",  "2058  Switch avoid mode (on/off)"),
]


async def ask_bool(prompt="on/off [on]: "):
    raw = await asyncio.to_thread(input, f"  {prompt}")
    return raw.strip().lower() not in ("off", "0", "false", "no", "n")


async def ask_int(prompt="value", default=1):
    raw = await asyncio.to_thread(input, f"  {prompt} [{default}]: ")
    try:
        return int(raw)
    except ValueError:
        return default


async def ask_float(prompt="value", default=0.0):
    raw = await asyncio.to_thread(input, f"  {prompt} [{default}]: ")
    try:
        return float(raw)
    except ValueError:
        return default


async def call(conn, api_id, parameter=None):
    """Request/response sport call. Returns (code, raw_data)."""
    payload = {"api_id": api_id}
    if parameter is not None:
        payload["parameter"] = parameter
    response = await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC["SPORT_MOD"], payload
    )
    code = response.get("data", {}).get("header", {}).get("status", {}).get("code", -1)
    data = response.get("data", {}).get("data", "")
    return code, data


def call_no_reply(conn, api_id, parameter=None):
    """Fire-and-forget sport call (Move uses this — no response is awaited).

    Wire shape matches unitree_webrtc_sdk's `_CallNoReplyBase`:
      header.policy.noreply = True, msg_type defaults to "msg".
    """
    generated_id = int(time.time() * 1000) % 2147483648 + random.randint(0, 1000)
    request_payload = {
        "header": {
            "identity": {"id": generated_id, "api_id": api_id},
            "policy": {"priority": 0, "noreply": True},
        },
        "parameter": json.dumps(parameter) if parameter is not None else "",
        "binary": [],
    }
    conn.datachannel.pub_sub.publish_without_callback(
        RTC_TOPIC["SPORT_MOD"], request_payload
    )


async def dispatch(conn, name):
    if name == "Damp":
        return await call(conn, SPORT_CMD_MCF["Damp"])
    if name == "BalanceStand":
        return await call(conn, SPORT_CMD_MCF["BalanceStand"])
    if name == "StopMove":
        return await call(conn, SPORT_CMD_MCF["StopMove"])
    if name == "StandUp":
        return await call(conn, SPORT_CMD_MCF["StandUp"])
    if name == "StandDown":
        return await call(conn, SPORT_CMD_MCF["StandDown"])
    if name == "RecoveryStand":
        return await call(conn, SPORT_CMD_MCF["RecoveryStand"])
    if name == "Euler":
        roll = await ask_float("roll", 0.1)
        pitch = await ask_float("pitch", 0.2)
        yaw = await ask_float("yaw", 0.3)
        return await call(conn, SPORT_CMD_MCF["Euler"], {"x": roll, "y": pitch, "z": yaw})
    if name == "MoveForward":
        vx = await ask_float("vx", 0.3)
        call_no_reply(conn, SPORT_CMD_MCF["Move"], {"x": vx, "y": 0, "z": 0})
        return None
    if name == "MoveSideways":
        vy = await ask_float("vy", 0.3)
        call_no_reply(conn, SPORT_CMD_MCF["Move"], {"x": 0, "y": vy, "z": 0})
        return None
    if name == "MoveRotate":
        vyaw = await ask_float("vyaw", 0.5)
        call_no_reply(conn, SPORT_CMD_MCF["Move"], {"x": 0, "y": 0, "z": vyaw})
        return None
    if name == "Sit":
        return await call(conn, SPORT_CMD_MCF["Sit"])
    if name == "RiseSit":
        return await call(conn, SPORT_CMD_MCF["RiseSit"])
    if name == "SpeedLevel":
        level = await ask_int("level", 1)
        return await call(conn, SPORT_CMD_MCF["SpeedLevel"], {"data": level})
    if name == "Hello":
        return await call(conn, SPORT_CMD_MCF["Hello"])
    if name == "Stretch":
        return await call(conn, SPORT_CMD_MCF["Stretch"])
    if name == "ContinuousGait":
        flag = await ask_int("flag", 1)
        return await call(conn, SPORT_CMD_MCF["ContinuousGait"], {"data": flag})
    if name == "Content":
        return await call(conn, SPORT_CMD_MCF["Content"])
    if name == "Dance1":
        return await call(conn, SPORT_CMD_MCF["Dance1"])
    if name == "Dance2":
        return await call(conn, SPORT_CMD_MCF["Dance2"])
    if name == "GetSpeedLevel":
        code, data = await call(conn, SPORT_CMD_MCF["GetSpeedLevel"])
        if code == 0 and data:
            try:
                print(f"  SpeedLevel: {json.loads(data).get('data')}")
            except Exception:
                print(f"  raw: {data}")
        return code, data
    if name == "SwitchJoystick":
        return await call(conn, SPORT_CMD_MCF["SwitchJoystick"], {"data": await ask_bool()})
    if name == "Pose":
        return await call(conn, SPORT_CMD_MCF["Pose"], {"data": True})
    if name == "Scrape":
        return await call(conn, SPORT_CMD_MCF["Scrape"])
    if name == "FrontFlip":
        return await call(conn, SPORT_CMD_MCF["FrontFlip"], {"data": True})
    if name == "FrontJump":
        return await call(conn, SPORT_CMD_MCF["FrontJump"])
    if name == "FrontPounce":
        return await call(conn, SPORT_CMD_MCF["FrontPounce"])
    if name == "GetState":
        keys = ["state", "bodyHeight", "speedLevel", "gait",
                "continuousGait", "economicGait"]
        code, data = await call(conn, SPORT_CMD_MCF["GetState"], keys)
        if code != 0:
            print(f"  GetState failed: code={code}")
        elif not data:
            print(f"  GetState ok but data field is empty: {data!r}")
        else:
            try:
                parsed = json.loads(data)
                print("  State:")
                for k, v in parsed.items():
                    print(f"    {k}: {v}")
            except Exception as e:
                print(f"  raw (parse failed: {e}): {data}")
        return code, data
    if name == "Heart":
        return await call(conn, SPORT_CMD_MCF["Heart"])
    if name == "StaticWalk":
        return await call(conn, SPORT_CMD_MCF["StaticWalk"], {"data": await ask_bool()})
    if name == "TrotRun":
        return await call(conn, SPORT_CMD_MCF["TrotRun"], {"data": await ask_bool()})
    if name == "EconomicGait":
        return await call(conn, SPORT_CMD_MCF["EconomicGait"], {"data": await ask_bool()})
    if name == "HandStand":
        return await call(conn, SPORT_CMD_MCF["HandStand"], {"data": await ask_bool()})
    if name == "LeftFlip":
        return await call(conn, SPORT_CMD_MCF["LeftFlip"], {"data": True})
    if name == "BackFlip":
        return await call(conn, SPORT_CMD_MCF["BackFlip"], {"data": True})
    if name == "FreeWalk":
        return await call(conn, SPORT_CMD_MCF["FreeWalk"], {"data": await ask_bool()})
    if name == "FreeBound":
        return await call(conn, SPORT_CMD_MCF["FreeBound"], {"data": await ask_bool()})
    if name == "FreeJump":
        return await call(conn, SPORT_CMD_MCF["FreeJump"], {"data": await ask_bool()})
    if name == "FreeAvoid":
        return await call(conn, SPORT_CMD_MCF["FreeAvoid"], {"data": await ask_bool()})
    if name == "ClassicWalk":
        return await call(conn, SPORT_CMD_MCF["ClassicWalk"], {"data": await ask_bool()})
    if name == "BackStand":
        return await call(conn, SPORT_CMD_MCF["BackStand"], {"data": await ask_bool()})
    if name == "CrossStep":
        return await call(conn, SPORT_CMD_MCF["CrossStep"], {"data": await ask_bool()})
    if name == "SetAutoRecovery":
        return await call(conn, SPORT_CMD_MCF["SetAutoRecovery"], {"data": await ask_bool()})
    if name == "GetAutoRecovery":
        code, data = await call(conn, SPORT_CMD_MCF["GetAutoRecovery"])
        if code == 0 and data:
            try:
                print(f"  AutoRecovery: {json.loads(data).get('data')}")
            except Exception:
                print(f"  raw: {data}")
        return code, data
    if name == "LeadFollow":
        return await call(conn, SPORT_CMD_MCF["LeadFollow"], {"data": await ask_bool()})
    if name == "SwitchAvoidMode":
        return await call(conn, SPORT_CMD_MCF["SwitchAvoidMode"], {"data": await ask_bool()})
    return -1, None


async def main():
    print("WARNING: Ensure there are no obstacles around the robot.")
    print("This example assumes the robot is already in MCF mode (no motion_switcher).")
    print("Requires Unitree firmware >= 1.1.7 (MCF introduced in 1.1.7 and used since).")
    await asyncio.to_thread(input, "Press Enter to continue...")

    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ROBOT_IP)
    await conn.connect()

    print("\nAvailable commands:")
    for i, (name, desc) in enumerate(MENU):
        print(f"  {i:2d}: {name:20s}  {desc}")
    print("   q: Quit")

    while True:
        raw = await asyncio.to_thread(input, "\nCommand #: ")
        raw = raw.strip()
        if raw.lower() == "q":
            break
        try:
            idx = int(raw)
        except ValueError:
            print("Invalid input")
            continue
        if not (0 <= idx < len(MENU)):
            print("Unknown command")
            continue

        name = MENU[idx][0]
        try:
            result = await dispatch(conn, name)
        except Exception as e:
            print(f"  -> {name} failed: {e}")
            continue
        if result is None:
            print(f"  -> {name} sent (no reply)")
            code = None
        else:
            code, _ = result
            print(f"  -> {name} returned code={code}")
        if name == "StandUp" and code == 0:
            print("  HINT: joints may be locked after StandUp — "
                  "run BalanceStand (1002) before any Move/gesture command.")
        if name == "Pose" and code == 0:
            print("  HINT: run StopMove (1003) to exit Pose mode.")
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting")
        sys.exit(0)
