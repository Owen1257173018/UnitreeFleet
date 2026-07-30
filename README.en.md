# Unitree Fleet

[中文](README.md) · **English**

A PyQt6 desktop app for **controlling multiple Unitree robots simultaneously** (Go2 quadrupeds, G1 humanoids) via WebRTC data-channel. Supports LAN group control, timed choreographies, and live recording.

> 🐕🤖 One laptop, one UI, N robots.

![PyQt6](https://img.shields.io/badge/PyQt6-6.4+-blue) ![Python](https://img.shields.io/badge/Python-3.10+-green) ![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey) ![License](https://img.shields.io/badge/License-MIT-blue)

---

## ✨ Highlights

- **Multi-robot concurrency**: Mix any number of Go2 and G1 robots; commands dispatched concurrently via `asyncio.gather`.
- **New-firmware support**: Handles the `data2=3` encrypted handshake (Go2 ≥ 1.1.15 / G1 ≥ 1.5.1). Built-in Unitree cloud login to fetch the per-device AES-128 key in one click.
- **Three ways to add a robot**:
  - `+ Add by IP` — enter IP / SN / AES key (works for both Go2 and G1)
  - `📡 Scan LAN` — UDP multicast auto-discovery (**Go2 only**; use IP-Add for G1)
  - `📂 Load Preset` — restore a saved list of robots with one click
- **Preset save/load**: Snapshot the current robot list as a named preset for different show configurations.
- **Choreography**:
  - Multi-track timeline editor mapped to robots by list position
  - Go2 sport actions (dances, stunts) and G1 arm/mode actions have fixed durations to prevent drift
  - Append multiple choreographies in parallel
- **Live recording**: Capture live user operations (actions, movement, mode switches) and export as replayable `ChoreoScript`.
- **Keyboard + touch**: `WASD` / arrows for forward/back/turn, `Z/X` for strafe, `Space` for e-stop; all buttons are touch-friendly.
- **Bilingual (中文 / English)**: Toggle via the `🌐 中` button in the top-left header; preference persists to config.

---

## 📦 Installation

### 1. Install dependencies

```bash
git clone https://github.com/Owen1257173018/unitree-fleet.git
cd unitree-fleet

# Install the local WebRTC library (includes local patches: EC pubkey support + zh-CN Windows header fix)
pip install -e unitree_webrtc_connect-master/

# Install app dependencies
pip install -r requirements.txt
```

### 2. Run

```bash
python MultiRobotApp.py
```

### 3. (Optional) Bundle as a standalone app

The `MultiRobotApp.spec` supports both Windows and macOS — **you get whichever platform you build on**:

```bash
pip install pyinstaller
pyinstaller MultiRobotApp.spec
```

- Windows → `dist/MultiRobotApp.exe` (onefile, double-click to run)
- macOS → `dist/MultiRobotApp.app` (drop it into Applications)

> Cross-compilation is not supported; run PyInstaller on the target OS.

---

## 🚀 Quick Start

### Connecting old-firmware robots (Go2 < 1.1.15 / G1 < 1.5.1)

1. Put the computer and the robot on the same Wi-Fi subnet (or connect to the robot's hotspot directly).
2. **Go2**: click `📡 Scan LAN` → `Start Scan` (leaving the SN box empty scans all online Go2s) → check items → `✅ Add Selected`
3. **G1**: click `+ Add by IP` → fill IP / SN / choose type G1 → connect

### Connecting new-firmware robots (data2=3)

New firmware requires a **per-device AES-128 key** stored in Unitree's cloud. Two ways to get it:

- **A (recommended) — in-app fetch**: In the scan result or the Add-by-IP dialog, click the `☁` button → enter your Unitree account credentials → key is filled in and cached automatically.
- **B — CLI**: `python -m unitree_webrtc_connect._cli --email <your-email> --sn <robot-SN>`

Once fetched, the key is stored in the local config — you don't need to log in again for that robot.

### Save / restore a preset

Save the currently added robots as a named preset: `💾 Save Preset` → name it (e.g. "ShowA").
Next time, `📂 Load Preset` → pick it → all robots connect at once.

---

## 🏗 Architecture

```
MultiRobotApp.py  →  main_window.py  →  backend.py  →  unitree_webrtc_connect-master/
   (entry)           (PyQt6 UI)         (async logic)     (WebRTC library)
```

- **`backend.py`** owns a dedicated asyncio event-loop thread. All robot connections and commands run there. Results are posted back to the Qt UI thread via `pyqtSignal`.
- **`main_window.py`** has the left robot list + the right control panel; the panel switches between Go2 / G1 / mixed UIs based on the current selection.
- **`choreography.py`** contains the choreography editor, player, and `RecordingSession`.
- **`i18n.py`** is a tiny translation layer: Chinese-as-key with an English dictionary; misses fall back to Chinese.
- **`unitree_webrtc_connect-master/`** is a local fork of the official library with a few patches (EC pubkey fallback, zh-CN Windows header fix, etc.) — see credits below.

---

## 🛠 Config file

On first launch the app creates `unitree_robots_config.json` in the program directory:

```json
{
  "saved_configs": [
    {
      "name": "ShowA",
      "robots": [
        {"name": "DogA", "robot_type": "go2", "ip": "192.168.1.100",
         "aes_128_key": "abc...32-hex...", "sn": "B42D..."}
      ]
    }
  ],
  "unitree_email": "you@example.com",
  "language": "en"
}
```

> **Note**: passwords are never written; only the email is remembered to prefill next time. AES keys are stored in plaintext, so **don't share this config file** with anyone.

---

## ⚠️ Known limitations

- New-firmware robots must first be activated/bound via the official Unitree app (only devices visible in your cloud device list can have their key fetched).
- LAN scan only detects Go2 (relies on Unitree's multicast protocol). Use `+ Add by IP` to add G1 manually.
- LAN scan relies on the router allowing UDP multicast on the same subnet; some corporate/hotel networks block this.
- WebRTC video and lidar data channels are only subscribed (not fully visualized) at the moment.
- In rare cases Qt's `InternalMove` drag-drop wipes custom widgets; `RobotListPanel._on_order_changed()` re-binds them as a fallback.

---

## 🤝 Credits

- Upstream WebRTC library: **[unitree_webrtc_connect](https://github.com/legion1581/unitree_webrtc_connect)** by Konstantin Severov (MIT License). This repo bundles a local fork with the following patches:
  - EC public-key fallback added to `encryption.py`
  - Fix for `time.strftime("%Z")` returning non-ASCII on Chinese Windows in `unitree_cloud.py`
  - Structured exceptions + AES-128 key flow (kept in sync with upstream)
- UI colors: [Catppuccin Mocha](https://github.com/catppuccin/catppuccin).
- Unitree's official robots, documentation, and SDK.

---

## 📄 License

Released under the **MIT License**. The `unitree_webrtc_connect-master/` subdirectory retains its original MIT License, © Konstantin Severov.
