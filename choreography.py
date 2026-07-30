"""
choreography.py — 机器人编排功能

ChoreoStep         : 一个动作步骤（类型 + api_id + 持续时长）
ChoreoTrack        : 单个机器人角色的步骤序列
ChoreoScript       : 完整编排剧本（多角色），可序列化为 JSON 文件

TimelineCanvas     : QPainter 时间线预览控件
ChoreoEditorDialog : 编排编辑器对话框
ChoreoPlayerDialog : 编排播放器（角色分配 + 播放控制 + 紧急停止）
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sys
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


def _sanitize_filename(name: str) -> str:
    """去掉文件名里非法/保留的字符，避免 \\ / : * ? \" < > | 与路径分隔符；
    如末尾已是 .json 则剥掉，避免拼接后变成 .json.json。"""
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" .")
    if safe.lower().endswith(".json"):
        safe = safe[:-5].rstrip(" .")
    return safe or "新编排"

# ──────────────────────────────────────────────────────────
# 编排自动保存目录（应用根目录下的 choreo_auto/ 子目录）
# 打包后 __file__ 指向 _internal/，所以用 sys.executable 的目录
# ──────────────────────────────────────────────────────────
def _choreo_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CHOREO_AUTO_DIR = os.path.join(_choreo_root(), "choreo_auto")
os.makedirs(CHOREO_AUTO_DIR, exist_ok=True)

from PyQt6.QtCore import Qt, QTimer, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QGroupBox,
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QDoubleSpinBox, QSpinBox,
    QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
    QComboBox,
)

from backend import (
    RobotManager, RobotInfo,
    GO2_ACTIONS, G1_ARM_ACTIONS, G1_MOVE_MODES, SPORT_CMD,
    ROBOT_TYPE_GO2, ROBOT_TYPE_G1,
    STATUS_CONNECTED,
    set_playback_verbose_logging,
)
from i18n import tr

logger = logging.getLogger("unitree.choreo")


# ──────────────────────────────────────────────────────────
# 样式常量
# ──────────────────────────────────────────────────────────
_DIALOG_STYLE = """
    QDialog, QWidget   { background: #1e1e2e; color: #cdd6f4; }
    QGroupBox          { border: 1px solid #45475a; border-radius: 5px;
                         margin-top: 10px; padding-top: 4px; color: #89b4fa; }
    QGroupBox::title   { subcontrol-origin: margin; left: 8px; }
    QListWidget        { background: #11111b; border: 1px solid #313244;
                         border-radius: 4px; }
    QListWidget::item  { padding: 4px 6px; }
    QListWidget::item:selected { background: #313244; color: #cdd6f4; }
    QLineEdit, QSpinBox, QDoubleSpinBox { background: #181825; border: 1px solid #45475a;
                          border-radius: 4px; padding: 3px 6px; color: #cdd6f4; }
    QComboBox          { background: #181825; border: 1px solid #45475a;
                         border-radius: 4px; padding: 2px 6px; color: #cdd6f4; }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView { background: #181825; color: #cdd6f4; }
    QProgressBar       { background: #181825; border: 1px solid #313244;
                         border-radius: 4px; text-align: center; color: #cdd6f4; }
    QProgressBar::chunk { background: #a6e3a1; border-radius: 3px; }
    QTextEdit          { background: #11111b; color: #a6adc8; border: none;
                         font-family: Consolas, Menlo, monospace; font-size: 11px; }
    QScrollArea        { border: none; }
    QScrollBar:vertical   { background: #181825; width: 6px; border-radius: 3px; }
    QScrollBar::handle:vertical { background: #45475a; border-radius: 3px;
                                  min-height: 20px; }
    QScrollBar:horizontal { background: #181825; height: 6px; border-radius: 3px; }
    QScrollBar::handle:horizontal { background: #45475a; border-radius: 3px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QTabWidget::pane   { border: 1px solid #45475a; background: #1e1e2e; }
    QTabBar::tab       { background: #2a2a3e; color: #a6adc8; padding: 5px 12px;
                         border-top-left-radius: 4px; border-top-right-radius: 4px; }
    QTabBar::tab:selected { background: #313244; color: #89b4fa; }
    QTabBar::tab:hover    { background: #313244; }
"""

_BTN = """
    QPushButton { background: #313244; color: #cdd6f4;
        border: 1px solid #45475a; border-radius: 4px;
        padding: 5px 10px; font-size: 12px; }
    QPushButton:hover   { background: #45475a; }
    QPushButton:pressed { background: #585b70; }
    QPushButton:disabled { color: #585b70; border-color: #313244; }
"""
_PRIMARY = """
    QPushButton { background: #1e3a5f; color: #89b4fa;
        border: 1px solid #3a6898; border-radius: 4px;
        padding: 5px 10px; font-weight: bold; }
    QPushButton:hover    { background: #274d7a; }
    QPushButton:pressed  { background: #1a3254; }
    QPushButton:disabled { background: #1e2535; color: #45475a; border-color: #313244; }
"""
_DANGER = """
    QPushButton { background: #3d2020; color: #f38ba8;
        border: 1px solid #7d2a2a; border-radius: 4px;
        padding: 5px 10px; }
    QPushButton:hover   { background: #4d2828; }
    QPushButton:pressed { background: #5d3030; }
    QPushButton:disabled { color: #585b70; border-color: #313244;
                           background: #2a2020; }
"""
_ACTION_BTN = """
    QPushButton { background: #252535; color: #cdd6f4;
        border: 1px solid #45475a; border-radius: 4px;
        padding: 3px 6px; font-size: 11px; }
    QPushButton:hover { background: #35354f; border-color: #89b4fa; }
    QPushButton:pressed { background: #45455f; }
"""


# ──────────────────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────────────────
@dataclass
class ChoreoStep:
    """单个动作步骤。"""
    action_type: str   # "sport" | "arm" | "g1_mode" | "move" | "wait"
    api_id: int        # sport api_id / arm data / g1_mode code / 0 for move|wait
    label: str         # 显示名称
    duration_ms: int   # 发送动作后等待多少毫秒再执行下一步
    parameters: dict = field(default_factory=dict)


@dataclass
class ChoreoTrack:
    """单个机器人角色的步骤序列。"""
    role_name: str     # 角色名，如 "Go2 角色1"
    robot_type: str    # "go2" | "g1"
    steps: List[ChoreoStep] = field(default_factory=list)

    def total_duration_ms(self) -> int:
        return sum(s.duration_ms for s in self.steps)


def _slot_role_name(idx0: int, robot_type: str) -> str:
    """根据位置生成角色名：'#1 Go2' / '#3 G1'（idx0 为 0-based）"""
    type_label = "Go2" if robot_type == ROBOT_TYPE_GO2 else "G1"
    return f"#{idx0 + 1} {type_label}"


def renumber_tracks(script: "ChoreoScript"):
    """按当前 tracks 列表顺序，重新生成每条轨道的 role_name（#1/#2/...）。"""
    for i, t in enumerate(script.tracks):
        t.role_name = _slot_role_name(i, t.robot_type)


# ──────────────────────────────────────────────────────────
# 动作时长表
# 机器狗没有可靠的"停动作"API，所以编排必须给每条动作预留完整执行时间。
# 舞蹈1=25s，舞蹈2=40s，其他动作统一 15s。
# ──────────────────────────────────────────────────────────
_SPORT_DURATION_MS: Dict[int, int] = {
    SPORT_CMD["Dance1"]: 20_000,
    SPORT_CMD["Dance2"]: 40_000,
}
SPORT_DEFAULT_DURATION_MS = 5_000

# G1 手臂动作 / 运动模式 也没"停动作"API，只能按固定时长预留，下一步等本步走完才开始。
# 实机测下来 10 秒才够：G1 是双足人形，手臂动作和起蹲这类状态切换都比四足慢，
# 之前按 5 秒（照抄 Go2 sport 默认值）会在上一步还没做完时就发下一步，编排时间线漂掉。
G1_ACTION_FIXED_MS = 10_000


def get_sport_duration_ms(api_id: int) -> int:
    """Go2 sport 动作的标准时长（毫秒）。"""
    return _SPORT_DURATION_MS.get(api_id, SPORT_DEFAULT_DURATION_MS)


def get_fixed_duration_ms(action_type: str, api_id: int) -> Optional[int]:
    """返回需要"固定"的动作时长（毫秒），不可缩短。None 表示该类型用户可自定。

    G1 arm / g1_mode 与 Go2 sport 一样统一固定，避免编排时间线漂移。
    """
    if action_type == "sport":
        return get_sport_duration_ms(api_id)
    if action_type in ("arm", "g1_mode"):
        return G1_ACTION_FIXED_MS
    return None


class ChoreoScript:
    """完整编排剧本，可序列化为 JSON。"""

    def __init__(self, name: str = "新编排"):
        self.name   = name
        self.tracks: List[ChoreoTrack] = []

    def total_duration_ms(self) -> int:
        if not self.tracks:
            return 0
        return max((t.total_duration_ms() for t in self.tracks), default=0)

    def has_any_steps(self) -> bool:
        return any(t.steps for t in self.tracks)

    def describe_layout(self) -> str:
        """例：'Go2 × 2 + G1 × 1（共 3 个位置）'"""
        n_go2 = sum(1 for t in self.tracks if t.robot_type == ROBOT_TYPE_GO2)
        n_g1  = sum(1 for t in self.tracks if t.robot_type == ROBOT_TYPE_G1)
        parts = []
        if n_go2: parts.append(f"Go2 × {n_go2}")
        if n_g1:  parts.append(f"G1 × {n_g1}")
        return " + ".join(parts) + tr("（共 {n} 个位置）", n=len(self.tracks))

    # ── 序列化 ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name":   self.name,
            "tracks": [
                {
                    "role_name":  t.role_name,
                    "robot_type": t.robot_type,
                    "steps": [
                        {
                            "action_type": s.action_type,
                            "api_id":      s.api_id,
                            "label":       s.label,
                            "duration_ms": s.duration_ms,
                            "parameters":  s.parameters,
                        }
                        for s in t.steps
                    ],
                }
                for t in self.tracks
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChoreoScript":
        script = cls(name=d.get("name", "编排"))
        for td in d.get("tracks", []):
            track = ChoreoTrack(
                role_name=td["role_name"],
                robot_type=td["robot_type"],
                steps=[
                    ChoreoStep(
                        action_type=sd["action_type"],
                        api_id=sd["api_id"],
                        label=sd["label"],
                        duration_ms=sd["duration_ms"],
                        parameters=sd.get("parameters", {}),
                    )
                    for sd in td.get("steps", [])
                ],
            )
            script.tracks.append(track)
        return script

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("编排已保存：%s", path)

    @classmethod
    def load(cls, path: str) -> "ChoreoScript":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        script = cls.from_dict(data)
        logger.info("编排已加载：%s  tracks=%d", path, len(script.tracks))
        return script


def append_script_parallel(base: "ChoreoScript", other: "ChoreoScript"):
    """把 other 的每条轨道作为**新的独立轨道**追加到 base 下方。

    结果：base 的轨道数 = 原 base 轨道数 + other 轨道数，
    所有轨道从 t=0 起同时开始，形成并行时间线。
    例：2 条狗 + 另 1 条狗 = 3 条狗并行。
    追加完后按新的顺序重新编号（#1、#2、#3…）。
    """
    for tb in other.tracks:
        new_track = ChoreoTrack(
            role_name=tb.role_name,   # 会被 renumber_tracks 覆盖
            robot_type=tb.robot_type,
            steps=[ChoreoStep(
                action_type=s.action_type,
                api_id=s.api_id,
                label=s.label,
                duration_ms=s.duration_ms,
                parameters=dict(s.parameters) if s.parameters else {},
            ) for s in tb.steps],
        )
        base.tracks.append(new_track)
    renumber_tracks(base)


def check_script_compat(script: "ChoreoScript",
                        ordered_robots: List[RobotInfo]
                        ) -> Tuple[bool, str]:
    """
    严格按位置比对：len 必须相等，每个位置 robot_type 必须一致。
    匹配失败返回 (False, 说明文本)；成功返回 (True, "")。
    """
    n_script = len(script.tracks)
    n_dev    = len(ordered_robots)
    if n_script != n_dev:
        return False, tr(
            "本编排要求设备列表有 {ns} 个机器人（按顺序），"
            "但当前设备列表有 {nd} 个。"
            "请在编排库中打开编辑器删除多余的空白轨道后再试。",
            ns=n_script, nd=n_dev)
    for i, (track, robot) in enumerate(zip(script.tracks, ordered_robots)):
        if track.robot_type != robot.robot_type:
            want = "Go2" if track.robot_type == ROBOT_TYPE_GO2 else "G1"
            have = "Go2" if robot.robot_type  == ROBOT_TYPE_GO2 else "G1"
            return False, tr(
                "第 {i} 个位置类型不匹配：编排需要 {want}，"
                "当前设备列表该位置是 {have}（{name}）。",
                i=i + 1, want=want, have=have, name=robot.name)
    return True, ""


# ──────────────────────────────────────────────────────────
# 录制辅助
# ──────────────────────────────────────────────────────────
def _move_label(lx: float, ly: float, rx: float) -> str:
    if   ly >  0.1: return tr("▲ 前进")
    if   ly < -0.1: return tr("▼ 后退")
    if   rx < -0.1: return tr("↺ 左转")
    if   rx >  0.1: return tr("↻ 右转")
    if   lx < -0.1: return tr("◀ 左移")
    if   lx >  0.1: return tr("▶ 右移")
    return tr("移动")


class RecordingSession:
    """
    实时录制操作会话，将对机器人的操作转化为 ChoreoScript。

    用法：
      session = RecordingSession(ordered_robot_infos)
      manager.set_recording_hook(session.on_event)
      ...操作机器人...
      manager.clear_recording_hook()
      session.flush_joystick()
      script = session.build_script("录制名称")
    """

    def __init__(self, robot_infos: List[RobotInfo]):
        self._robots   = list(robot_infos)   # 按列表顺序
        self._start_ms = int(_time.time() * 1000)
        self._start_monotonic = _time.monotonic()  # 修复P3：添加monotonic初始化
        # robot_id → [(abs_ms, action_type, api_id, label, params_dict), ...]
        self._events: Dict[str, List] = {r.id: [] for r in robot_infos}
        # 摇杆状态跟踪
        self._joy_state:    Dict[str, tuple] = {r.id: (0.0, 0.0, 0.0, 0.0) for r in robot_infos}
        self._joy_start_ms: Dict[str, int]   = {}

    def _now_ms(self) -> int:
        # 修复P3：使用monotonic()代替time()以不受NTP调整影响
        return int((_time.monotonic() - self._start_monotonic) * 1000)

    def on_event(self, event: str, robot_ids: List[str], **kw):
        """由 RobotManager 钩子调用（可在任意线程，仅写 Python 对象，线程安全）。"""
        t = self._now_ms()
        for rid in robot_ids:
            if rid not in self._events:
                continue
            if event == "sport":
                api_id = kw["api_id"]
                label  = next((k for k, v in SPORT_CMD.items() if v == api_id), str(api_id))
                self._events[rid].append((t, "sport", api_id, label, {}))
            elif event == "arm":
                d     = kw["action_data"]
                label = next((l for dd, l in G1_ARM_ACTIONS if dd == d), str(d))
                self._events[rid].append((t, "arm", d, label, {}))
            elif event == "g1_mode":
                c     = kw["mode_data"]
                label = next((l for cc, l in G1_MOVE_MODES if cc == c), str(c))
                self._events[rid].append((t, "g1_mode", c, label, {}))
            elif event == "joystick":
                self._handle_joystick(rid, t, kw["lx"], kw["ly"], kw["rx"], kw.get("ry", 0.0))

    def _handle_joystick(self, rid: str, t: int,
                         lx: float, ly: float, rx: float, ry: float):
        prev      = self._joy_state.get(rid, (0.0, 0.0, 0.0, 0.0))
        is_zero   = (abs(lx) < 0.05 and abs(ly) < 0.05 and abs(rx) < 0.05)
        was_zero  = (abs(prev[0]) < 0.05 and abs(prev[1]) < 0.05 and abs(prev[2]) < 0.05)
        # 方向变化：取1位小数避免浮点抖动
        cur_dir   = (round(lx, 1), round(ly, 1), round(rx, 1))
        prev_dir  = (round(prev[0], 1), round(prev[1], 1), round(prev[2], 1))

        if not is_zero and was_zero:
            self._joy_start_ms[rid] = t
            self._joy_state[rid]    = (lx, ly, rx, ry)
        elif not is_zero and not was_zero and cur_dir != prev_dir:
            # 方向改变：先结束上一段，再开始新的
            self._emit_joystick(rid, t, prev[0], prev[1], prev[2], prev[3])
            self._joy_start_ms[rid] = t
            self._joy_state[rid]    = (lx, ly, rx, ry)
        elif is_zero and not was_zero:
            self._emit_joystick(rid, t, prev[0], prev[1], prev[2], prev[3])
            self._joy_state[rid] = (0.0, 0.0, 0.0, 0.0)

    def _emit_joystick(self, rid: str, end_t: int,
                       lx: float, ly: float, rx: float, ry: float):
        start_t = self._joy_start_ms.get(rid, end_t)
        dur_ms  = max(100, end_t - start_t)
        speed   = max(abs(lx), abs(ly), abs(rx))
        label   = tr("{dir}(速度{speed})",
                     dir=_move_label(lx, ly, rx), speed=f"{speed:.1f}")
        self._events[rid].append(
            (start_t, "move", 0, label,
             {"lx": lx, "ly": ly, "rx": rx, "ry": ry, "duration_ms": dur_ms}))

    def flush_joystick(self):
        """停止录制时调用，把还在进行中的摇杆动作收尾。"""
        t = self._now_ms()
        for rid in list(self._joy_state.keys()):
            s = self._joy_state[rid]
            if abs(s[0]) > 0.05 or abs(s[1]) > 0.05 or abs(s[2]) > 0.05:
                self._emit_joystick(rid, t, s[0], s[1], s[2], s[3])
                self._joy_state[rid] = (0.0, 0.0, 0.0, 0.0)

    def build_script(self, name: str = "") -> ChoreoScript:
        if not name:
            name = f"录制_{datetime.datetime.now().strftime('%m%d_%H%M%S')}"
        script  = ChoreoScript(name)
        end_ms  = self._now_ms()

        for i, robot in enumerate(self._robots):
            track  = ChoreoTrack(_slot_role_name(i, robot.robot_type),
                                 robot.robot_type)
            events = sorted(self._events.get(robot.id, []), key=lambda e: e[0])

            prev_end_ms = 0
            for ev_idx, (t, action_type, api_id, label, params) in enumerate(events):
                gap = t - prev_end_ms
                if gap > 300:
                    track.steps.append(ChoreoStep("wait", 0, tr("等待"), gap))

                if action_type == "move":
                    dur = params.get("duration_ms", 1000)
                    p   = {k: v for k, v in params.items() if k != "duration_ms"}
                    track.steps.append(ChoreoStep("move", 0, label, dur, p))
                    prev_end_ms = t + dur
                elif action_type == "sport":
                    # 机器狗没有可靠的"停动作"API，每条动作必须保留足够时长：
                    # 舞蹈1=25s，舞蹈2=40s，其他=15s（recordings 里尤其重要：
                    # 录制时用户连点可能只相隔 0.5s，但实际动作要跑完 15s）。
                    dur = get_sport_duration_ms(api_id)
                    track.steps.append(ChoreoStep("sport", api_id, label, dur))
                    prev_end_ms = t + dur
                else:
                    # G1 arm / g1_mode：用到下一事件或结束的时间，至少 500ms
                    if ev_idx + 1 < len(events):
                        dur = max(500, events[ev_idx + 1][0] - t)
                    else:
                        dur = max(500, end_ms - t)
                    track.steps.append(ChoreoStep(action_type, api_id, label, dur))
                    prev_end_ms = t + dur

            # 收尾对齐：把这条轨道补到全局结束时刻。只动一台机器人时，其它机器人整段
            # 都是等待（而不是「轮到它才从头开始」），各轨道等长、回放时序和录制时一致。
            tail = end_ms - prev_end_ms
            if tail > 300:
                track.steps.append(ChoreoStep("wait", 0, tr("等待"), tail))

            script.tracks.append(track)

        return script


# ──────────────────────────────────────────────────────────
# TimelineCanvas
# ──────────────────────────────────────────────────────────
_TH       = 48   # 每行轨道高度 px
_HEAD_H   = 28   # 标题行高度 px
_LABEL_W  = 92   # 左侧角色名列宽 px
_PX_PER_S = 40   # 每秒对应像素数（缩放级别）

_STEP_BG: Dict[str, QColor] = {
    "sport":   QColor("#2d4a3e"),
    "arm":     QColor("#1e3a5f"),
    "g1_mode": QColor("#3d2d5a"),
    "move":    QColor("#3d3a2d"),
    "wait":    QColor("#252535"),
}
_STEP_FG: Dict[str, QColor] = {
    "sport":   QColor("#a6e3a1"),
    "arm":     QColor("#89b4fa"),
    "g1_mode": QColor("#cba6f7"),
    "move":    QColor("#f9e2af"),
    "wait":    QColor("#6c7086"),
}


class TimelineCanvas(QWidget):
    """QPainter 时间线：轨道 = 行，步骤 = 彩色矩形，点击选中步骤。"""

    step_selected = pyqtSignal(int, int)   # (track_idx, step_idx)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._script:  Optional[ChoreoScript] = None
        self._sel      = (-1, -1)
        self._px_per_s = _PX_PER_S
        self.setMinimumHeight(_HEAD_H + 2 * _TH)
        self.setMouseTracking(True)

    def set_script(self, script: Optional[ChoreoScript]):
        self._script = script
        self._sel    = (-1, -1)
        self._refit()
        self.update()

    def refresh(self):
        self._refit()
        self.update()

    def set_selection(self, ti: int, si: int):
        self._sel = (ti, si)
        self.update()

    # ── internals ────────────────────────────────────────────

    def _ms2px(self, ms: int) -> int:
        return int(ms * self._px_per_s / 1000)

    def _refit(self):
        if not self._script:
            self.setMinimumSize(600, _HEAD_H + 2 * _TH)
            return
        n  = len(self._script.tracks)
        ms = self._script.total_duration_ms()
        w  = max(600, self._ms2px(ms) + _LABEL_W + 80)
        h  = _HEAD_H + max(n, 2) * _TH + 4
        self.setMinimumSize(w, h)

    # ── paint ────────────────────────────────────────────────

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor("#1e1e2e"))

        if not self._script or not self._script.tracks:
            p.setPen(QColor("#45475a"))
            p.setFont(QFont("PingFang SC", 11))
            p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter,
                       tr("暂无内容 — 请先添加角色和步骤"))
            p.end()
            return

        # ── header: time ruler ──
        p.fillRect(0, 0, w, _HEAD_H, QColor("#181825"))
        p.setPen(QColor("#585b70"))
        p.setFont(QFont("Consolas", 9))
        total_s = self._script.total_duration_ms() / 1000 + 2
        s = 0
        while s <= total_s:
            x = _LABEL_W + self._ms2px(int(s * 1000))
            if x > w:
                break
            p.drawLine(x, _HEAD_H - 6, x, _HEAD_H)
            p.drawText(x + 2, 2, 40, _HEAD_H - 2,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"{s}s")
            s += 1

        # ── track rows ──
        for ti, track in enumerate(self._script.tracks):
            y      = _HEAD_H + ti * _TH
            row_bg = QColor("#252535") if ti % 2 == 0 else QColor("#202030")
            p.fillRect(0, y, w, _TH, row_bg)

            # role label column
            p.fillRect(0, y, _LABEL_W, _TH, QColor("#1a1a2e"))
            icon = "🐕" if track.robot_type == ROBOT_TYPE_GO2 else "🤖"
            p.setPen(QColor("#cdd6f4"))
            p.setFont(QFont("PingFang SC", 10))
            p.drawText(4, y + 4, _LABEL_W - 6, _TH - 8,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"{icon} {track.role_name}")

            # steps
            t_ms = 0
            for si, step in enumerate(track.steps):
                sx = _LABEL_W + self._ms2px(t_ms)
                sw = max(6, self._ms2px(step.duration_ms))
                bg = _STEP_BG.get(step.action_type, QColor("#2a2a3e"))
                fg = _STEP_FG.get(step.action_type, QColor("#cdd6f4"))

                rect = QRect(sx, y + 5, sw - 2, _TH - 10)
                p.fillRect(rect, bg)

                if (ti, si) == self._sel:
                    p.setPen(QPen(QColor("#f5c2e7"), 2))
                else:
                    p.setPen(QPen(fg.darker(150), 1))
                p.drawRect(rect)

                if sw > 18:
                    p.setPen(fg)
                    p.setFont(QFont("PingFang SC", 9))
                    p.drawText(rect.adjusted(3, 2, -2, -2),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               step.label)

                t_ms += step.duration_ms

        # ── grid lines ──
        p.setPen(QPen(QColor("#313244"), 1))
        for ti in range(len(self._script.tracks) + 1):
            y = _HEAD_H + ti * _TH
            p.drawLine(0, y, w, y)
        p.drawLine(_LABEL_W, 0, _LABEL_W, h)

        p.end()

    def mousePressEvent(self, event):
        if not self._script:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        x, y = pos.x(), pos.y()
        if y < _HEAD_H or x < _LABEL_W:
            return
        ti = (y - _HEAD_H) // _TH
        if ti < 0 or ti >= len(self._script.tracks):
            return
        track = self._script.tracks[ti]
        t_ms  = 0
        for si, step in enumerate(track.steps):
            sx = _LABEL_W + self._ms2px(t_ms)
            sw = max(6, self._ms2px(step.duration_ms))
            if sx <= x <= sx + sw:
                self._sel = (ti, si)
                self.update()
                self.step_selected.emit(ti, si)
                return
            t_ms += step.duration_ms


# ──────────────────────────────────────────────────────────
# ChoreoEditorDialog
# ──────────────────────────────────────────────────────────
class ChoreoEditorDialog(QDialog):
    """
    编排编辑器。
    左：角色列表  |  右上：动作选择面板  |  右中：当前角色步骤列表
    底部：时间线预览（可横向滚动）
    """

    def __init__(self, manager: RobotManager, parent=None,
                 initial_script: Optional["ChoreoScript"] = None,
                 ordered_robots: Optional[List[RobotInfo]] = None,
                 get_ordered_robots: Optional[Callable[[], List[RobotInfo]]] = None):
        super().__init__(parent)
        self._mgr                = manager
        self._get_ordered_robots = get_ordered_robots
        # 新建编排：按当前设备列表（从上到下顺序）自动 seed 空轨道
        if initial_script is None:
            self._script = ChoreoScript()
            if ordered_robots:
                for i, robot in enumerate(ordered_robots):
                    self._script.tracks.append(
                        ChoreoTrack(_slot_role_name(i, robot.robot_type),
                                    robot.robot_type))
        else:
            self._script = initial_script
            # 兼容旧文件：统一 role_name 为 "#N 类型"
            renumber_tracks(self._script)
        self._sel_track_idx   = -1
        self._sel_step_idx    = -1
        self._is_dirty        = False

        self.setWindowTitle(tr("机器人编排编辑器"))
        self.resize(1150, 760)
        self.setMinimumSize(920, 620)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build_ui()
        self._refresh_track_list()
        if initial_script:
            self._name_edit.setText(initial_script.name)
        self._timeline.set_script(self._script)
        # 默认选中第 1 条轨道便于直接编辑
        if self._script.tracks:
            self._track_list.setCurrentRow(0)

    # ── UI building ───────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 顶部工具栏 ──
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("编排名称：")))
        self._name_edit = QLineEdit(self._script.name)
        self._name_edit.setFixedWidth(200)
        self._name_edit.textChanged.connect(
            lambda t: setattr(self._script, "name", t))

        load_btn   = QPushButton(tr("📂 加载"))
        append_btn = QPushButton(tr("➕ 追加编排"))
        save_btn   = QPushButton(tr("💾 保存"))
        play_btn   = QPushButton(tr("▶  播放"))
        clear_btn  = QPushButton(tr("🗑 清空步骤"))
        for b, s in ((load_btn, _BTN), (append_btn, _BTN),
                     (save_btn, _PRIMARY), (play_btn, _PRIMARY),
                     (clear_btn, _DANGER)):
            b.setStyleSheet(s)
            b.setFixedHeight(30)

        append_btn.setToolTip(tr(
            "选择另一份编排 JSON，把它的步骤按位置并联地接在当前编排末尾。\n"
            "两份编排将同时运行。轨道布局（数量 + 每个位置的类型）必须完全一致。"))
        clear_btn.setToolTip(tr("清空所有轨道的步骤，但保留轨道布局"))

        load_btn.clicked.connect(self._on_load)
        append_btn.clicked.connect(self._on_append_script)
        save_btn.clicked.connect(self._on_save)
        play_btn.clicked.connect(self._on_play)
        clear_btn.clicked.connect(self._on_clear)

        top.addWidget(self._name_edit)
        top.addSpacing(10)
        top.addWidget(load_btn)
        top.addWidget(append_btn)
        top.addWidget(save_btn)
        top.addWidget(play_btn)
        top.addSpacing(10)
        top.addWidget(clear_btn)
        top.addStretch()
        root.addLayout(top)

        # ── 主区域：左（角色列表）| 右（动作选 + 步骤列表）──
        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.setHandleWidth(3)
        h_split.addWidget(self._build_track_panel())
        h_split.addWidget(self._build_step_panel())
        h_split.setSizes([200, 950])

        # ── 底部：时间线（与主区域上下可拖拽）──
        tl_group = QGroupBox(tr("时间线预览（点击步骤可快速定位）"))
        tl_v = QVBoxLayout(tl_group)
        tl_v.setContentsMargins(4, 8, 4, 4)

        self._timeline = TimelineCanvas()
        self._timeline.step_selected.connect(self._on_timeline_click)

        tl_scroll = QScrollArea()
        tl_scroll.setWidget(self._timeline)
        tl_scroll.setWidgetResizable(False)
        tl_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tl_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tl_v.addWidget(tl_scroll)

        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setHandleWidth(4)
        v_split.addWidget(h_split)
        v_split.addWidget(tl_group)
        v_split.setSizes([680, 160])
        v_split.setCollapsible(0, False)
        v_split.setCollapsible(1, False)
        root.addWidget(v_split, 1)

    # ── 角色面板 ─────────────────────────────────────────────

    def _build_track_panel(self) -> QWidget:
        w  = QWidget()
        v  = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        grp = QGroupBox(tr("轨道（对应设备列表位置）"))
        gv  = QVBoxLayout(grp)
        gv.setSpacing(4)
        gv.setContentsMargins(6, 10, 6, 6)

        tip = QLabel(tr(
            "轨道 #N 对应左侧设备列表第 N 个机器人。\n"
            "可手动添加 Go2 / G1 轨道，也可按设备列表自动生成。"))
        tip.setStyleSheet("color:#6c7086; font-size:10px;")
        tip.setWordWrap(True)
        gv.addWidget(tip)

        add_row = QHBoxLayout()
        add_go2_btn = QPushButton("➕ Go2")
        add_g1_btn  = QPushButton("➕ G1")
        for b in (add_go2_btn, add_g1_btn):
            b.setStyleSheet(_BTN)
            b.setFixedHeight(28)
        add_go2_btn.setToolTip(tr("添加一条 Go2（机器狗）空轨道"))
        add_g1_btn.setToolTip(tr("添加一条 G1（人形）空轨道"))
        add_go2_btn.clicked.connect(lambda: self._add_track(ROBOT_TYPE_GO2))
        add_g1_btn.clicked.connect(lambda: self._add_track(ROBOT_TYPE_G1))
        add_row.addWidget(add_go2_btn)
        add_row.addWidget(add_g1_btn)
        gv.addLayout(add_row)

        btn_row = QHBoxLayout()
        del_btn = QPushButton(tr("删除选中轨道"))
        del_btn.setStyleSheet(_DANGER)
        del_btn.setFixedHeight(28)
        del_btn.setToolTip(tr(
            "从本编排移除选中的轨道并重新编号。通常用于裁掉未使用的空轨道，\n"
            "让编排文件可在更少机器人的设备列表上播放。"))
        del_btn.clicked.connect(self._del_track)

        reseed_btn = QPushButton(tr("按当前设备列表重置"))
        reseed_btn.setStyleSheet(_BTN)
        reseed_btn.setFixedHeight(28)
        reseed_btn.setToolTip(tr(
            "清空当前所有步骤，按当前设备列表（从上到下）重新 seed 轨道。"))
        reseed_btn.clicked.connect(self._reseed_from_device_list)

        btn_row.addWidget(del_btn)
        btn_row.addWidget(reseed_btn)
        gv.addLayout(btn_row)

        self._track_list = QListWidget()
        self._track_list.setFixedWidth(188)
        self._track_list.currentRowChanged.connect(self._on_track_select)
        gv.addWidget(self._track_list)

        v.addWidget(grp)
        v.addStretch()
        return w

    # ── 步骤面板（动作选择 + 步骤列表）────────────────────────

    def _build_step_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.setHandleWidth(3)
        h_split.addWidget(self._build_action_picker())
        h_split.addWidget(self._build_step_list_panel())
        h_split.setSizes([560, 340])

        v.addWidget(h_split)
        return w

    def _build_action_picker(self) -> QWidget:
        grp = QGroupBox(tr("动作选择"))
        v   = QVBoxLayout(grp)
        v.setContentsMargins(8, 12, 8, 8)
        v.setSpacing(8)

        # 时长 + 等待 同一行
        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel(tr("步骤时长：")))
        self._dur_spin = QDoubleSpinBox()
        self._dur_spin.setRange(0.2, 60.0)
        self._dur_spin.setValue(3.0)
        self._dur_spin.setSingleStep(0.5)
        self._dur_spin.setDecimals(1)
        self._dur_spin.setSuffix(" s")
        self._dur_spin.setFixedWidth(90)
        dur_row.addWidget(self._dur_spin)
        dur_row.addSpacing(16)
        wait_btn = QPushButton(tr("⏸  添加等待"))
        wait_btn.setStyleSheet(_BTN)
        wait_btn.setFixedHeight(30)
        wait_btn.setToolTip(tr("不发命令，仅等待指定时长"))
        wait_btn.clicked.connect(lambda: self._add_step(
            ChoreoStep("wait", 0,
                       tr("等待 {s}s", s=f"{self._dur_spin.value():.1f}"),
                       int(self._dur_spin.value() * 1000))))
        dur_row.addWidget(wait_btn)
        dur_row.addStretch()
        v.addLayout(dur_row)

        # 动作选项卡（移动/旋转 优先）
        self._action_tabs = QTabWidget()
        self._move_tab = self._build_move_picker()
        self._go2_tab  = self._build_go2_picker()
        self._g1_tab   = self._build_g1_picker()
        self._action_tabs.addTab(self._move_tab, tr("移动"))
        self._action_tabs.addTab(self._go2_tab,  tr("Go2 动作"))
        self._action_tabs.addTab(self._g1_tab,   tr("G1 动作"))
        v.addWidget(self._action_tabs, 1)

        return grp

    def _build_go2_picker(self) -> QWidget:
        page   = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner  = QWidget()
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(4, 4, 4, 4)
        inner_v.setSpacing(6)

        for category, actions in GO2_ACTIONS.items():
            grp  = QGroupBox(category)
            grid = QGridLayout(grp)
            grid.setSpacing(4)
            grid.setContentsMargins(4, 8, 4, 4)
            for idx, (api_id, label) in enumerate(actions):
                btn = QPushButton(tr(label))
                btn.setStyleSheet(_ACTION_BTN)
                btn.setFixedHeight(30)
                # sport 动作的时长从标准表取（舞蹈1=25s/舞蹈2=40s/其他=15s）
                # 不再用时长滑块；因为机器狗没有"停动作"API，缩短时长会在下
                # 一步真正执行前就把时间线推过，造成漂移/卡顿。
                std_dur = get_sport_duration_ms(api_id)
                btn.setToolTip(tr("该动作时长：{s} s（已固定）",
                                  s=f"{std_dur / 1000:.0f}"))
                btn.clicked.connect(
                    lambda checked, aid=api_id, lbl=label, d=std_dur: self._add_step(
                        ChoreoStep("sport", aid, lbl, d)))
                grid.addWidget(btn, idx // 4, idx % 4)
            inner_v.addWidget(grp)

        inner_v.addStretch()
        scroll.setWidget(inner)
        page_v = QVBoxLayout(page)
        page_v.setContentsMargins(0, 0, 0, 0)
        page_v.addWidget(scroll)
        return page

    def _build_g1_picker(self) -> QWidget:
        page   = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner  = QWidget()
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(4, 4, 4, 4)
        inner_v.setSpacing(6)

        # G1 手臂动作和运动模式与机器狗 sport 一样固定 5 秒，避免编排
        # 时间线和实际动作不同步（没有"停动作"API）。
        arm_grp  = QGroupBox(tr("手臂动作（固定 {n} 秒）",
                                n=G1_ACTION_FIXED_MS // 1000))
        arm_grid = QGridLayout(arm_grp)
        arm_grid.setSpacing(4)
        arm_grid.setContentsMargins(4, 8, 4, 4)
        for idx, (data, label) in enumerate(G1_ARM_ACTIONS):
            btn = QPushButton(tr(label))
            btn.setStyleSheet(_ACTION_BTN)
            btn.setFixedHeight(30)
            btn.setToolTip(tr("该动作时长：{s} s（已固定）",
                              s=f"{G1_ACTION_FIXED_MS / 1000:.0f}"))
            btn.clicked.connect(
                lambda checked, d=data, lbl=label: self._add_step(
                    ChoreoStep("arm", d, lbl, G1_ACTION_FIXED_MS)))
            arm_grid.addWidget(btn, idx // 4, idx % 4)
        inner_v.addWidget(arm_grp)

        mode_grp  = QGroupBox(tr("运动模式（固定 {n} 秒）",
                                 n=G1_ACTION_FIXED_MS // 1000))
        mode_grid = QGridLayout(mode_grp)
        mode_grid.setSpacing(4)
        mode_grid.setContentsMargins(4, 8, 4, 4)
        for idx, (code, label) in enumerate(G1_MOVE_MODES):
            btn = QPushButton(tr(label))
            btn.setStyleSheet(_ACTION_BTN)
            btn.setFixedHeight(30)
            btn.setToolTip(tr("该模式时长：{s} s（已固定）",
                              s=f"{G1_ACTION_FIXED_MS / 1000:.0f}"))
            btn.clicked.connect(
                lambda checked, c=code, lbl=label: self._add_step(
                    ChoreoStep("g1_mode", c, lbl, G1_ACTION_FIXED_MS)))
            mode_grid.addWidget(btn, 0, idx)
        inner_v.addWidget(mode_grp)
        inner_v.addStretch()

        scroll.setWidget(inner)
        page_v = QVBoxLayout(page)
        page_v.setContentsMargins(0, 0, 0, 0)
        page_v.addWidget(scroll)
        return page

    def _build_move_picker(self) -> QWidget:
        """移动动作选择器（Go2 和 G1 通用）。"""
        page = QWidget()
        v    = QVBoxLayout(page)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(8)

        tip = QLabel(tr("移动适用于 Go2 和 G1，播放时持续发送摇杆指令直到步骤结束。"))
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#585b70; font-size:11px;")
        v.addWidget(tip)

        # ── 速度滑块 ──
        spd_row = QHBoxLayout()
        spd_lbl = QLabel(tr("速度："))
        spd_lbl.setStyleSheet("color:#a6adc8; font-size:12px;")
        self._move_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._move_speed_slider.setRange(10, 100)
        self._move_speed_slider.setValue(60)
        self._move_speed_val = QLabel("0.6")
        self._move_speed_val.setStyleSheet("color:#cdd6f4; font-size:12px;")
        self._move_speed_val.setFixedWidth(28)
        self._move_speed_slider.valueChanged.connect(
            lambda v: self._move_speed_val.setText(f"{v / 100:.1f}"))
        spd_row.addWidget(spd_lbl)
        spd_row.addWidget(self._move_speed_slider, 1)
        spd_row.addWidget(self._move_speed_val)
        v.addLayout(spd_row)

        # ── 方向控制（前进/后退/左转/右转）──
        dir_grp = QGroupBox(tr("方向控制"))
        dir_grid = QGridLayout(dir_grp)
        dir_grid.setSpacing(6)
        dir_grid.setContentsMargins(8, 12, 8, 8)
        for i in range(3):
            dir_grid.setRowStretch(i, 1)
            dir_grid.setColumnStretch(i, 1)

        _MOVE_ACTIONS = [
            ("↺\n左转", 0.0,  0.0, -1.0, 0, 0),
            ("▲\n前进", 0.0,  1.0,  0.0, 0, 1),
            ("↻\n右转", 0.0,  0.0,  1.0, 0, 2),
            ("◀\n左移", -1.0, 0.0,  0.0, 1, 0),
            ("▶\n右移",  1.0, 0.0,  0.0, 1, 2),
            ("▼\n后退", 0.0, -1.0,  0.0, 2, 1),
        ]
        for label, lx, ly, rx, row, col in _MOVE_ACTIONS:
            btn = QPushButton(tr(label))
            btn.setStyleSheet(_ACTION_BTN)
            btn.setMinimumHeight(64)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding,
                              QSizePolicy.Policy.Expanding)
            btn.clicked.connect(
                lambda _c, lbl=label.replace("\n", " "), _lx=lx, _ly=ly, _rx=rx:
                    self._add_move_step(lbl, _lx, _ly, _rx))
            dir_grid.addWidget(btn, row, col)
        v.addWidget(dir_grp, 2)

        return page

    def _add_move_step(self, label: str,
                       lx: float, ly: float, rx: float):
        """创建一个 move 类型步骤（带速度参数）。"""
        speed = self._move_speed_slider.value() / 100.0
        full_label = tr("{label} (速度{speed})",
                        label=label, speed=f"{speed:.1f}")
        self._add_step(ChoreoStep(
            action_type="move",
            api_id=0,
            label=full_label,
            duration_ms=int(self._dur_spin.value() * 1000),
            parameters={"lx": lx, "ly": ly, "rx": rx, "speed": speed},
        ))

    def _build_step_list_panel(self) -> QWidget:
        grp = QGroupBox(tr("当前角色步骤列表"))
        v   = QVBoxLayout(grp)
        v.setContentsMargins(6, 10, 6, 6)
        v.setSpacing(6)

        self._step_list = QListWidget()
        self._step_list.currentRowChanged.connect(self._on_step_select)
        v.addWidget(self._step_list, 1)

        # 上/下/删除
        ctrl = QHBoxLayout()
        up_btn  = QPushButton(tr("↑ 上移"))
        dn_btn  = QPushButton(tr("↓ 下移"))
        del_btn = QPushButton(tr("✕ 删除"))
        for b in (up_btn, dn_btn):
            b.setStyleSheet(_BTN)
            b.setFixedHeight(28)
        del_btn.setStyleSheet(_DANGER)
        del_btn.setFixedHeight(28)
        up_btn.clicked.connect(self._step_up)
        dn_btn.clicked.connect(self._step_down)
        del_btn.clicked.connect(self._step_delete)
        ctrl.addWidget(up_btn)
        ctrl.addWidget(dn_btn)
        ctrl.addStretch()
        ctrl.addWidget(del_btn)
        v.addLayout(ctrl)

        # 修改时长
        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel(tr("修改时长：")))
        self._step_dur_spin = QDoubleSpinBox()
        self._step_dur_spin.setRange(0.2, 60.0)
        self._step_dur_spin.setSingleStep(0.5)
        self._step_dur_spin.setDecimals(1)
        self._step_dur_spin.setSuffix(" s")
        self._step_dur_spin.setFixedWidth(90)
        apply_btn = QPushButton(tr("应用"))
        apply_btn.setStyleSheet(_PRIMARY)
        apply_btn.setFixedHeight(28)
        apply_btn.clicked.connect(self._apply_step_dur)
        dur_row.addWidget(self._step_dur_spin)
        dur_row.addWidget(apply_btn)
        dur_row.addStretch()
        v.addLayout(dur_row)

        return grp

    # ── 轨道管理 ──────────────────────────────────────────────

    def _add_track(self, robot_type: str):
        """手动添加一条指定类型的空轨道。"""
        idx = len(self._script.tracks)
        track = ChoreoTrack(_slot_role_name(idx, robot_type), robot_type)
        self._script.tracks.append(track)
        self._is_dirty = True
        self._refresh_track_list()
        self._timeline.set_script(self._script)
        self._track_list.setCurrentRow(idx)
        type_label = "Go2" if robot_type == ROBOT_TYPE_GO2 else "G1"
        logger.info("手动添加轨道：#%d %s", idx + 1, type_label)

    def _del_track(self):
        idx = self._track_list.currentRow()
        if idx < 0 or idx >= len(self._script.tracks):
            return
        track = self._script.tracks[idx]
        if track.steps:
            ret = QMessageBox.question(
                self, tr("确认删除"),
                tr("{role} 有 {n} 个步骤，删除后这些步骤会一并丢失，确定吗？",
                   role=track.role_name, n=len(track.steps)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                return
        name = track.role_name
        self._script.tracks.pop(idx)
        renumber_tracks(self._script)
        self._is_dirty = True
        self._sel_track_idx = -1
        self._refresh_track_list()
        self._refresh_step_list()
        self._timeline.set_script(self._script)
        logger.info("删除轨道：%s", name)

    def _reseed_from_device_list(self):
        """按当前设备列表重新 seed（清空所有步骤）。"""
        robots: List[RobotInfo] = []
        if self._get_ordered_robots:
            try:
                robots = list(self._get_ordered_robots() or [])
            except Exception:
                robots = []
        if self._script.has_any_steps():
            ret = QMessageBox.question(
                self, tr("确认重置"),
                tr("将清空当前所有轨道和步骤，按设备列表重新生成空轨道，确定吗？"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                return
        self._is_dirty = True
        self._script.tracks.clear()
        for i, robot in enumerate(robots):
            self._script.tracks.append(
                ChoreoTrack(_slot_role_name(i, robot.robot_type),
                            robot.robot_type))
        self._sel_track_idx = -1
        self._sel_step_idx  = -1
        self._refresh_track_list()
        self._refresh_step_list()
        self._timeline.set_script(self._script)
        if self._script.tracks:
            self._track_list.setCurrentRow(0)

    def _refresh_track_list(self):
        prev = self._track_list.currentRow()
        self._track_list.clear()
        for t in self._script.tracks:
            icon = "🐕" if t.robot_type == ROBOT_TYPE_GO2 else "🤖"
            self._track_list.addItem(f"{icon} {t.role_name}")
        if 0 <= prev < self._track_list.count():
            self._track_list.setCurrentRow(prev)

    def _on_track_select(self, idx: int):
        self._sel_track_idx = idx
        self._sel_step_idx  = -1
        self._refresh_step_list()
        self._timeline.set_selection(idx, -1)
        self._update_action_tabs()

    def _update_action_tabs(self):
        """根据当前选中轨道的 robot_type 显示/隐藏对应的动作选项卡。"""
        tabs = self._action_tabs
        # 记住当前可见 tab 的 widget，切换后尽量保留
        cur_widget = tabs.currentWidget()

        # 先移除所有 tab（不销毁 widget）
        while tabs.count():
            tabs.removeTab(0)

        # 移动/旋转 始终显示
        tabs.addTab(self._move_tab, tr("移动"))

        if (0 <= self._sel_track_idx < len(self._script.tracks)):
            rtype = self._script.tracks[self._sel_track_idx].robot_type
            if rtype == ROBOT_TYPE_GO2:
                tabs.addTab(self._go2_tab, tr("Go2 动作"))
            else:
                tabs.addTab(self._g1_tab, tr("G1 动作"))
        else:
            # 未选中轨道时显示全部
            tabs.addTab(self._go2_tab, tr("Go2 动作"))
            tabs.addTab(self._g1_tab,  tr("G1 动作"))

        # 尝试恢复之前选中的 tab
        for i in range(tabs.count()):
            if tabs.widget(i) is cur_widget:
                tabs.setCurrentIndex(i)
                return

    # ── 步骤管理 ──────────────────────────────────────────────

    def _add_step(self, step: ChoreoStep):
        if (self._sel_track_idx < 0 or
                self._sel_track_idx >= len(self._script.tracks)):
            QMessageBox.warning(self, tr("提示"), tr("请先在左侧选择一个角色"))
            return
        track = self._script.tracks[self._sel_track_idx]
        track.steps.append(step)
        self._is_dirty = True
        self._refresh_step_list()
        self._timeline.refresh()
        self._step_list.setCurrentRow(len(track.steps) - 1)
        logger.info("添加步骤：角色=%s  动作=%s  时长=%dms",
                    track.role_name, step.label, step.duration_ms)

    def _refresh_step_list(self):
        prev = self._step_list.currentRow()
        self._step_list.clear()
        if (self._sel_track_idx < 0 or
                self._sel_track_idx >= len(self._script.tracks)):
            return
        track = self._script.tracks[self._sel_track_idx]
        for i, step in enumerate(track.steps):
            self._step_list.addItem(
                f"{i + 1}. [{step.action_type}] {step.label}"
                f"  ({step.duration_ms / 1000:.1f}s)")
        if 0 <= prev < self._step_list.count():
            self._step_list.setCurrentRow(prev)

    def _on_step_select(self, idx: int):
        self._sel_step_idx = idx
        self._timeline.set_selection(self._sel_track_idx, idx)
        if (0 <= self._sel_track_idx < len(self._script.tracks) and
                0 <= idx < len(self._script.tracks[self._sel_track_idx].steps)):
            step = self._script.tracks[self._sel_track_idx].steps[idx]
            self._step_dur_spin.setValue(step.duration_ms / 1000.0)

    def _on_timeline_click(self, ti: int, si: int):
        """时间线点击 → 同步到列表选中。"""
        self._track_list.setCurrentRow(ti)
        self._step_list.setCurrentRow(si)

    def _step_up(self):
        idx = self._step_list.currentRow()
        if (idx <= 0 or self._sel_track_idx < 0 or
                self._sel_track_idx >= len(self._script.tracks)):
            return
        steps = self._script.tracks[self._sel_track_idx].steps
        steps[idx - 1], steps[idx] = steps[idx], steps[idx - 1]
        self._is_dirty = True
        self._refresh_step_list()
        self._step_list.setCurrentRow(idx - 1)
        self._timeline.refresh()

    def _step_down(self):
        idx = self._step_list.currentRow()
        if (self._sel_track_idx < 0 or
                self._sel_track_idx >= len(self._script.tracks)):
            return
        steps = self._script.tracks[self._sel_track_idx].steps
        if idx < 0 or idx >= len(steps) - 1:
            return
        steps[idx], steps[idx + 1] = steps[idx + 1], steps[idx]
        self._is_dirty = True
        self._refresh_step_list()
        self._step_list.setCurrentRow(idx + 1)
        self._timeline.refresh()

    def _step_delete(self):
        idx = self._step_list.currentRow()
        if (idx < 0 or self._sel_track_idx < 0 or
                self._sel_track_idx >= len(self._script.tracks)):
            return
        steps = self._script.tracks[self._sel_track_idx].steps
        if 0 <= idx < len(steps):
            steps.pop(idx)
            self._is_dirty = True
            self._refresh_step_list()
            self._timeline.refresh()

    def _apply_step_dur(self):
        idx = self._step_list.currentRow()
        if (idx < 0 or self._sel_track_idx < 0 or
                self._sel_track_idx >= len(self._script.tracks)):
            return
        steps = self._script.tracks[self._sel_track_idx].steps
        if 0 <= idx < len(steps):
            step = steps[idx]
            new_dur = int(self._step_dur_spin.value() * 1000)

            # sport / arm / g1_mode 这类动作没有"停动作"API，时长由固件行为决定，
            # 缩短会导致编排时间线和实际动作不同步。
            std = get_fixed_duration_ms(step.action_type, step.api_id)
            if std is not None and new_dur < std:
                type_label = tr({
                    "sport":   "sport",
                    "arm":     "G1 手臂",
                    "g1_mode": "G1 运动模式",
                }.get(step.action_type, step.action_type))
                ret = QMessageBox.warning(
                    self, tr("时长过短"),
                    tr("该 {type} 动作的标准时长为 {std}s。\n"
                       "缩短到 {new}s 会导致动作还没跑完就开始下一步，"
                       "造成时间线与实际不同步。\n\n确定要缩短吗？",
                       type=type_label,
                       std=f"{std / 1000:.0f}",
                       new=f"{new_dur / 1000:.1f}"),
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No)
                if ret != QMessageBox.StandardButton.Yes:
                    return

            step.duration_ms = new_dur
            step.label = (
                tr("等待 {s}s", s=f"{step.duration_ms / 1000:.1f}")
                if step.action_type == "wait"
                else step.label)
            self._refresh_step_list()
            self._timeline.refresh()

    # ── 文件操作 ──────────────────────────────────────────────

    def _on_save(self):
        if not self._script.tracks:
            QMessageBox.warning(self, tr("提示"), tr("编排为空，请先添加角色和步骤"))
            return
        # 警告：整个脚本没有任何步骤 —— 保存了也无法播放
        if not self._script.has_any_steps():
            ret = QMessageBox.question(
                self, tr("编排为空"),
                tr("当前编排的所有轨道都没有任何步骤，保存后也无法播放。\n"
                   "确定要保存这个空编排吗？"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                return
        self._script.name = self._name_edit.text().strip() or tr("新编排")
        # 默认保存到 choreo_auto/ 目录；文件名需要去掉非法字符
        safe_name = _sanitize_filename(self._script.name)
        default_path = os.path.join(CHOREO_AUTO_DIR, f"{safe_name}.json")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("保存编排"), default_path,
            "Choreography JSON (*.json)")
        if not path:
            return
        try:
            self._script.save(path)
            self._is_dirty = False
            self._mgr.log_user_action("保存编排", path)
            QMessageBox.information(
                self, tr("保存成功"),
                tr("已保存：\n{path}\n\n（choreo_auto/ 目录中的文件可从主界面直接加载播放）",
                   path=path))
        except Exception as e:
            QMessageBox.critical(self, tr("保存失败"), str(e))

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("加载编排"), CHOREO_AUTO_DIR,
            "Choreography JSON (*.json)")
        if not path:
            return
        try:
            self._script = ChoreoScript.load(path)
            self._name_edit.setText(self._script.name)
            self._sel_track_idx = -1
            self._sel_step_idx  = -1
            self._refresh_track_list()
            self._refresh_step_list()
            self._timeline.set_script(self._script)
            self._is_dirty = False
            self._mgr.log_user_action("加载编排", path)
        except Exception as e:
            QMessageBox.critical(self, tr("加载失败"), str(e))

    def _on_append_script(self):
        """并行追加：选一个外部 JSON，把它的每条轨道作为新的独立轨道
        加到当前编排下方。追加后轨道数 = 原数量 + 被加编排的轨道数，
        所有轨道从 t=0 同时播放。例：2 条狗 + 另 1 条狗 = 3 条狗并行。"""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择要并行追加的编排 JSON"),
            CHOREO_AUTO_DIR, "Choreography JSON (*.json)")
        if not path:
            return
        try:
            other = ChoreoScript.load(path)
        except Exception as e:
            QMessageBox.critical(self, tr("加载失败"), str(e))
            return
        if not other.tracks:
            QMessageBox.information(
                self, tr("无可追加内容"),
                tr("待追加的编排里没有任何轨道。"))
            return

        before_n = len(self._script.tracks)
        before_total = self._script.total_duration_ms()
        append_script_parallel(self._script, other)
        self._is_dirty = True
        after_n = len(self._script.tracks)
        after_total = self._script.total_duration_ms()

        self._sel_track_idx = -1
        self._sel_step_idx = -1
        self._refresh_track_list()
        self._refresh_step_list()
        self._timeline.set_script(self._script)

        logger.info(
            "并行追加编排：%s  轨道数 %d → %d，总时长 %.1fs → %.1fs",
            path, before_n, after_n, before_total / 1000, after_total / 1000)
        QMessageBox.information(
            self, tr("追加成功"),
            tr("已把《{name}》以并行方式追加为新轨道。\n"
               "轨道数：{a} → {b}\n"
               "总时长：{ta}s  →  {tb}s\n\n"
               "⚠ 播放时设备列表必须有至少 {b} 个机器人，"
               "且每个位置的类型要匹配，否则请先在设备列表中补齐/换位。",
               name=other.name, a=before_n, b=after_n,
               ta=f"{before_total / 1000:.1f}",
               tb=f"{after_total / 1000:.1f}"))

    def _on_clear(self):
        if self._script.has_any_steps():
            if QMessageBox.question(
                    self, tr("确认清空"),
                    tr("清空将删除所有步骤（保留轨道布局），确定吗？"),
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
        # 清空步骤但保留轨道布局，与 "一个位置一条轨道" 的模型保持一致
        for t in self._script.tracks:
            t.steps.clear()
        self._is_dirty = True
        self._sel_step_idx = -1
        self._refresh_step_list()
        self._timeline.set_script(self._script)

    def _on_play(self):
        if not self._script.tracks:
            QMessageBox.warning(self, tr("提示"), tr("编排为空，请先在左侧添加机器人"))
            return
        if not self._script.has_any_steps():
            QMessageBox.warning(self, tr("提示"), tr("所有轨道都没有步骤，无法播放"))
            return
        robots: List[RobotInfo] = []
        if self._get_ordered_robots:
            try:
                robots = list(self._get_ordered_robots() or [])
            except Exception:
                robots = []
        ok, msg = check_script_compat(self._script, robots)
        if not ok:
            QMessageBox.warning(self, tr("无法播放"), msg)
            return
        dlg = ChoreoPlayerDialog(self._script, self._mgr, robots, self)
        dlg.exec()


    def _mark_dirty(self):
        self._is_dirty = True

    def _check_unsaved(self) -> bool:
        if not getattr(self, "_is_dirty", False):
            return True
        ret = QMessageBox.question(
            self, tr("未保存的更改"),
            tr("当前编排有未保存的修改，直接关闭会丢失这些内容。\n\n确定要放弃修改并关闭吗？"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return ret == QMessageBox.StandardButton.Yes

    def reject(self):
        if not self._check_unsaved():
            return
        super().reject()

    def closeEvent(self, event):
        if not self._check_unsaved():
            event.ignore()
        else:
            event.accept()

# ──────────────────────────────────────────────────────────
# ChoreoPlayerDialog — 播放器
# ──────────────────────────────────────────────────────────
class ChoreoPlayerDialog(QDialog):
    """
    编排播放器（新模型）：
      - 编排里的轨道 #N 按位置直接对应"设备列表"中第 N 个机器人。
      - 不再需要用户手动做角色分配。
      - 位置数 / 类型必须完全匹配才能开始；否则提示用户去编排库里裁剪空轨道。
    """

    def __init__(self, script: ChoreoScript,
                 manager: RobotManager,
                 ordered_robots: List[RobotInfo],
                 parent=None):
        super().__init__(parent)
        self._script         = script
        self._mgr            = manager
        # 播放时固定用这一份快照（modal 对话框期间设备列表不会变）
        self._ordered_robots = list(ordered_robots)

        # 按位置映射：第 i 条轨道 → 第 i 个机器人
        ok, msg = check_script_compat(script, self._ordered_robots)
        self._compat_ok  = ok
        self._compat_msg = msg
        if ok:
            self._role_robot_ids: List[Optional[str]] = [
                r.id for r in self._ordered_robots]
        else:
            self._role_robot_ids = [None] * len(script.tracks)

        # 播放状态
        self._playing          = False
        self._start_t          = 0.0
        self._events:     List[Tuple[int, int, ChoreoStep]] = []
        self._next_evt         = 0
        self._total_ms         = 0
        # 持续移动：{track_idx: (robot_id, lx, ly, rx, end_ms)} — 在 _tick 中持续发送
        self._active_moves: Dict[int, Tuple[str, float, float, float, int]] = {}
        # 每条轨道上一次发送摇杆的时刻（monotonic s），用于限频到 ~80ms
        self._last_joy_sent:  Dict[int, float] = {}
        # 每个轨道上一步的类型，用于检测 move→sport 过渡
        self._prev_step_type: Dict[int, str] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(20)   # 20ms tick，提高播放时间精度
        self._timer.timeout.connect(self._tick)

        self.setWindowTitle(tr("编排播放器"))
        self.resize(720, 520)
        self.setMinimumSize(600, 420)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build_ui()
        if not ok:
            self._log(tr("⚠ 布局不匹配：{msg}", msg=msg), "#f38ba8")

    # ── UI ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 剧本信息
        total_ms = self._script.total_duration_ms()
        info = QLabel(tr(
            "剧本：{name}  |  位置数：{n}  |  总时长：{s} 秒",
            name=self._script.name,
            n=len(self._script.tracks),
            s=f"{total_ms / 1000:.1f}"))
        info.setStyleSheet("color: #89b4fa; font-size: 12px;")
        root.addWidget(info)

        # 位置映射表（只读）
        map_grp  = QGroupBox(tr(
            "位置映射  —  编排轨道 #N  →  设备列表第 N 个机器人"))
        map_grid = QGridLayout(map_grp)
        map_grid.setSpacing(6)
        map_grid.setContentsMargins(10, 12, 10, 8)

        n_rows = max(len(self._script.tracks), len(self._ordered_robots))
        for ti in range(n_rows):
            track = (self._script.tracks[ti]
                     if ti < len(self._script.tracks) else None)
            robot = (self._ordered_robots[ti]
                     if ti < len(self._ordered_robots) else None)

            if track is not None:
                icon = "🐕" if track.robot_type == ROBOT_TYPE_GO2 else "🤖"
                left = (f"{icon}  {track.role_name}  "
                        f"[{track.robot_type.upper()}]  "
                        + tr("{n} 步  →", n=len(track.steps)))
            else:
                left = tr("（编排无第 {i} 条轨道）  →", i=ti + 1)

            if robot is not None and track is not None:
                match = (robot.robot_type == track.robot_type)
                status = (tr("已连接") if robot.status == STATUS_CONNECTED
                          else tr("未连接"))
                right = (tr("第 {i} 个：", i=ti + 1) + f"{robot.name}  "
                         f"[{robot.robot_type.upper()}]  ({status})")
                color = ("#a6e3a1" if match and robot.status == STATUS_CONNECTED
                         else ("#f9e2af" if match else "#f38ba8"))
            elif robot is not None:
                right = (tr("第 {i} 个：", i=ti + 1) + f"{robot.name}  "
                         f"[{robot.robot_type.upper()}]  "
                         + tr("（编排无此轨道）"))
                color = "#f38ba8"
            else:
                right = tr("（设备列表无第 {i} 个机器人）", i=ti + 1)
                color = "#f38ba8"

            l_lbl = QLabel(left)
            l_lbl.setStyleSheet("color:#cdd6f4;")
            r_lbl = QLabel(right)
            r_lbl.setStyleSheet(f"color:{color};")
            map_grid.addWidget(l_lbl, ti, 0)
            map_grid.addWidget(r_lbl, ti, 1)

        if not self._compat_ok:
            warn = QLabel(f"⚠ {self._compat_msg}")
            warn.setStyleSheet(
                "color:#f38ba8; font-size:11px; padding-top:6px;")
            warn.setWordWrap(True)
            map_grid.addWidget(warn, n_rows, 0, 1, 2)

        root.addWidget(map_grp)

        # 进度条
        prog_grp = QGroupBox(tr("播放进度"))
        prog_v   = QVBoxLayout(prog_grp)
        prog_v.setContentsMargins(8, 8, 8, 8)
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setFixedHeight(22)
        self._progress.setFormat("0.0s / 0.0s")
        prog_v.addWidget(self._progress)
        root.addWidget(prog_grp)

        # 控制按钮
        ctrl = QHBoxLayout()
        self._play_btn  = QPushButton(tr("▶  开始播放"))
        self._stop_btn  = QPushButton(tr("⏹  停止"))
        self._estop_btn = QPushButton(tr("🚨  全体紧急停止"))

        self._play_btn.setStyleSheet(_PRIMARY)
        self._stop_btn.setStyleSheet(_BTN)
        self._estop_btn.setStyleSheet(_DANGER)
        for b in (self._play_btn, self._stop_btn, self._estop_btn):
            b.setFixedHeight(38)

        self._stop_btn.setEnabled(False)
        self._play_btn.setEnabled(self._compat_ok)
        if not self._compat_ok:
            self._play_btn.setToolTip(tr(
                "编排布局与当前设备列表不一致，无法开始播放。\n"
                "请在「编排库」打开本编排，在编辑器中删除多余的空轨道后保存再试。"))
        self._play_btn.clicked.connect(self._on_play)
        self._stop_btn.clicked.connect(self._on_stop)
        self._estop_btn.clicked.connect(self._on_emergency_stop)

        ctrl.addWidget(self._play_btn)
        ctrl.addWidget(self._stop_btn)
        ctrl.addStretch()
        ctrl.addWidget(self._estop_btn)
        root.addLayout(ctrl)

        # 执行日志
        log_grp = QGroupBox(tr("执行日志"))
        log_v   = QVBoxLayout(log_grp)
        log_v.setContentsMargins(4, 8, 4, 4)
        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFixedHeight(130)
        log_v.addWidget(self._log_edit)
        root.addWidget(log_grp)

    # ── 播放逻辑 ─────────────────────────────────────────────

    def _build_event_list(self) -> bool:
        """构建排序好的事件列表：[(abs_time_ms, track_idx, step)]。"""
        if not self._compat_ok:
            return False
        self._events = []
        for ti, track in enumerate(self._script.tracks):
            t_ms = 0
            for step in track.steps:
                self._events.append((t_ms, ti, step))
                t_ms += step.duration_ms
        self._events.sort(key=lambda e: e[0])
        self._total_ms = self._script.total_duration_ms()
        return True

    def _on_play(self):
        if self._playing:
            return
        if not self._compat_ok:
            QMessageBox.warning(self, tr("无法播放"), self._compat_msg)
            return
        if not self._build_event_list() or not self._events:
            QMessageBox.warning(self, tr("提示"), tr("编排中所有轨道都没有步骤。"))
            return

        self._playing  = True
        self._next_evt = 0
        self._start_t  = _time.monotonic()
        self._finish_called = False
        self._prev_step_type.clear()
        self._last_joy_sent.clear()

        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

        self._progress.setValue(0)
        self._progress.setFormat(f"0.0s / {self._total_ms / 1000:.1f}s")
        self._log(tr("▶ 开始播放"), "#a6e3a1")
        self._mgr.log_user_action("编排开始播放", self._script.name)
        
        # 编排播放前：设置所有 Go2 为连续行走模式，支持摇杆控制
        self._setup_continuous_gait()
        
        # 编排播放期间打开 verbose 日志，便于排查 "只有一只狗动" 之类的并行问题
        try:
            set_playback_verbose_logging(True)
        except Exception:
            pass
        self._timer.start()

    def _on_stop(self):
        if not self._playing:
            return
        self._playing = False
        self._timer.stop()
        self._stop_all_moves()
        self._stop_sport_commands()

        self._play_btn.setEnabled(self._compat_ok)
        self._stop_btn.setEnabled(False)

        try:
            set_playback_verbose_logging(False)
        except Exception:
            pass
        self._log(tr("⏹ 播放停止"), "#f9e2af")
        self._mgr.log_user_action("编排停止播放", self._script.name)

    def _stop_sport_commands(self):
        """编排结束/停止时的收尾指令：StopMove + 切 normal + RecoveryStand，
        强制中断舞蹈动画、恢复摇杆控制。StopMove 单独发不够，因为 Go2
        固件下它只能停移动而无法中断已经开始的舞蹈；必须配合模式切换。"""
        valid_ids = [rid for rid in self._role_robot_ids if rid is not None]
        if not valid_ids:
            return
        try:
            self._mgr.stop_choreography(valid_ids)
        except Exception as e:
            logger.warning("[choreo] 收尾停止失败: %s", e)

    def _on_emergency_stop(self):
        """停止播放并向所有机器人发送紧急停止。

        Go2 部分安全，立即执行；G1 急停是切阻尼，走跑中被打断会直接摔倒，风险和
        Go2 不是一个量级，弹二次确认，用户确认后才对 G1 发（不能像以前那样一个
        emergency_stop_all 把两种机器人混在一起无脑发出去）。
        """
        if self._playing:
            self._playing = False
            self._timer.stop()
            self._stop_all_moves()
            self._play_btn.setEnabled(self._compat_ok)
            self._stop_btn.setEnabled(False)

        valid_ids = [rid for rid in self._role_robot_ids if rid is not None]
        self._mgr.emergency_stop_go2(valid_ids)

        g1_ids = self._mgr.g1_ids_among(valid_ids)
        if g1_ids:
            g1_names = [r.name for rid in g1_ids if (r := self._mgr.get_robot(rid))]
            ret = QMessageBox.warning(
                self, tr("⚠️ 确认对 G1 急停？"),
                tr("G1 急停会立即切阻尼、腿部瞬间卸力——如果这时候正在走跑，会直接摔倒。\n"
                   "这个场景没有实测验证过安全性，确定要继续吗？\n\n"
                   "目标：{names}", names="、".join(g1_names)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret == QMessageBox.StandardButton.Yes:
                self._mgr.emergency_stop_g1(g1_ids)

        try:
            set_playback_verbose_logging(False)
        except Exception:
            pass
        self._log(tr("🚨 全体紧急停止！"), "#f38ba8")
        self._mgr.log_user_action("编排紧急停止")

    def _tick(self):
        """20ms 定时器：按绝对时间触发各步骤。"""
        if not self._playing:
            return

        elapsed_ms = int((_time.monotonic() - self._start_t) * 1000)

        # 进度条更新
        if self._total_ms > 0:
            self._progress.setValue(
                min(1000, int(elapsed_ms * 1000 / self._total_ms)))
            self._progress.setFormat(
                f"{elapsed_ms / 1000:.1f}s / {self._total_ms / 1000:.1f}s")

        # 触发到期事件
        while self._next_evt < len(self._events):
            ev_ms, ti, step = self._events[self._next_evt]
            if elapsed_ms >= ev_ms:
                self._fire_step(ti, step, ev_ms)
                self._next_evt += 1
            else:
                break

        # 持续移动：限频到 ~80ms 发一次（20ms tick 时 4 次才发 1 次）；
        # 避免把 rt/wirelesscontroller 刷爆、压垮 asyncio 任务队列
        now_s = _time.monotonic()
        for ti, (robot_id, lx, ly, rx, end_ms) in list(self._active_moves.items()):
            if elapsed_ms >= end_ms:
                self._stop_track_move(ti)
                continue
            last = self._last_joy_sent.get(ti, 0.0)
            if now_s - last >= 0.08:       # 80ms 最小间隔
                self._mgr.send_joystick([robot_id], lx, ly, rx)
                self._last_joy_sent[ti] = now_s

        # 全部触发且时间到 → 完成
        if (self._next_evt >= len(self._events) and
                elapsed_ms >= self._total_ms):
            self._on_finish()

    def _fire_step(self, track_idx: int, step: ChoreoStep, start_ms: int = 0):
        """发送单条步骤指令到对应机器人。"""
        # 无论什么新步骤，先停止该轨道正在进行的持续移动
        self._stop_track_move(track_idx)

        robot_id = self._role_robot_ids[track_idx]
        if robot_id is None:
            return
        robot = self._mgr.get_robot(robot_id)
        if not robot or robot.status != STATUS_CONNECTED:
            track = self._script.tracks[track_idx]
            self._log(
                tr("⚠ {role}：机器人未连接，跳过 [{label}]",
                   role=track.role_name, label=step.label),
                "#f9e2af")
            return
        
        # 在执行移动步骤前，确保该机器人处于可行走姿态
        if step.action_type == "move" and robot.is_go2:
            if robot.needs_recovery:
                self._mgr.send_sport_cmd_fire_and_forget(
                    [robot_id], SPORT_CMD["RecoveryStand"])
            self._mgr.send_sport_cmd_fire_and_forget(
                [robot_id], SPORT_CMD["ContinuousGait"])

        track = self._script.tracks[track_idx]
        prev_type = self._prev_step_type.get(track_idx, "")
        self._prev_step_type[track_idx] = step.action_type

        self._log(
            f"▶ {track.role_name} [{robot.name}]：{step.label}",
            "#89b4fa")

        if step.action_type == "wait":
            pass   # 纯等待，不发指令

        elif step.action_type == "sport":
            # 如果上一步是 move，机器人需要过渡时间才能执行 sport 指令
            # 延迟 300ms 发送，避免 401001 拒绝
            delay = 300 if prev_type == "move" else 0
            self._schedule_sport_cmd(robot_id, step, delay)

        elif step.action_type == "arm":
            self._mgr.send_g1_arm_action([robot_id], step.api_id)
        elif step.action_type == "g1_mode":
            self._mgr.send_g1_switch_mode([robot_id], step.api_id)
        elif step.action_type == "move":
            p   = step.parameters or {}
            lx  = p.get("lx", 0.0)
            ly  = p.get("ly", 0.0)
            rx  = p.get("rx", 0.0)
            # 编辑器创建的步骤有 "speed" 键（lx/ly/rx 是原始方向值，需要乘速度）
            # 录制创建的步骤无 "speed" 键（lx/ly/rx 已含速度缩放，直接使用）
            if "speed" in p:
                spd = p["speed"]
                lx *= spd
                ly *= spd
                rx *= spd
            # 注册持续移动，在 _tick 中每帧发送摇杆指令（到 end_ms 自动停止）
            end_ms = start_ms + step.duration_ms
            self._active_moves[track_idx] = (robot_id, lx, ly, rx, end_ms)
            # 立即发送一次，并记录时间，避免下一 tick 立刻重发造成抖动
            # 注：ContinuousGait 模式已在 _fire_step 开头设置，这里直接发摇杆
            self._mgr.send_joystick([robot_id], lx, ly, rx)
            self._last_joy_sent[track_idx] = _time.monotonic()

    def _schedule_sport_cmd(self, robot_id: str, step: ChoreoStep, delay_ms: int):
        """发送 sport 指令，可选延迟。使用 fire-and-forget 不等待回复。

        注意：不做应用层重发。WebRTC datachannel 走 SCTP（可靠传输），
        不需要额外重发；对 Dance1 等长动作重发会导致机器狗重新从头开始跳。
        """
        def _do_send():
            if not getattr(self, "_playing", False):
                return
            try:
                self._mgr.send_sport_cmd_fire_and_forget(
                    [robot_id], step.api_id,
                    step.parameters if step.parameters else None)
            except RuntimeError:
                pass

        if delay_ms > 0:
            QTimer.singleShot(delay_ms, _do_send)
        else:
            _do_send()

    def _stop_track_move(self, track_idx: int):
        """停止某轨道的持续移动并发送摇杆归零。"""
        entry = self._active_moves.pop(track_idx, None)
        if entry:
            robot_id = entry[0]
            self._mgr.send_joystick([robot_id], 0.0, 0.0, 0.0)

    def _setup_continuous_gait(self):
        """编排播放前，设置所有 Go2 为连续行走模式。需要恢复的先 RecoveryStand。"""
        valid_ids = [rid for rid in self._role_robot_ids if rid is not None]
        if not valid_ids:
            return
        # 需要恢复行走的 Go2 先发 RecoveryStand
        recovery_ids = []
        for rid in valid_ids:
            robot = self._mgr.get_robot(rid)
            if robot and robot.is_go2 and robot.needs_recovery:
                recovery_ids.append(rid)
        if recovery_ids:
            self._mgr.send_sport_cmd_fire_and_forget(
                recovery_ids, SPORT_CMD["RecoveryStand"])
        # 给所有连接的 Go2 发送 ContinuousGait 命令（立即生效，不等待）
        self._mgr.send_sport_cmd_fire_and_forget(
            valid_ids, SPORT_CMD["ContinuousGait"])

    def _stop_all_moves(self):
        """停止所有轨道的持续移动。"""
        for ti in list(self._active_moves):
            self._stop_track_move(ti)

    def _on_finish(self):
        # 修复P2：添加finished flag防止多次调用
        if getattr(self, '_finish_called', False):
            return
        self._finish_called = True

        self._playing = False
        self._timer.stop()
        self._stop_all_moves()
        # 编排时间线走完后必须主动发收尾指令：
        # 1) Go2 没有可靠的"停动作"API，舞蹈会一直循环（见 logs/app.log 的
        #    "跳个不停"问题），只有切 MOTION_SWITCHER 才能强制中断；
        # 2) 收尾后 RecoveryStand 让狗回到可控状态，避免下次摇杆无响应。
        self._stop_sport_commands()
        self._progress.setValue(1000)
        self._play_btn.setEnabled(self._compat_ok)
        self._stop_btn.setEnabled(False)
        try:
            set_playback_verbose_logging(False)
        except Exception:
            pass
        self._log(tr("✅ 编排播放完成，已发送收尾停止+恢复站立"), "#a6e3a1")
        self._mgr.log_user_action("编排播放完成", self._script.name)

    def _log(self, msg: str, color: str = "#a6adc8"):
        ts = _time.strftime("%H:%M:%S")
        self._log_edit.append(
            f'<span style="color:{color};">[{ts}]  {msg}</span>')
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event):
        try:
            if self._playing:
                self._on_stop()
        finally:
            # 任何异常路径都必须关闭 verbose 日志，避免把 app.log 刷爆
            try:
                set_playback_verbose_logging(False)
            except Exception:
                pass
            # 停掉定时器 & 清空状态，避免对话框销毁后 _tick 还在触发
            try:
                self._timer.stop()
            except Exception:
                pass
            self._active_moves.clear()
            self._last_joy_sent.clear()
        event.accept()


# ──────────────────────────────────────────────────────────
# ChoreoLibraryDialog — 主界面"加载编排"按钮打开
# ──────────────────────────────────────────────────────────
class ChoreoLibraryDialog(QDialog):
    """
    扫描 choreo_auto/ 目录下所有 .json 编排文件，
    严格按"设备列表位置"比对兼容性（长度 + 每个位置的机器人类型）。
    只有完全匹配才能直接播放；否则用户需先在编辑器里裁剪空白轨道。
    """

    def __init__(self, manager: RobotManager, parent=None,
                 get_ordered_robots: Optional[Callable[[], List[RobotInfo]]] = None):
        super().__init__(parent)
        self._mgr = manager
        self._get_ordered_robots = get_ordered_robots
        self.setWindowTitle(tr("编排库  —  choreo_auto/"))
        self.resize(760, 500)
        self.setMinimumSize(640, 380)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build_ui()
        self._scan()

    def _current_ordered_robots(self) -> List[RobotInfo]:
        if self._get_ordered_robots is None:
            return []
        try:
            return list(self._get_ordered_robots() or [])
        except Exception:
            return []

    # ── UI ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 目录提示
        dir_lbl = QLabel(tr("📂  扫描目录：{path}", path=CHOREO_AUTO_DIR))
        dir_lbl.setStyleSheet("color: #585b70; font-size: 11px;")
        root.addWidget(dir_lbl)

        # 当前连接状态
        self._conn_lbl = QLabel("")
        self._conn_lbl.setStyleSheet("color: #89b4fa; font-size: 12px;")
        root.addWidget(self._conn_lbl)

        # 编排列表
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet("""
            QListWidget { background: #11111b; alternate-background-color: #181825;
                          border: 1px solid #313244; }
            QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #252535; }
            QListWidget::item:selected { background: #313244; }
        """)
        self._list.itemDoubleClicked.connect(self._on_play)
        root.addWidget(self._list, 1)

        # 控制按钮
        ctrl = QHBoxLayout()
        refresh_btn = QPushButton(tr("↺ 刷新"))
        self._play_btn  = QPushButton(tr("▶  播放选中编排"))
        self._edit_btn  = QPushButton(tr("✏ 在编辑器中打开"))
        open_dir_btn = QPushButton(tr("📂 打开目录"))

        for b, s in ((refresh_btn, _BTN), (self._play_btn, _PRIMARY),
                     (self._edit_btn, _BTN), (open_dir_btn, _BTN)):
            b.setStyleSheet(s)
            b.setFixedHeight(34)

        self._play_btn.setEnabled(False)
        self._edit_btn.setEnabled(False)

        refresh_btn.clicked.connect(self._scan)
        self._play_btn.clicked.connect(self._on_play)
        self._edit_btn.clicked.connect(self._on_edit)
        open_dir_btn.clicked.connect(self._open_dir)
        self._list.currentRowChanged.connect(self._on_select)

        ctrl.addWidget(refresh_btn)
        ctrl.addWidget(self._play_btn)
        ctrl.addWidget(self._edit_btn)
        ctrl.addStretch()
        ctrl.addWidget(open_dir_btn)
        root.addLayout(ctrl)

    # ── 扫描 ─────────────────────────────────────────────────

    def _scan(self):
        """扫描 choreo_auto/ 目录，加载所有 .json 并按设备列表位置严格比对。"""
        ordered = self._current_ordered_robots()
        if ordered:
            layout_parts = []
            for i, r in enumerate(ordered):
                tag = "Go2" if r.robot_type == ROBOT_TYPE_GO2 else "G1"
                layout_parts.append(f"#{i + 1}{tag}")
            self._conn_lbl.setText(
                tr("当前设备列表（按顺序）：{n} 个 — ", n=len(ordered))
                + "  ".join(layout_parts))
        else:
            self._conn_lbl.setText(tr("当前设备列表为空"))

        self._list.clear()
        self._scripts: List[Optional[ChoreoScript]] = []

        json_files = sorted(Path(CHOREO_AUTO_DIR).glob("*.json"))
        if not json_files:
            item = QListWidgetItem(tr("  （choreo_auto/ 目录为空，请先在编排编辑器中保存剧本）"))
            item.setForeground(QColor("#585b70"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
            self._scripts.append(None)
            return

        for fpath in json_files:
            try:
                script = ChoreoScript.load(str(fpath))
            except Exception as e:
                item = QListWidgetItem(tr("  ⚠ {name}  （解析失败：{err}）",
                                          name=fpath.name, err=e))
                item.setForeground(QColor("#f38ba8"))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self._list.addItem(item)
                self._scripts.append(None)
                continue

            total_s = script.total_duration_ms() / 1000
            ok, why = check_script_compat(script, ordered)
            compat = tr("✅ 可播放") if ok else tr("⚠ 布局不匹配")
            compat_color = "#a6e3a1" if ok else "#f9e2af"

            text = (
                f"{compat}   {script.name}"
                f"   |   {tr('要求：')}{script.describe_layout()}"
                f"   |   {total_s:.1f}s   |   {fpath.name}")
            item = QListWidgetItem(f"  {text}")
            item.setForeground(QColor(compat_color))
            item.setData(Qt.ItemDataRole.UserRole, ok)
            if not ok and why:
                item.setToolTip(why)
            self._list.addItem(item)
            self._scripts.append(script)

    def _on_select(self, row: int):
        valid = (0 <= row < len(self._scripts) and
                 self._scripts[row] is not None)
        ok = valid and bool(self._list.item(row) and
                            self._list.item(row).data(Qt.ItemDataRole.UserRole))
        self._play_btn.setEnabled(ok)
        self._edit_btn.setEnabled(valid)

    # ── 操作 ─────────────────────────────────────────────────

    def _current_script(self) -> Optional[ChoreoScript]:
        row = self._list.currentRow()
        if 0 <= row < len(self._scripts):
            return self._scripts[row]
        return None

    def _on_play(self):
        script = self._current_script()
        if not script:
            return
        ordered = self._current_ordered_robots()
        ok, msg = check_script_compat(script, ordered)
        if not ok:
            QMessageBox.warning(self, tr("无法播放"), msg)
            return
        self._mgr.log_user_action("从库播放编排", script.name)
        dlg = ChoreoPlayerDialog(script, self._mgr, ordered, self)
        dlg.exec()

    def _on_edit(self):
        script = self._current_script()
        if not script:
            return
        dlg = ChoreoEditorDialog(
            self._mgr, self,
            initial_script=script,
            get_ordered_robots=self._get_ordered_robots)
        self._mgr.log_user_action("从库编辑编排", script.name)
        dlg.exec()
        # 编辑完后刷新库列表（可能保存了新版本）
        self._scan()

    def _open_dir(self):
        import subprocess, sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", CHOREO_AUTO_DIR])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", CHOREO_AUTO_DIR])
        else:
            subprocess.Popen(["xdg-open", CHOREO_AUTO_DIR])
