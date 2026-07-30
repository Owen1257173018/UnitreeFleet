"""
i18n.py — 极简双语翻译

设计思路：
  * 中文作为 key（源语言 = zh），en 字典按需翻译
  * 未命中的字符串直接原样返回，永不 crash
  * 支持 str.format() 占位：`tr("已连接 {n} 台", n=3)`
  * 切换语言 = 修改 _current_lang；建议在 UI 完全构建前设定，
    切换后需重启窗口/进程才能全部生效（因为大部分静态 QLabel/QPushButton
    的 text 是在构造时一次性写入的）

使用：
    from i18n import tr
    btn = QPushButton(tr("＋ IP 添加"))
    label.setText(tr("已连接 {n} 台", n=connected_count))
"""

from __future__ import annotations
from typing import Callable

_current_lang = "zh"

def set_language(lang: str) -> None:
    global _current_lang
    if lang not in ("zh", "en"):
        lang = "zh"
    _current_lang = lang

def get_language() -> str:
    return _current_lang


def tr(text: str, **fmt) -> str:
    """翻译 text。若当前语言是 en 且字典命中则返回英文，否则原样。
    可选 kwargs 参与 str.format 展开。"""
    if _current_lang == "en":
        out = _EN.get(text, text)
    else:
        out = text
    if fmt:
        try:
            out = out.format(**fmt)
        except (KeyError, IndexError, ValueError):
            pass
    return out


# 便捷别名（模仿 gettext 风格）
_: Callable[..., str] = tr


