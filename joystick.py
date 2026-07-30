"""
joystick.py — 移动控制控件

MovementButtonPanel : 方向按钮 + 旋转按钮，按住持续发送（键盘/鼠标都支持）
KeyboardMoveFilter  : 安装在主窗口的键盘事件过滤器，把按键路由给 MovementButtonPanel

键位说明：
  W / ↑        前进
  S / ↓        后退
  A / ← / Q    左转
  D / → / E    右转
  Z            左移（侧走）
  X            右移（侧走）
  Space        紧急停止
"""

from __future__ import annotations

from typing import Callable, Optional, Set

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import QColor, QFont, QKeyEvent

from i18n import tr
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget, QFrame
)


# ──────────────────────────────────────────────────────────
# 按钮样式
# ──────────────────────────────────────────────────────────
_BTN_IDLE = """
    QPushButton {{
        background: #2a2a3e;
        color: {fg};
        border: 1px solid #45475a;
        border-radius: 6px;
        font-size: {fs}px;
        font-weight: bold;
        padding: 0px;
    }}
    QPushButton:hover {{ background: #35354f; border-color: #89b4fa; }}
"""

_BTN_ACTIVE = """
    QPushButton {{
        background: {bg};
        color: #1e1e2e;
        border: 1px solid {bg};
        border-radius: 6px;
        font-size: {fs}px;
        font-weight: bold;
        padding: 0px;
    }}
"""

_STOP_IDLE = """
    QPushButton {
        background: #2a1a1a;
        color: #f38ba8;
        border: 1px solid #7d2a2a;
        border-radius: 6px;
        font-size: 13px;
        font-weight: bold;
    }
    QPushButton:hover { background: #3d2020; border-color: #f38ba8; }
"""

_STOP_ACTIVE = """
    QPushButton {
        background: #f38ba8;
        color: #1e1e2e;
        border: 1px solid #f38ba8;
        border-radius: 6px;
        font-size: 13px;
        font-weight: bold;
    }
"""

# 方向按钮颜色 (active)
_FWD_COLOR   = "#a6e3a1"   # 绿
_SIDE_COLOR  = "#89b4fa"   # 蓝
_BACK_COLOR  = "#f9e2af"   # 黄
_TURN_COLOR  = "#cba6f7"   # 紫


def _make_dir_btn(label: str, key_hint: str,
                  active_bg: str, font_size: int = 18) -> QPushButton:
    btn = QPushButton(f"{label}\n{key_hint}")
    btn.setStyleSheet(_BTN_IDLE.format(fg="#cdd6f4", fs=font_size))
    btn._active_style = _BTN_ACTIVE.format(bg=active_bg, fs=font_size)
    btn._idle_style   = _BTN_IDLE.format(fg="#cdd6f4", fs=font_size)
    btn.setMinimumSize(72, 64)
    btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    btn.setAutoRepeat(False)
    return btn