# ─────────────────────────────────────────────────────────────
# 英文翻译字典
# 添加/修改翻译只需要往这里加/改条目；缺失条目会自动 fallback 到中文。
# ─────────────────────────────────────────────────────────────
_EN: dict[str, str] = {
    # ── 主窗口 / 面板通用 ──
    "机器人列表": "Robots",
    "＋ IP 添加": "+ Add by IP",
    "💾 保存配置": "💾 Save Preset",
    "📂 配置连接": "📂 Load Preset",
    "📡 扫描添加": "📡 Scan LAN",
    "☑ 全选": "☑ Select All",
    "☐ 全不选": "☐ Deselect All",
    "🗑 删除": "🗑 Remove",
    "🎬 编排": "🎬 Choreo",
    "📂 编排库": "📂 Library",
    "📋 编排库": "📋 Library",
    "🔴 录制": "🔴 Record",
    "🎬 打开编排编辑器": "🎬 Open Choreography",
    "请在左侧选择机器人": "Select a robot on the left",
    "语言": "Language",
    "🌐 中文": "🌐 中文",
    "🌐 English": "🌐 English",
    "切换语言": "Switch Language",
    "语言已切换。": "Language changed.",
    "重启后完全生效。": "Restart the app to fully apply.",
    "现在退出？": "Quit now?",
    "对讲播放音量": "Talk playback volume",
    "麦克风：静音（点击开启说话）": "Mic: muted (click to talk)",
    "麦克风：开启（点击静音）": "Mic: on (click to mute)",

    # ── 移动控制 ──
    "移动控制 (W/S/A/D + Q/E 旋转 | Z/X 侧走 | Space 停止)":
        "Move (W/S/A/D + Q/E rotate | Z/X strafe | Space stop)",
    "移动控制（全部选中的机器人）": "Move (all selected robots)",
    "速度：": "Speed:",
    "  W/S = 前后  |  A/D/Q/E = 左右转  |  Z/X = 左右走  |  Space = 停止":
        "  W/S = forward/back  |  A/D/Q/E = turn  |  Z/X = strafe  |  Space = stop",
    "ℹ️  同时选中了 Go2 和 G1 机器人 — 混合模式下仅显示移动控制":
        "ℹ️  Mixed Go2 & G1 selection — only movement is shown in mixed mode",

    # ── 状态 ──
    "已连接": "Connected",
    "连接中…": "Connecting…",
    "已断开": "Disconnected",
    "错误": "Error",
    "重连中": "Reconnecting",
    "错误：{msg}": "Error: {msg}",

    # ── 按钮通用 ──
    "取消": "Cancel",
    "确定": "OK",
    "保存": "Save",
    "关闭": "Close",
    "连接": "Connect",
    "删除": "Delete",
    "提示": "Info",
    "警告": "Warning",
    "确认": "Confirm",
    "全选": "Select All",
    "全不选": "Deselect All",
    "已保存": "Saved",

    # ── AddByIPDialog ──
    "手动添加机器人": "Add Robot by IP",
    "设备信息": "Device Info",
    "名称：": "Name:",
    "IP 地址：": "IP address:",
    "SN：": "SN:",
    "Token：": "Token:",
    "AES 密钥：": "AES key:",
    "机器人类型": "Robot type",
    "🐕  Go2 机器狗": "🐕  Go2 Quadruped",
    "🤖  G1 人形机器人": "🤖  G1 Humanoid",
    "例：机器狗A  /  G1铁柱": "e.g. DogA / G1-01",
    "例：192.168.88.10": "e.g. 192.168.88.10",
    "选填，新固件拉取 AES 密钥时必需": "Optional; required to fetch AES key for new firmware",
    "选填（LocalSTA 通常不需要）": "Optional (LocalSTA usually not needed)",
    "32 位 16 进制（仅新固件需要，留空=老固件）":
        "32-hex chars (new firmware only; leave blank for old firmware)",
    "☁ 从云端获取": "☁ Fetch from cloud",
    "缺少名称": "Missing name",
    "请输入机器人名称。": "Please enter a robot name.",
    "缺少 IP": "Missing IP",
    "请填写机器人的 IP 地址。": "Please enter the robot's IP address.",
    "需要 SN": "SN required",
    "云端拉取需要 SN 序列号，请先填写。SN 可在机器人电池仓或机身贴纸找到。":
        "Fetching from cloud requires the SN. It's on the battery bay or a sticker on the robot.",

    # ── UnitreeCloudLoginDialog ──
    "从宇树云端获取 AES 密钥": "Fetch AES Key from Unitree Cloud",
    "目标机器人 SN：<b>{sn}</b><br>需要用您的 <b>宇树官方账号</b> 登录，仅用于一次性拉取该设备的<br>AES-128 密钥（持久化在本地配置，密码不会保存）。":
        "Target robot SN: <b>{sn}</b><br>Log in with your <b>Unitree account</b> to fetch this device's<br>AES-128 key once (cached locally; password is never stored).",
    "邮箱：": "Email:",
    "密码：": "Password:",
    "区域：": "Region:",
    "设备类型：": "Device type:",
    "global（国际）": "global (International)",
    "cn（中国）": "cn (China)",
    "获取密钥": "Fetch key",
    "获取中…": "Fetching…",
    "⚠ 请填写邮箱": "⚠ Please enter email",
    "⚠ 请填写密码": "⚠ Please enter password",
    "⏳ 正在连接宇树云端，请稍候…": "⏳ Connecting to Unitree cloud, please wait…",
    "云端未返回密钥（SN 可能未绑定到此账号）":
        "Cloud returned no key (SN may not be bound to this account)",
    "库不支持此功能（请确认已升级到新版）：{err}":
        "Library does not support this (please upgrade): {err}",
    "✅ 获取成功：{key}": "✅ Success: {key}",
    "❌ {msg}": "❌ {msg}",

    # ── AutoAddDialog ──
    "自动扫描添加": "Auto-Scan & Add",
    "目标 SN 列表（每行一个）": "Target SN list (one per line)",
    "保存此 SN 列表，下次自动填入": "Remember these SNs for next time",
    "超时：": "Timeout:",
    " 秒": " s",
    "📡  开始扫描": "📡  Start Scan",
    "扫描中…": "Scanning…",
    "扫描结果（勾选要添加的设备）": "Scan results (check items to add)",
    "✅  添加选中设备": "✅  Add Selected",
    "❌  未发现任何设备，请检查网络连接": "❌  No devices found — check network",
    "✅  发现 {n} 台设备，目标命中 {hit} 台": "✅  Found {n} devices; {hit} matched",
    "，{n} 台未在线": ", {n} offline",
    "离线": "offline",
    "设备名称": "Device name",
    "🐕 Go2 机器狗": "🐕 Go2",
    "🤖 G1 人形机器人": "🤖 G1",
    "✓ 已有密钥": "✓ Has key",
    "⚠ 需获取": "⚠ Need key",
    "从宇树云端拉取此设备的 AES-128 密钥": "Fetch AES-128 key for this device from cloud",
    "没有选中任何在线设备。": "No online device is selected.",
    "请在上方输入至少一个序列号。\n如果想扫描网络中所有设备，可不填 SN 直接扫描。":
        "Please enter at least one SN above.\nOr leave blank to scan all devices on the network.",

    # ── ConfirmDeleteDialog ──
    "确认删除": "Confirm Delete",
    "确定要断开并删除以下 {n} 台设备吗？": "Disconnect and remove these {n} devices?",

    # ── SaveConfigDialog / ConfigPickerDialog ──
    "保存当前配置": "Save Current Preset",
    "当前机器人列表为空，请先添加再保存。": "The robot list is empty — add robots first.",
    "将保存当前 {n} 台机器人的 IP / AES 密钥：":
        "Will save IP / AES key of the current {n} robot(s):",
    "配置名称：": "Preset name:",
    "例：客厅3只 / 演出A组": "e.g. LivingRoom3 / ShowGroupA",
    "✓ 含密钥": "✓ has key",
    "无密钥": "no key",
    "⚠ 请填写配置名称": "⚠ Please enter a preset name",
    "覆盖已有配置？": "Overwrite existing preset?",
    "配置「{name}」已存在，确定覆盖吗？": "Preset '{name}' already exists. Overwrite?",
    "当前机器人列表为空，请先添加机器人再保存配置。":
        "The robot list is empty. Add robots before saving a preset.",
    "配置「{name}」已保存（{n} 台机器人）。": "Preset '{name}' saved ({n} robots).",

    "配置连接": "Load Preset",
    "还没有保存任何配置。\n\n先用 IP 添加 / 扫描添加把机器人加到列表，\n再点「💾 保存配置」给当前列表取名保存。":
        "No presets yet.\n\nAdd robots via '+ Add by IP' or '📡 Scan LAN',\nthen click '💾 Save Preset' to name and save the current list.",
    "共 {n} 个配置，选择一个连接：": "{n} preset(s). Pick one to connect:",
    "连接此配置": "Connect this preset",
    "{n} 台 · {k} 台含密钥": "{n} robots · {k} with key",
    "删除配置": "Delete preset",
    "确定要删除配置「{name}」吗？此操作不可撤销。": "Delete preset '{name}'? This cannot be undone.",
    "请选择一个配置。": "Please select a preset.",

    # ── 主窗口右键菜单 / AES ──
    "🔑 编辑 AES 密钥（新固件）…": "🔑 Edit AES Key (new firmware)…",
    "需要 SN": "SN required",
    "此机器人没有 SN，无法从云端拉取 AES 密钥。请先删除后用「IP 添加」重新创建并填写 SN。":
        "This robot has no SN, cannot fetch key from cloud. Remove it and re-add via 'IP Add' with an SN.",
    "已更新": "Updated",
    "AES 密钥已更新，请尝试重新连接此机器人。": "AES key updated. Please reconnect this robot.",

    # ── 通话 / 对讲 ──
    "开启对讲": "Start talk",
    "结束对讲": "End talk",
    "🎙 [{name}] 开启对讲": "🎙 [{name}] talk started",
    "🎙 [{name}] 结束对讲": "🎙 [{name}] talk ended",
    "对讲当前仅支持 Go2": "Talk is currently Go2-only",
    "机器人未连接，无法开启对讲": "Robot not connected; cannot start talk",
    "对讲功能不可用：{err}": "Talk unavailable: {err}",
    "开启对讲失败：{err}": "Failed to start talk: {err}",
    "重新连接此机器人": "Reconnect this robot",

    # ── 连接错误 / 提示 ──
    "连接超时（15 秒），请检查 {addr} 是否在线":
        "Connection timeout (15s). Check whether {addr} is online.",
    "此机器人为新固件 (data2=3)，需要 AES-128 密钥。请右键机器人 → 编辑 AES 密钥，从云端拉取。":
        "New firmware (data2=3) requires an AES-128 key. Right-click the robot → Edit AES Key.",
    "AES 密钥不匹配（机器人重置/重置 SN 后会重新分配）。请重新从云端拉取。详情：{err}":
        "AES key mismatch (reassigned after robot reset). Please re-fetch from cloud. Details: {err}",
    "无法连接机器人 9991/8081 端口，请检查电源 / 网络（{err}）":
        "Cannot reach robot ports 9991/8081. Check power/network ({err})",
    "机器人已被其它客户端占用（手机 APP 等），请断开后重试":
        "Robot is already used by another client (mobile app). Disconnect it and retry.",
    "握手超时，机器人可能掉线：{err}": "Handshake timeout — robot may be offline: {err}",
    "连接失败：{err}": "Connection failed: {err}",
    "没有提供 IP 或 SN，无法连接": "No IP or SN provided; cannot connect",

    # ── 编排编辑器 ──
    "编排": "Choreography",
    "轨道": "Track",
    "步骤": "Step",
    "当前角色步骤列表": "Steps of current role",
    "↑ 上移": "↑ Up",
    "↓ 下移": "↓ Down",
    "✕ 删除": "✕ Delete",
    "应用": "Apply",
    "修改时长：": "Duration:",
    "移动": "Move",
    "移动适用于 Go2 和 G1，播放时持续发送摇杆指令直到步骤结束。":
        "Move works for both Go2 and G1; joystick signals are sent continuously until step ends.",
    "方向控制": "Direction",
    "↺\n左转": "↺\nTurn L",
    "▲\n前进": "▲\nForward",
    "↻\n右转": "↻\nTurn R",
    "◀\n左移": "◀\nStrafe L",
    "▶\n右移": "▶\nStrafe R",
    "▼\n后退": "▼\nBack",
    "▲ 前进": "▲ Forward",
    "▼ 后退": "▼ Back",
    "↺ 左转": "↺ Turn L",
    "↻ 右转": "↻ Turn R",
    "◀ 左移": "◀ Strafe L",
    "▶ 右移": "▶ Strafe R",
    "手臂动作（固定 {n} 秒）": "Arm Actions (fixed {n}s)",
    "运动模式（固定 {n} 秒）": "Move Modes (fixed {n}s)",
    "手臂动作": "Arm Actions",
    "运动模式": "Move Modes",
    "该动作时长：{s} s（已固定）": "Duration: {s}s (fixed)",
    "该模式时长：{s} s（已固定）": "Duration: {s}s (fixed)",
    "时长过短": "Duration too short",
    "该 {type} 动作的标准时长为 {std}s。\n缩短到 {new}s 会导致动作还没跑完就开始下一步，造成时间线与实际不同步。\n\n确定要缩短吗？":
        "The standard duration of this {type} action is {std}s.\nShortening to {new}s can cause the next step to fire before this one finishes, breaking timeline sync.\n\nProceed?",
    "sport": "sport",
    "G1 手臂": "G1 arm",
    "G1 运动模式": "G1 move mode",
    "新编排": "New Choreography",

    # ── 保存 / 导入 / 导出 ──
    "打开编排": "Open Choreography",
    "保存编排": "Save Choreography",
    "另存为": "Save As",
    "导入": "Import",
    "导出": "Export",
    "未命名": "Untitled",

    # ── 录制 ──
    "🔴 开始录制": "🔴 Start Recording",
    "⏹ 停止录制": "⏹ Stop Recording",
    "录制": "Recording",

    # ── 电量 ──
    "{pct}%": "{pct}%",

    # ── 主窗口 / 选择状态 / 日志面板 ──
    "已选 {n} / {t}": "{n} / {t} selected",
    "无法录制": "Cannot record",
    "列表中没有机器人，请先添加并连接机器人。":
        "The robot list is empty. Add and connect a robot first.",
    "注意": "Notice",
    "当前没有已连接的机器人。录制会记录设备列表的布局，但至少需要连接一台机器人才能实际捕获动作。\n\n录制已开始，连接机器人后的操作将被记录。":
        "No robots are connected. Recording will keep the layout, but at least one connected robot is needed to capture actions.\n\nRecording started; actions on any newly-connected robot will be captured.",
    "⏹ 停止录制": "⏹ Stop Recording",
    "⏺ 录制": "⏺ Record",
    "录制为空": "Recording empty",
    "录制期间没有捕获到任何操作，未保存文件。\n请确认在录制期间有对机器人执行动作（移动、sport 指令等）。":
        "No actions captured; nothing was saved.\nMake sure the robot received some action during the recording (movement, sport commands, etc.).",
    "保存失败": "Save failed",
    "录制完成": "Recording done",
    "录制已保存：\n{path}": "Recording saved to:\n{path}",
    "是否立即在编排编辑器中打开以查看或继续编辑？":
        "Open it in the Choreography Editor now to review or edit?",
    "打开编排编辑器：为多个机器人设计动作时间线，保存到 choreo_auto/":
        "Open the Choreography Editor: design action timelines for multiple robots, saved to choreo_auto/",
    "扫描 choreo_auto/ 目录，选择兼容的编排直接播放":
        "Scan choreo_auto/ and pick a compatible choreography to play directly",
    "开始录制：记录对所有机器人的操作，停止后保存为可回放的 JSON 文件":
        "Start recording: capture all robot actions and save as a replayable JSON",
    "已选中": "Selected",
    "日志": "Log",
    "清空": "Clear",
    "↺ 重连": "↺ Reconnect",
    "← 在左侧选择机器人\n单选：显示该机器人全部控制\n多选（Ctrl/Shift）：显示通用移动控制":
        "← Select a robot on the left\nSingle-select: show that robot's full controls\nMulti-select (Ctrl/Shift): show shared movement controls",

    # ── Go2 / G1 Tab labels ──
    "高级设置": "Advanced",
    "LED 颜色：": "LED color:",
    "LED 亮度：": "LED brightness:",
    "设置": "Apply",
    "运动模式：": "Motion mode:",
    "普通": "Normal",
    "AI": "AI",
    "音乐播放": "Music",

    # ── Choreography 编辑器 ──
    "机器人编排编辑器": "Choreography Editor",
    "编排名称：": "Choreography name:",
    "📂 加载": "📂 Load",
    "➕ 追加编排": "➕ Append",
    "💾 保存": "💾 Save",
    "▶  播放": "▶  Play",
    "🗑 清空步骤": "🗑 Clear steps",
    "选择另一份编排 JSON，把它的步骤按位置并联地接在当前编排末尾。\n两份编排将同时运行。轨道布局（数量 + 每个位置的类型）必须完全一致。":
        "Pick another choreography JSON and append its steps in parallel by track position.\nBoth choreographies run at the same time. Track layout (count + type per slot) must match exactly.",
    "清空所有轨道的步骤，但保留轨道布局":
        "Clear all steps but keep the track layout",
    "时间线预览（点击步骤可快速定位）":
        "Timeline preview (click a step to jump)",
    "轨道（对应设备列表位置）": "Tracks (mapped to device list positions)",
    "轨道 #N 对应左侧设备列表第 N 个机器人。\n可手动添加 Go2 / G1 轨道，也可按设备列表自动生成。":
        "Track #N maps to the Nth robot in the device list on the left.\nAdd Go2/G1 tracks manually, or auto-generate from the device list.",
    "添加一条 Go2（机器狗）空轨道": "Add an empty Go2 track",
    "添加一条 G1（人形）空轨道": "Add an empty G1 track",
    "删除选中轨道": "Delete selected track",
    "从本编排移除选中的轨道并重新编号。通常用于裁掉未使用的空轨道，\n让编排文件可在更少机器人的设备列表上播放。":
        "Remove the selected track from this choreography and renumber. Typically used to trim unused empty tracks\nso the file plays on device lists with fewer robots.",
    "按当前设备列表重置": "Reseed from device list",
    "清空当前所有步骤，按当前设备列表（从上到下）重新 seed 轨道。":
        "Clear all steps and reseed tracks from the current device list (top to bottom).",
    "动作选择": "Actions",
    "步骤时长：": "Step duration:",
    "⏸  添加等待": "⏸  Add wait",
    "不发命令，仅等待指定时长": "Send no command; just wait the given duration",
    "等待 {s}s": "wait {s}s",
    "Go2 动作": "Go2 Actions",
    "G1 动作": "G1 Actions",
    "当前角色步骤列表": "Steps of Current Track",
    "修改时长：": "Change duration:",
    "请先在左侧选择一个角色": "Please select a track on the left",
    "编排为空，请先添加角色和步骤": "Choreography is empty; add tracks and steps first",
    "加载失败": "Load failed",
    "编排为空，请先在左侧添加机器人": "Choreography is empty; add robots on the left first",
    "所有轨道都没有步骤，无法播放": "No steps in any track; nothing to play",
    "无法播放": "Cannot play",
    "编排播放器": "Choreography Player",
    "播放进度": "Progress",
    "▶  开始播放": "▶  Play",
    "⏹  停止": "⏹  Stop",
    "🚨  全体紧急停止": "🚨  Emergency Stop All",
    "编排布局与当前设备列表不一致，无法开始播放。\n请在「编排库」打开本编排，在编辑器中删除多余的空轨道后保存再试。":
        "Track layout does not match the current device list; cannot play.\nOpen it in the Library and remove unused tracks from the editor, then save and retry.",
    "执行日志": "Execution log",
    "编排中所有轨道都没有步骤。": "No steps in any track.",
    "编排库  —  choreo_auto/": "Choreography Library — choreo_auto/",
    "↺ 刷新": "↺ Refresh",
    "▶  播放选中编排": "▶  Play Selected",
    "✏ 在编辑器中打开": "✏ Open in Editor",
    "📂 打开目录": "📂 Open Directory",
    "当前设备列表为空": "Device list is empty",

    # ── Go2 action categories (from backend.GO2_ACTIONS) ──
    "基础姿态": "Basic Postures",
    "情感互动": "Emotion & Interaction",
    "舞蹈": "Dance",
    "杂技": "Stunts",
    "步态": "Gaits",

    # ── Joystick / button labels ──
    "⬛\n停止\nSpace": "⬛\nStop\nSpace",
    "重连中…": "Reconnecting…",
    "连接中…": "Connecting…",
    "已断开": "Disconnected",
    "A / ← 左转": "A / ← Turn L",
    "D / → 右转": "D / → Turn R",
    "Z 左移": "Z Strafe L",
    "X 右移": "X Strafe R",

    # ── Main window title + status bar ──
    "Unitree 多机器人控制台": "Unitree Fleet",
    "机器人：{n}": "Robots: {n}",
    "已连接：{n}": "Connected: {n}",
    "✓ {name} 指令成功": "✓ {name} command OK",
    "✓ {name} 已连接": "✓ {name} connected",
    " 等 {n} 台": " and {n} more",
    "⚠️ 确认对 G1 急停？": "⚠️ Emergency-stop G1?",
    "G1 急停会立即切阻尼、腿部瞬间卸力——如果这时候正在走跑，会直接摔倒。\n这个场景没有实测验证过安全性，确定要继续吗？\n\n目标：{names}":
        "G1 emergency-stop switches to damping mode immediately and legs go limp — if it's walking/running it will fall over.\nThis scenario is untested; are you sure?\n\nTarget: {names}",

    # ── Music panel ──
    "机器人内置音频：": "On-robot audio:",
    "刷新列表": "Refresh",
    "▶ 播放": "▶ Play",
    "⏸ 暂停": "⏸ Pause",
    "⏵ 继续": "⏵ Resume",
    "上传": "Upload",
    "正在加载…": "Loading…",
    "（无音频文件）": "(no audio files)",
    "选择音频文件": "Choose audio file",
    "音频文件 (*.mp3 *.wav);;MP3 (*.mp3);;WAV (*.wav)":
        "Audio files (*.mp3 *.wav);;MP3 (*.mp3);;WAV (*.wav)",

    # ── Choreography extras ──
    "确认删除": "Confirm delete",
    "{role} 有 {n} 个步骤，删除后这些步骤会一并丢失，确定吗？":
        "{role} has {n} steps. Delete anyway (steps will be lost)?",
    "确认重置": "Confirm reset",
    "将清空当前所有轨道和步骤，按设备列表重新生成空轨道，确定吗？":
        "Clear all tracks and steps and reseed from the device list. Proceed?",
    "编排为空": "Empty choreography",
    "当前编排的所有轨道都没有任何步骤，保存后也无法播放。\n确定要保存这个空编排吗？":
        "None of the tracks have any steps. This choreography cannot be played after saving.\nSave anyway?",
    "新编排": "New Choreography",
    "保存编排": "Save Choreography",
    "保存成功": "Saved",
    "已保存：\n{path}\n\n（choreo_auto/ 目录中的文件可从主界面直接加载播放）":
        "Saved to:\n{path}\n\n(Files in choreo_auto/ can be loaded directly from the Library.)",
    "加载编排": "Load Choreography",
    "选择要并行追加的编排 JSON": "Choose choreography JSON to append in parallel",
    "无可追加内容": "Nothing to append",
    "待追加的编排里没有任何轨道。": "The chosen file has no tracks.",
    "追加成功": "Appended",
    "已把《{name}》以并行方式追加为新轨道。\n轨道数：{a} → {b}\n总时长：{ta}s  →  {tb}s\n\n⚠ 播放时设备列表必须有至少 {b} 个机器人，且每个位置的类型要匹配，否则请先在设备列表中补齐/换位。":
        "Appended '{name}' as parallel tracks.\nTracks: {a} → {b}\nTotal duration: {ta}s → {tb}s\n\n⚠ Playback requires at least {b} robots in the device list with matching types at each position.",
    "确认清空": "Confirm clear",
    "清空将删除所有步骤（保留轨道布局），确定吗？":
        "This clears all steps (tracks are kept). Proceed?",
    "未保存的更改": "Unsaved changes",
    "当前编排有未保存的修改，直接关闭会丢失这些内容。\n\n确定要放弃修改并关闭吗？":
        "This choreography has unsaved changes.\n\nDiscard changes and close?",
    "暂无内容 — 请先添加角色和步骤":
        "Empty — please add a track and some steps first",
    "移动": "Move",
    "等待": "wait",
    "等待 {s}s": "wait {s}s",
    "{label} (速度{speed})": "{label} (speed {speed})",
    "{dir}(速度{speed})": "{dir} (speed {speed})",

    # ── Timeline player (dynamic labels) ──
    "剧本：{name}  |  位置数：{n}  |  总时长：{s} 秒":
        "Script: {name}  |  Tracks: {n}  |  Duration: {s}s",
    "位置映射  —  编排轨道 #N  →  设备列表第 N 个机器人":
        "Track mapping — Choreo track #N → Nth robot in device list",
    "{n} 步  →": "{n} steps  →",
    "（编排无第 {i} 条轨道）  →": "(no track #{i} in choreography)  →",
    "已连接": "Connected",
    "未连接": "Not connected",
    "第 {i} 个：": "#{i}: ",
    "（编排无此轨道）": "(no matching track)",
    "（设备列表无第 {i} 个机器人）": "(no robot #{i} in device list)",
    "⚠ 布局不匹配：{msg}": "⚠ Layout mismatch: {msg}",
    "▶ 开始播放": "▶ Playback started",
    "⏹ 播放停止": "⏹ Playback stopped",
    "🚨 全体紧急停止！": "🚨 Emergency stop all!",
    "⚠ {role}：机器人未连接，跳过 [{label}]":
        "⚠ {role}: robot not connected, skipping [{label}]",
    "✅ 编排播放完成，已发送收尾停止+恢复站立":
        "✅ Playback complete; sent StopMove + RecoveryStand",

    # ── Choreography library ──
    "📂  扫描目录：{path}": "📂  Scanning: {path}",
    "当前设备列表（按顺序）：{n} 个 — ": "Device list (in order): {n} — ",
    "  （choreo_auto/ 目录为空，请先在编排编辑器中保存剧本）":
        "  (choreo_auto/ is empty — save a choreography from the editor first)",
    "  ⚠ {name}  （解析失败：{err}）": "  ⚠ {name}  (parse failed: {err})",
    "✅ 可播放": "✅ Playable",
    "⚠ 布局不匹配": "⚠ Layout mismatch",
    "要求：": "requires: ",
    "（共 {n} 个位置）": "（{n} slots total）",
    "本编排要求设备列表有 {ns} 个机器人（按顺序），但当前设备列表有 {nd} 个。请在编排库中打开编辑器删除多余的空白轨道后再试。":
        "This choreography needs {ns} robots (in order), but the current device list has {nd}. Open it in the Library and remove unused empty tracks in the editor first.",
    "第 {i} 个位置类型不匹配：编排需要 {want}，当前设备列表该位置是 {have}（{name}）。":
        "Position #{i} type mismatch: choreography wants {want}, device list has {have} ({name}).",

    # ── G1 action labels + move modes (from backend constants) ──
    "握手": "Handshake",
    "击掌": "High Five",
    "拥抱": "Hug",
    "高挥手": "Wave High",
    "鼓掌": "Clap",
    "脸旁挥手": "Face Wave",
    "左飞吻": "Kiss (L)",
    "手心爱心": "Palm Heart",
    "右爱心": "Heart (R)",
    "双手举起": "Hands Up",
    "X光造型": "X-Ray Pose",
    "右手举起": "Right Hand Up",
    "拒绝": "Refuse",
    "收手/取消": "Retract / Cancel",
    "阻尼": "Damping",
    "锁定站立": "Stand Lock",
    "蹲起/蹲下": "Squat / Rise",
    "跑步": "Run",

    # ── Go2 sport action categories + labels (backend.GO2_ACTIONS) ──
    "基本姿态": "Basic Postures",
    "舞蹈动作": "Dances",
    "高难特技": "Stunts",
    "互动动作": "Interactions",
    "归正": "Recovery",
    "正常站立": "Stand Up",
    "趴下": "Lie Down",
    "坐下": "Sit",
    "平衡站": "Balance Stand",
    "停止移动": "Stop Move",
    "阻尼模式": "Damping Mode",
    "舞蹈1": "Dance 1",
    "舞蹈2": "Dance 2",
    "扭臀": "Wiggle Hips",
    "太空步": "Moon Walk",
    "交叉步": "Cross Step",
    "单侧步": "One-sided Step",
    "跳跃奔跑": "Bound",
    "前空翻": "Front Flip",
    "后空翻": "Back Flip",
    "左空翻": "Left Flip",
    "右空翻": "Right Flip",
    "向前跳": "Front Jump",
    "前扑": "Front Pounce",
    "倒立": "Handstand",
    "打招呼": "Hello",
    "伸展": "Stretch",
    "比心": "Finger Heart",
    "打滚": "Wallow",
    "挠头": "Scrape",
    "满足": "Content",
    "造型": "Pose",
    "坐立": "Rise Sit",

    # ── VUI colors ──
    # ── 最后一批补漏 ──
    "⚠ 请填写 SN 序列号": "⚠ Please enter the SN",
    "✓ 密钥": "✓ key",
    "不会保存到本地": "Not stored locally",
    "在这里直接填 <b>SN</b> 和选 <b>设备类型</b>，再用您的 <b>宇树官方账号</b> 登录，<br>一次性拉取该设备的 AES-128 密钥（持久化在本地配置，密码不会保存）。":
        "Enter the <b>SN</b> and pick the <b>device type</b> here, then log in with your <b>Unitree account</b><br>to fetch this robot's AES-128 key (cached locally; password is never stored).",
    "机器人电池仓/机身贴纸上的序列号":
        "Serial number from the robot's battery bay or body sticker",

    "白": "White",
    "红": "Red",
    "黄": "Yellow",
    "蓝": "Blue",
    "绿": "Green",
    "青": "Cyan",
    "紫": "Purple",
}