# ──────────────────────────────────────────────────────────
# MovementButtonPanel
# ──────────────────────────────────────────────────────────
class MovementButtonPanel(QWidget):
    """
    移动控制按钮面板。
    按住按钮（或键盘）→ 80ms 定时器持续发出 joystickChanged。
    松开 → 停止发送（归零）。
    """

    joystickChanged = pyqtSignal(float, float, float, float)  # lx, ly, rx, ry
    emergencyStop   = pyqtSignal()                            # 立即停止信号

    # 键名到 (lx, ly, rx) 增量的映射
    _KEY_MAP = {
        "forward":     ( 0.0,  1.0,  0.0),
        "back":        ( 0.0, -1.0,  0.0),
        "turn_left":   ( 0.0,  0.0, -1.0),
        "turn_right":  ( 0.0,  0.0,  1.0),
        "strafe_left": (-1.0,  0.0,  0.0),
        "strafe_right":( 1.0,  0.0,  0.0),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._held: Set[str] = set()
        self._speed = 0.6

        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._emit_values)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # ── 速度滑块 ──
        speed_row = QHBoxLayout()
        speed_lbl = QLabel(tr("速度："))
        speed_lbl.setStyleSheet("color:#a6adc8; font-size:12px;")
        speed_lbl.setFixedWidth(36)
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(10, 100)
        self._speed_slider.setValue(60)
        self._speed_slider.setFixedWidth(140)
        self._speed_val_lbl = QLabel("0.6")
        self._speed_val_lbl.setStyleSheet("color:#cdd6f4; font-size:12px;")
        self._speed_val_lbl.setFixedWidth(28)
        self._speed_slider.valueChanged.connect(self._on_speed_change)

        speed_row.addWidget(speed_lbl)
        speed_row.addWidget(self._speed_slider)
        speed_row.addWidget(self._speed_val_lbl)
        speed_row.addStretch()

        hint = QLabel(tr("  W/S = 前后  |  A/D/Q/E = 左右转  |  Z/X = 左右走  |  Space = 停止"))
        hint.setStyleSheet("color:#585b70; font-size:11px;")
        speed_row.addWidget(hint)
        root.addLayout(speed_row)

        # ── 方向按钮网格 ──
        # 布局:
        #   [左转 A/Q]  [前进 W↑]  [右转 D/E]
        #   [左移 Z]    [停止]     [右移 X]
        #   [空]        [后退 S↓]  [空]
        grid = QGridLayout()
        grid.setSpacing(5)

        self._btn_fwd          = _make_dir_btn("▲",  "W / ↑", _FWD_COLOR)
        self._btn_back         = _make_dir_btn("▼",  "S / ↓", _BACK_COLOR)
        self._btn_stop         = QPushButton(tr("⬛\n停止\nSpace"))
        self._btn_turn_left    = _make_dir_btn("↺",  tr("A / ← 左转"), _TURN_COLOR, 14)
        self._btn_turn_right   = _make_dir_btn("↻",  tr("D / → 右转"), _TURN_COLOR, 14)
        self._btn_strafe_left  = _make_dir_btn("◀",  tr("Z 左移"),     _SIDE_COLOR, 14)
        self._btn_strafe_right = _make_dir_btn("▶",  tr("X 右移"),     _SIDE_COLOR, 14)

        self._btn_stop.setStyleSheet(_STOP_IDLE)
        self._btn_stop.setMinimumSize(72, 64)
        self._btn_stop.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 行 0: [左转] [前进] [右转]
        grid.addWidget(self._btn_turn_left,  0, 0)
        grid.addWidget(self._btn_fwd,        0, 1)
        grid.addWidget(self._btn_turn_right, 0, 2)
        # 行 1: [左移] [停止] [右移]
        grid.addWidget(self._btn_strafe_left,  1, 0)
        grid.addWidget(self._btn_stop,         1, 1)
        grid.addWidget(self._btn_strafe_right, 1, 2)
        # 行 2: [空] [后退] [空]
        grid.addWidget(self._btn_back, 2, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        root.addLayout(grid)

        # ── 按钮信号绑定 ──
        self._bind_dir_btn(self._btn_fwd,          "forward")
        self._bind_dir_btn(self._btn_back,         "back")
        self._bind_dir_btn(self._btn_turn_left,    "turn_left")
        self._bind_dir_btn(self._btn_turn_right,   "turn_right")
        self._bind_dir_btn(self._btn_strafe_left,  "strafe_left")
        self._bind_dir_btn(self._btn_strafe_right, "strafe_right")
        self._btn_stop.clicked.connect(self.emergency_stop)

        # 保存按钮引用方便更新样式
        self._btn_map = {
            "forward":      self._btn_fwd,
            "back":         self._btn_back,
            "turn_left":    self._btn_turn_left,
            "turn_right":   self._btn_turn_right,
            "strafe_left":  self._btn_strafe_left,
            "strafe_right": self._btn_strafe_right,
        }

    def _on_speed_change(self, value: int):
        self._speed = value / 100.0
        self._speed_val_lbl.setText(f"{self._speed:.1f}")

    def _bind_dir_btn(self, btn: QPushButton, key: str):
        btn.pressed.connect(lambda: self.key_press(key))
        btn.released.connect(lambda: self.key_release(key))

    # ── 公开：键盘过滤器调用 ──

    def key_press(self, key: str):
        if key in self._held:
            return
        self._held.add(key)
        self._update_btn_style(key, True)
        if not self._timer.isActive():
            self._timer.start()
        self._emit_values()

    def key_release(self, key: str):
        self._held.discard(key)
        self._update_btn_style(key, False)
        self._emit_values()
        if not self._held:
            self._timer.stop()

    def release_all(self):
        """释放所有按住的键（窗口失焦 / 面板切换时调用，防止机器人继续移动）。"""
        if not self._held:
            return
        self._held.clear()
        self._timer.stop()
        for key in self._btn_map:
            self._update_btn_style(key, False)
        self.joystickChanged.emit(0.0, 0.0, 0.0, 0.0)

    def emergency_stop(self):
        self._held.clear()
        self._timer.stop()
        for key in self._btn_map:
            self._update_btn_style(key, False)
        self._btn_stop.setStyleSheet(_STOP_ACTIVE)
        # 先发送零值摇杆
        self.joystickChanged.emit(0.0, 0.0, 0.0, 0.0)
        # 再发出紧急停止信号（让 ControlPanel 调用后端立即停止）
        self.emergencyStop.emit()
        # 短暂高亮后恢复
        QTimer.singleShot(200, lambda: self._btn_stop.setStyleSheet(_STOP_IDLE))

    def _update_btn_style(self, key: str, active: bool):
        btn = self._btn_map.get(key)
        if not btn:
            return
        if active:
            btn.setStyleSheet(getattr(btn, "_active_style",
                                      btn.styleSheet()))
        else:
            btn.setStyleSheet(getattr(btn, "_idle_style",
                                      btn.styleSheet()))

    def _emit_values(self):
        lx = ly = rx = 0.0
        for k in self._held:
            dlx, dly, drx = self._KEY_MAP.get(k, (0, 0, 0))
            lx += dlx
            ly += dly
            rx += drx
        # 归一化（防斜方向过快）
        if lx != 0.0 and ly != 0.0:
            import math
            scale = 1.0 / math.sqrt(2)
            lx *= scale
            ly *= scale

        lx = max(-1.0, min(1.0, lx * self._speed))
        ly = max(-1.0, min(1.0, ly * self._speed))
        rx = max(-1.0, min(1.0, rx * self._speed))
        self.joystickChanged.emit(lx, ly, rx, 0.0)

    def stop(self):
        self.emergency_stop()


# ──────────────────────────────────────────────────────────
# KeyboardMoveFilter — 安装在主窗口
# ──────────────────────────────────────────────────────────
class KeyboardMoveFilter(QObject):
    """
    事件过滤器：把 MainWindow 的 KeyPress/KeyRelease 路由给 MovementButtonPanel。
    """

    _KEY_TO_ACTION = {
        Qt.Key.Key_W:     "forward",
        Qt.Key.Key_Up:    "forward",
        Qt.Key.Key_S:     "back",
        Qt.Key.Key_Down:  "back",
        Qt.Key.Key_A:     "turn_left",
        Qt.Key.Key_Left:  "turn_left",
        Qt.Key.Key_Q:     "turn_left",
        Qt.Key.Key_D:     "turn_right",
        Qt.Key.Key_Right: "turn_right",
        Qt.Key.Key_E:     "turn_right",
        Qt.Key.Key_Z:     "strafe_left",
        Qt.Key.Key_X:     "strafe_right",
    }

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._panel: Optional[MovementButtonPanel] = None

    def set_panel(self, panel: Optional[MovementButtonPanel]):
        self._panel = panel

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self._panel is None:
            return False
        if not isinstance(event, QKeyEvent) or event.isAutoRepeat():
            return False

        key    = Qt.Key(event.key())
        action = self._KEY_TO_ACTION.get(key)

        # Space → 紧急停止
        if key == Qt.Key.Key_Space:
            if event.type() == QEvent.Type.KeyPress:
                self._panel.emergency_stop()
            return False

        if action:
            if event.type() == QEvent.Type.KeyPress:
                self._panel.key_press(action)
            elif event.type() == QEvent.Type.KeyRelease:
                self._panel.key_release(action)

        return False   # 不拦截，让其他控件也能收到事件
