"""
main_window.py — 主窗口 + 所有面板

布局:
  ┌──────────────────────────────────────────────────────┐
  │  左面板 (RobotListPanel)  │  右面板 (ControlPanel)   │
  │  机器人列表 + 管理按钮     │  选中机器人的控制界面     │
  │                           ├──────────────────────────┤
  │                           │  日志面板（底部，可折叠）  │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QPainter, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QDialog,
    QFileDialog, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QRadioButton, QScrollArea,
    QSizePolicy, QSlider, QSplitter, QStackedWidget,
    QTabWidget, QTextEdit, QToolButton, QVBoxLayout,
    QWidget, QComboBox,
)

from backend import (
    ConfigManager, RobotInfo, RobotManager,
    GO2_ACTIONS, G1_ARM_ACTIONS, G1_MOVE_MODES, VUI_COLORS,
    ROBOT_TYPE_GO2, ROBOT_TYPE_G1,
    STATUS_CONNECTED, STATUS_CONNECTING, STATUS_DISCONNECTED,
    STATUS_RECONNECTING, STATUS_ERROR,
    SPORT_CMD,
)
from joystick import MovementButtonPanel, KeyboardMoveFilter
from dialogs import AddByIPDialog, AutoAddDialog, ConfirmDeleteDialog
from choreography import (ChoreoEditorDialog, ChoreoLibraryDialog,
                          ChoreoScript, RecordingSession, CHOREO_AUTO_DIR,
                          _sanitize_filename)

logger = logging.getLogger("unitree.ui")


# ──────────────────────────────────────────────────────────
# 全局样式
# ──────────────────────────────────────────────────────────
APP_STYLE = """
QMainWindow, QWidget {
    background: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "PingFang SC", "Helvetica Neue", sans-serif;
    font-size: 13px;
}
QSplitter::handle { background: #45475a; width: 2px; }
QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 4px;
    background: #1e1e2e;
}
QTabBar::tab {
    background: #2a2a3e;
    color: #a6adc8;
    padding: 6px 14px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    min-width: 70px;
}
QTabBar::tab:selected { background: #313244; color: #89b4fa; }
QTabBar::tab:hover    { background: #313244; }
QScrollArea { border: none; }
QScrollBar:vertical {
    background: #181825; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #45475a; border-radius: 4px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QGroupBox {
    color: #89b4fa;
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 4px;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QSlider::groove:horizontal {
    background: #45475a; height: 4px; border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #89b4fa; width: 14px; height: 14px;
    border-radius: 7px; margin: -5px 0;
}
QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 2px; }
QStatusBar { background: #181825; color: #a6adc8; }
QTextEdit {
    background: #11111b; color: #a6adc8; border: none;
    font-family: "Consolas", "Menlo", monospace; font-size: 11px;
}
"""

_ACTION_BTN = """
    QPushButton {
        background: #313244; color: #cdd6f4;
        border: 1px solid #45475a; border-radius: 5px;
        padding: 6px 4px; font-size: 12px;
    }
    QPushButton:hover   { background: #45475a; border-color: #89b4fa; }
    QPushButton:pressed { background: #585b70; }
    QPushButton:disabled { color: #585b70; border-color: #313244; }
"""
_DANGER_BTN = """
    QPushButton {
        background: #3d2535; color: #f38ba8;
        border: 1px solid #7d3545; border-radius: 5px; padding: 5px 10px;
    }
    QPushButton:hover   { background: #4d2f40; }
    QPushButton:pressed { background: #5d3a4d; }
"""
_PRIMARY_BTN = """
    QPushButton {
        background: #1e3a5f; color: #89b4fa;
        border: 1px solid #3a6898; border-radius: 5px;
        padding: 5px 10px; font-weight: bold;
    }
    QPushButton:hover    { background: #274d7a; }
    QPushButton:pressed  { background: #1a3254; }
    QPushButton:disabled { background: #1e2535; color: #45475a; border-color: #313244; }
"""
_LIST_BTN = """
    QPushButton {
        background: transparent; color: #89b4fa;
        border: 1px solid #3a4060; border-radius: 4px;
        padding: 4px 8px; font-size: 12px;
    }
    QPushButton:hover   { background: #2a2a3e; }
    QPushButton:pressed { background: #313244; }
"""
_SAVE_BTN = """
    QPushButton {
        background: #1e3a2a; color: #a6e3a1;
        border: 1px solid #2a6a3a; border-radius: 4px;
        padding: 4px 8px; font-size: 12px;
    }
    QPushButton:hover   { background: #254535; }
    QPushButton:pressed { background: #1a3025; }
"""

_STATUS_COLOR = {
    STATUS_CONNECTED:    "#a6e3a1",
    STATUS_CONNECTING:   "#f9e2af",
    STATUS_RECONNECTING: "#fab387",
    STATUS_DISCONNECTED: "#6c7086",
    STATUS_ERROR:        "#f38ba8",
}
_STATUS_TEXT = {
    STATUS_CONNECTED:    "已连接",
    STATUS_CONNECTING:   "连接中…",
    STATUS_RECONNECTING: "重连中…",
    STATUS_DISCONNECTED: "已断开",
    STATUS_ERROR:        "错误",
}


def _make_status_dot(status: str, size: int = 10) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(_STATUS_COLOR.get(status, "#6c7086")))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return px


# ──────────────────────────────────────────────────────────
# RobotListItemWidget
# ──────────────────────────────────────────────────────────
class RobotListItemWidget(QWidget):
    reconnectRequested = pyqtSignal(str)   # robot_id

    def __init__(self, robot: RobotInfo, parent=None):
        super().__init__(parent)
        self._robot_id = robot.id
        self._build(robot)

    def _build(self, robot: RobotInfo):
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 4, 4)
        row.setSpacing(6)

        icon_lbl = QLabel("🐕" if robot.is_go2 else "🤖")
        icon_lbl.setFixedWidth(22)
        row.addWidget(icon_lbl)

        self._name_lbl = QLabel(robot.name)
        self._name_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self._name_lbl)

        addr = robot.ip or robot.sn or ""
        addr_lbl = QLabel(addr[:16] + ("…" if len(addr) > 16 else ""))
        addr_lbl.setStyleSheet("color:#585b70; font-size:10px;")
        addr_lbl.setFixedWidth(100)
        row.addWidget(addr_lbl)

        self._bat_lbl = QLabel("")
        self._bat_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
        self._bat_lbl.setFixedWidth(36)
        row.addWidget(self._bat_lbl)

        self._dot_lbl = QLabel()
        self._dot_lbl.setFixedWidth(12)
        row.addWidget(self._dot_lbl)

        self._status_lbl = QLabel(_STATUS_TEXT[robot.status])
        self._status_lbl.setFixedWidth(52)
        self._status_lbl.setStyleSheet(
            f"color:{_STATUS_COLOR[robot.status]}; font-size:11px;")
        row.addWidget(self._status_lbl)

        # 每机器人独立重连按钮（仅在错误/断开时显示）
        self._recon_btn = QPushButton("↺")
        self._recon_btn.setFixedSize(26, 26)
        self._recon_btn.setToolTip("重新连接此机器人")
        self._recon_btn.setStyleSheet("""
            QPushButton {
                background: #1e3a5f; color: #89b4fa;
                border: 1px solid #3a6a9f; border-radius: 4px;
                font-size: 14px; font-weight: bold; padding: 0px;
            }
            QPushButton:hover   { background: #2a4a6f; border-color: #89b4fa; }
            QPushButton:pressed { background: #1a3050; }
        """)
        self._recon_btn.clicked.connect(
            lambda: self.reconnectRequested.emit(self._robot_id))
        self._recon_btn.setVisible(False)
        row.addWidget(self._recon_btn)

        self.update_status(robot.status, robot.error_msg or "")
        if robot.battery is not None:
            self.update_battery(robot.battery)

    def update_status(self, status: str, error_msg: str = ""):
        color = _STATUS_COLOR.get(status, "#6c7086")
        self.setToolTip(f"错误：{error_msg}"
                        if status == STATUS_ERROR and error_msg else "")
        self._dot_lbl.setPixmap(_make_status_dot(status))
        self._status_lbl.setText(_STATUS_TEXT.get(status, status))
        self._status_lbl.setStyleSheet(f"color:{color}; font-size:11px;")
        # 错误或断开时显示重连按钮
        is_bad = status in (STATUS_ERROR, STATUS_DISCONNECTED)
        self._recon_btn.setVisible(is_bad)

    def update_battery(self, pct: int):
        color = "#a6e3a1" if pct > 20 else "#f9e2af" if pct > 10 else "#f38ba8"
        self._bat_lbl.setText(f"{pct}%")
        self._bat_lbl.setStyleSheet(f"color:{color}; font-size:11px;")

    @property
    def robot_id(self) -> str:
        return self._robot_id


# ──────────────────────────────────────────────────────────
# 共用对话框样式（替代原 SavedRobotsDialog 的内嵌样式）
# ──────────────────────────────────────────────────────────
_CONFIG_DIALOG_STYLE = """
    QDialog { background: #1e1e2e; }
    QLabel  { color: #cdd6f4; }
    QLineEdit {
        background: #2a2a3e; color: #cdd6f4;
        border: 1px solid #45475a; border-radius: 4px;
        padding: 5px 8px; selection-background-color: #585b70;
    }
    QLineEdit:focus { border-color: #89b4fa; }
    QRadioButton { color: #cdd6f4; spacing: 6px; }
    QPushButton {
        background: #313244; color: #cdd6f4;
        border: 1px solid #45475a; border-radius: 4px;
        padding: 5px 14px; min-width: 70px;
    }
    QPushButton:hover { background: #45475a; }
    QPushButton#ok {
        background: #89b4fa; color: #1e1e2e;
        font-weight: bold; border: none;
    }
    QPushButton#ok:hover { background: #74c7ec; }
    QPushButton#ok:disabled { background: #45475a; color: #6c7086; }
    QFrame { background: #252535; border-radius: 4px; }
    QScrollArea { border: none; }
"""


# ──────────────────────────────────────────────────────────
# SaveConfigDialog — 保存当前机器列表为命名配置
# ──────────────────────────────────────────────────────────
class SaveConfigDialog(QDialog):
    """输入配置名称 + 预览即将保存的机器人列表。返回时通过 config_name 取名称。"""

    def __init__(self, robots: List[dict], default_name: str = "",
                 existing_names: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("保存当前配置")
        self.setMinimumWidth(420)
        self.setStyleSheet(_CONFIG_DIALOG_STYLE)
        self._robots = robots
        self._existing = set(existing_names or [])
        self.config_name: str = ""
        self._build_ui(default_name)

    def _build_ui(self, default_name: str):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        if not self._robots:
            empty = QLabel("当前机器人列表为空，请先添加再保存。")
            empty.setStyleSheet("color:#f9e2af; font-size:13px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(empty)
        else:
            hint = QLabel(f"将保存当前 {len(self._robots)} 台机器人的 IP / AES 密钥：")
            hint.setStyleSheet("color:#a6adc8; font-size:12px;")
            root.addWidget(hint)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            inner = QWidget()
            inner_v = QVBoxLayout(inner)
            inner_v.setSpacing(4)
            inner_v.setAlignment(Qt.AlignmentFlag.AlignTop)

            for r in self._robots:
                frame = QFrame()
                row = QHBoxLayout(frame)
                row.setContentsMargins(8, 4, 8, 4)
                row.setSpacing(8)

                icon = QLabel("🐕" if r.get("robot_type") == ROBOT_TYPE_GO2 else "🤖")
                icon.setFixedWidth(20)
                row.addWidget(icon)

                name_lbl = QLabel(r.get("name", "?"))
                name_lbl.setStyleSheet("font-weight: bold;")
                row.addWidget(name_lbl)

                addr = r.get("ip") or r.get("sn") or "?"
                addr_lbl = QLabel(addr)
                addr_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
                row.addWidget(addr_lbl)

                row.addStretch()

                key_lbl = QLabel("✓ 含密钥" if r.get("aes_128_key") else "无密钥")
                key_lbl.setStyleSheet(
                    "color:#a6e3a1; font-size:11px;" if r.get("aes_128_key")
                    else "color:#585b70; font-size:11px;")
                row.addWidget(key_lbl)

                inner_v.addWidget(frame)

            scroll.setWidget(inner)
            scroll.setMinimumHeight(160)
            root.addWidget(scroll, 1)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("配置名称："))
        self._name_edit = QLineEdit()
        self._name_edit.setText(default_name)
        self._name_edit.setPlaceholderText("例：客厅3只 / 演出A组")
        name_row.addWidget(self._name_edit, 1)
        root.addLayout(name_row)

        self._hint_lbl = QLabel("")
        self._hint_lbl.setStyleSheet("color:#f9e2af; font-size:11px;")
        root.addWidget(self._hint_lbl)

        btn_row = QHBoxLayout()
        cancel = QPushButton("取消")
        ok_btn = QPushButton("保存")
        ok_btn.setObjectName("ok")
        ok_btn.setEnabled(bool(self._robots))
        cancel.clicked.connect(self.reject)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def _on_ok(self):
        name = self._name_edit.text().strip()
        if not name:
            self._hint_lbl.setText("⚠ 请填写配置名称")
            return
        if name in self._existing:
            ret = QMessageBox.question(
                self, "覆盖已有配置？",
                f"配置「{name}」已存在，确定覆盖吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                return
        self.config_name = name
        self.accept()


# ──────────────────────────────────────────────────────────
# ConfigPickerDialog — 选择一个已保存配置进行连接
# ──────────────────────────────────────────────────────────
class ConfigPickerDialog(QDialog):
    """单选一个已保存配置 → 连接此配置里的所有机器人。

    accepted 后通过 selected_config 取被选中的 dict（含 name / robots 列表）。
    """

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置连接")
        self.setMinimumWidth(460)
        self.setMinimumHeight(360)
        self.setStyleSheet(_CONFIG_DIALOG_STYLE)
        self._config = config
        self._radios: List[tuple] = []  # (QRadioButton, cfg_dict, QFrame)
        self.selected_config: Optional[dict] = None
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        saved = self._config.get_saved_configs()
        if not saved:
            empty = QLabel(
                "还没有保存任何配置。\n\n"
                "先用 IP 添加 / 扫描添加把机器人加到列表，\n"
                "再点「💾 保存配置」给当前列表取名保存。")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color:#585b70; font-size:13px;")
            root.addWidget(empty, 1)
        else:
            hint = QLabel(f"共 {len(saved)} 个配置，选择一个连接：")
            hint.setStyleSheet("color:#a6adc8; font-size:12px;")
            root.addWidget(hint)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            inner = QWidget()
            inner_v = QVBoxLayout(inner)
            inner_v.setSpacing(4)
            inner_v.setAlignment(Qt.AlignmentFlag.AlignTop)

            for cfg in saved:
                self._build_config_row(cfg, inner_v)

            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

            # 默认选第一个
            if self._radios:
                self._radios[0][0].setChecked(True)

        btn_row = QHBoxLayout()
        cancel = QPushButton("取消")
        ok_btn = QPushButton("连接此配置")
        ok_btn.setObjectName("ok")
        ok_btn.setEnabled(bool(self._radios))
        cancel.clicked.connect(self.reject)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def _build_config_row(self, cfg: dict, parent_layout: QVBoxLayout):
        frame = QFrame()
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # 顶行：单选 + 名字 + 数量 + 删除
        top = QHBoxLayout()
        top.setSpacing(8)

        radio = QRadioButton()
        self._btn_group.addButton(radio)
        top.addWidget(radio)

        name_lbl = QLabel(cfg.get("name", "?"))
        name_lbl.setStyleSheet("font-weight: bold; color: #cdd6f4;")
        top.addWidget(name_lbl)

        robots = cfg.get("robots", [])
        n_with_key = sum(1 for r in robots if r.get("aes_128_key"))
        count_lbl = QLabel(f"{len(robots)} 台 · {n_with_key} 台含密钥")
        count_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
        top.addWidget(count_lbl)

        top.addStretch()

        del_btn = QPushButton("删除")
        del_btn.setStyleSheet(
            "QPushButton{background:#3d2535;color:#f38ba8;"
            "border:1px solid #7d3545;border-radius:3px;"
            "padding:2px 8px;font-size:11px;min-width:0;}"
            "QPushButton:hover{background:#4d2f40;}")
        del_btn.setFixedHeight(22)
        name = cfg.get("name", "")
        del_btn.clicked.connect(
            lambda _c, n=name, fr=frame, r=radio: self._delete_config(n, fr, r))
        top.addWidget(del_btn)
        outer.addLayout(top)

        # 子行：机器人列表（紧凑）
        for r in robots:
            sub = QLabel(
                f"  · {'🐕' if r.get('robot_type') == ROBOT_TYPE_GO2 else '🤖'} "
                f"{r.get('name', '?')}  "
                f"<span style='color:#585b70;'>{r.get('ip') or r.get('sn') or '?'}</span>"
                f"  <span style='color:{'#a6e3a1' if r.get('aes_128_key') else '#585b70'};font-size:10px;'>"
                f"{'✓ 密钥' if r.get('aes_128_key') else '无密钥'}</span>")
            sub.setStyleSheet("color:#a6adc8; font-size:11px;")
            outer.addWidget(sub)

        # 点 frame 任意处也能选中该 radio
        radio.toggled.connect(
            lambda checked, fr=frame: fr.setStyleSheet(
                "QFrame { background: #2a2a4e; border-radius: 4px; }"
                if checked else
                "QFrame { background: #252535; border-radius: 4px; }"))

        parent_layout.addWidget(frame)
        self._radios.append((radio, cfg, frame))

    def _delete_config(self, name: str, frame: QFrame, radio: QRadioButton):
        ret = QMessageBox.question(
            self, "删除配置",
            f"确定要删除配置「{name}」吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._config.delete_saved_config(name)
        self._radios = [(r, c, f) for r, c, f in self._radios if c.get("name") != name]
        self._btn_group.removeButton(radio)
        frame.deleteLater()
        logger.info("ConfigPickerDialog: 删除配置 %s", name)

    def _on_ok(self):
        for radio, cfg, _frame in self._radios:
            if radio.isChecked():
                self.selected_config = cfg
                self.accept()
                return
        QMessageBox.information(self, "提示", "请选择一个配置。")


# ──────────────────────────────────────────────────────────
# _ToggleListWidget — 单击即 toggle，无需 Ctrl
# ──────────────────────────────────────────────────────────
class _ToggleListWidget(QListWidget):
    """
    点击行为：
      • 轻按未选中的行 → 加入选中集合（不清除其他已选行）
      • 轻按已选中的行 → 从选中集合移除
      • **长按 ≥ 400ms** → 进入拖拽模式，可上下拖动换位（InternalMove）

    设计要点：
      - selectionMode = MultiSelection，super 在 press 时会 toggle 一次。
      - 我们在 press 记录 "toggle 前" 的选中状态并调用 super（让 Qt 记下
        pressedIndex，长按拖拽才能正确启动）。
      - 长按计时器到点后还原 super 做的那次 toggle（长按是为了拖拽，不是选中），
        再打开 dragEnabled，Qt 会在接下来的移动中触发拖拽。
      - 位置直接映射到编排轨道（#N），所以拖拽换位 = 编排位置换位。
    """
    orderChanged = pyqtSignal()   # 拖拽完成后发出
    LONG_PRESS_MS = 400

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(False)   # 默认关闭；长按后再打开

        self._press_timer = QTimer(self)
        self._press_timer.setSingleShot(True)
        self._press_timer.setInterval(self.LONG_PRESS_MS)
        self._press_timer.timeout.connect(self._on_long_press_fired)

        self._press_item: Optional[QListWidgetItem] = None
        self._press_pos: Optional[QPoint] = None
        self._press_prev_selected: bool = False
        self._drag_armed = False

    def _on_long_press_fired(self):
        """长按到点：撤销 press 时 super 做的 toggle，进入拖拽模式。"""
        if (QApplication.mouseButtons() & Qt.MouseButton.LeftButton) == 0:
            return
        if self._press_item is None:
            return
        # 撤销 super 在 press 时做的 toggle —— 长按是为了拖拽
        self._press_item.setSelected(self._press_prev_selected)
        self._drag_armed = True
        self.setDragEnabled(True)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        item = self.itemAt(event.position().toPoint())
        self._press_item = item
        self._press_pos = event.position().toPoint()
        self._press_prev_selected = bool(item and item.isSelected())
        self._drag_armed = False
        self.setDragEnabled(False)

        # 让 super 处理（MultiSelection 下会自动 toggle；同时记下 pressedIndex，
        # 拖拽起点依赖这个）
        super().mousePressEvent(event)

        if item is not None:
            self._press_timer.start()

    def mouseMoveEvent(self, event):
        if self._drag_armed:
            super().mouseMoveEvent(event)
            return
        # 未进入拖拽：鼠标走出 startDragDistance 就取消长按（避免滚动时误触发）
        if self._press_pos is not None:
            delta = (event.position().toPoint() - self._press_pos).manhattanLength()
            if delta > QApplication.startDragDistance():
                self._press_timer.stop()
        # 不调用 super，避免在轻按期间 Qt 做区间选择之类的副作用

    def mouseReleaseEvent(self, event):
        was_armed = self._drag_armed
        self._press_timer.stop()
        self._drag_armed = False
        self.setDragEnabled(False)
        self.unsetCursor()

        # super 统一处理（无论拖拽或轻按）；MultiSelection 模式下，轻按的
        # toggle 已经在 press 时完成，这里只负责清 Qt 的内部 pressed 状态。
        super().mouseReleaseEvent(event)

        self._press_item = None
        self._press_pos = None

    def dropEvent(self, event):
        super().dropEvent(event)
        # Qt 的 InternalMove 会把 setItemWidget 清掉，通知外部重绑
        self.orderChanged.emit()


# ──────────────────────────────────────────────────────────
# RobotListPanel — 左面板
# ──────────────────────────────────────────────────────────
class RobotListPanel(QWidget):
    selectionChanged = pyqtSignal(list)   # list[robot_id]

    def __init__(self, manager: RobotManager,
                 config: ConfigManager, parent=None):
        super().__init__(parent)
        self._mgr    = manager
        self._config = config
        self._item_map: Dict[str, QListWidgetItem] = {}
        self._widget_map: Dict[str, "RobotListItemWidget"] = {}
        self._auto_dlg: Optional[AutoAddDialog] = None
        self._pending_scan_sns: List[str] = []

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题
        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(10, 0, 10, 0)
        title = QLabel("机器人列表")
        title.setStyleSheet("color:#cdd6f4; font-weight:bold; font-size:14px;")
        h_row.addWidget(title)
        h_row.addStretch()
        root.addWidget(header)

        # 按钮容器：统一用 3 列 QGridLayout，所有按钮等宽填满左栏，
        # 避免之前 HBoxLayout + addStretch 造成的不对齐（第二排两个按钮中间
        # 出现一大截空白；各排长度不一）。
        btn_bar = QWidget()
        btn_bar.setStyleSheet("background:#1a1a2e;")
        btn_grid = QGridLayout(btn_bar)
        btn_grid.setContentsMargins(6, 6, 6, 6)
        btn_grid.setHorizontalSpacing(5)
        btn_grid.setVerticalSpacing(5)
        # 3 列等宽
        for c in range(3):
            btn_grid.setColumnStretch(c, 1)

        # 统一按钮高度，让三排看起来整齐
        _BTN_H = 28

        # ── 第 1 行：IP 添加 / 保存配置 / 配置连接 ──
        self._add_ip_btn   = QPushButton("＋ IP 添加")
        self._save_cfg_btn = QPushButton("💾 保存配置")
        self._saved_btn    = QPushButton("📂 配置连接")
        self._add_ip_btn.setStyleSheet(_LIST_BTN)
        self._save_cfg_btn.setStyleSheet(_SAVE_BTN)
        self._saved_btn.setStyleSheet(_SAVE_BTN)
        for b in (self._add_ip_btn, self._save_cfg_btn, self._saved_btn):
            b.setFixedHeight(_BTN_H)
        btn_grid.addWidget(self._add_ip_btn,   0, 0)
        btn_grid.addWidget(self._save_cfg_btn, 0, 1)
        btn_grid.addWidget(self._saved_btn,    0, 2)

        # ── 第 2 行：扫描添加 / 全选 / 删除（删除缩小到 1 列宽，比之前减半，
        # 避免误点；并且和上一排的「配置连接」对齐，视觉更整齐）──
        self._auto_add_btn = QPushButton("📡 扫描添加")
        self._sel_all_btn  = QPushButton("☑ 全选")
        self._auto_add_btn.setStyleSheet(_LIST_BTN)
        self._sel_all_btn.setStyleSheet(_LIST_BTN)
        self._sel_all_btn.setEnabled(False)
        self._del_btn = QPushButton("🗑 删除")
        self._del_btn.setStyleSheet(
            _DANGER_BTN.replace("padding: 5px 10px", "padding: 3px 6px"))
        self._del_btn.setEnabled(False)
        for b in (self._auto_add_btn, self._sel_all_btn, self._del_btn):
            b.setFixedHeight(_BTN_H)
        btn_grid.addWidget(self._auto_add_btn, 1, 0)
        btn_grid.addWidget(self._sel_all_btn,  1, 1)
        btn_grid.addWidget(self._del_btn,      1, 2)

        # ── 第 3 行：编排 / 编排库 / 录制 ──
        _CHOREO_STYLE = """
            QPushButton {
                background: #2d1e4a; color: #cba6f7;
                border: 1px solid #5a3a8a; border-radius: 4px;
                padding: 4px 10px; font-size: 12px;
            }
            QPushButton:hover   { background: #3d2860; }
            QPushButton:pressed { background: #4d3270; }
        """
        _REC_IDLE = """
            QPushButton {
                background: #2d1e1e; color: #f38ba8;
                border: 1px solid #7d3a3a; border-radius: 4px;
                padding: 4px 10px; font-size: 12px;
            }
            QPushButton:hover   { background: #3d2828; }
            QPushButton:pressed { background: #4d3030; }
        """
        _REC_ACTIVE = """
            QPushButton {
                background: #7d2020; color: #ffffff;
                border: 1px solid #f38ba8; border-radius: 4px;
                padding: 4px 10px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover   { background: #8d2828; }
            QPushButton:pressed { background: #9d3030; }
        """
        self._choreo_btn = QPushButton("🎬 编排")
        self._choreo_btn.setStyleSheet(_CHOREO_STYLE)
        self._choreo_btn.setToolTip(
            "打开编排编辑器：为多个机器人设计动作时间线，保存到 choreo_auto/")

        self._lib_btn = QPushButton("📂 编排库")
        self._lib_btn.setStyleSheet(_CHOREO_STYLE)
        self._lib_btn.setToolTip(
            "扫描 choreo_auto/ 目录，选择兼容的编排直接播放")

        self._rec_btn = QPushButton("⏺ 录制")
        self._rec_btn.setStyleSheet(_REC_IDLE)
        self._rec_btn.setToolTip(
            "开始录制：记录对所有机器人的操作，停止后保存为可回放的 JSON 文件")
        self._rec_btn._style_idle   = _REC_IDLE
        self._rec_btn._style_active = _REC_ACTIVE

        for b in (self._choreo_btn, self._lib_btn, self._rec_btn):
            b.setFixedHeight(_BTN_H)
        btn_grid.addWidget(self._choreo_btn, 2, 0)
        btn_grid.addWidget(self._lib_btn,    2, 1)
        btn_grid.addWidget(self._rec_btn,    2, 2)

        root.addWidget(btn_bar)

        # 录制会话状态（不在 __init__ 初始化以便集中在一处）
        self._recording: Optional[RecordingSession] = None

        # 选中计数标签
        self._sel_count_lbl = QLabel("")
        self._sel_count_lbl.setStyleSheet(
            "color:#585b70; font-size:11px; padding: 0 6px 2px 6px;")
        self._sel_count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(self._sel_count_lbl)

        # ── 列表（自定义点击：单击 toggle，再次单击取消）──
        self._list = _ToggleListWidget()
        self._list.setStyleSheet("""
            QListWidget { background: #181825; border: none; outline: none; }
            QListWidget::item { border-bottom: 1px solid #252535; padding: 2px 0; }
            QListWidget::item:selected { background: #2a2a4e; }
            QListWidget::item:hover:!selected { background: #252535; }
        """)
        # NoSelection：完全由我们的 mousePressEvent 控制选中状态
        self._list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.orderChanged.connect(self._on_order_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        root.addWidget(self._list, 1)

        self._add_ip_btn.clicked.connect(self._on_add_ip)
        self._auto_add_btn.clicked.connect(self._on_auto_add)
        self._save_cfg_btn.clicked.connect(self._on_save_config)
        self._saved_btn.clicked.connect(self._on_config_connect)
        self._sel_all_btn.clicked.connect(self._on_select_all)
        self._del_btn.clicked.connect(self._on_delete)
        self._choreo_btn.clicked.connect(self._on_open_choreo)
        self._lib_btn.clicked.connect(self._on_open_choreo_lib)
        self._rec_btn.clicked.connect(self._on_record_toggle)

    def _on_open_choreo(self):
        logger.info("[用户操作] 打开编排编辑器")
        ordered = self.get_ordered_robot_infos()
        dlg = ChoreoEditorDialog(
            self._mgr, self,
            ordered_robots=ordered,
            get_ordered_robots=self.get_ordered_robot_infos)
        dlg.exec()

    def _on_open_choreo_lib(self):
        logger.info("[用户操作] 打开编排库")
        dlg = ChoreoLibraryDialog(
            self._mgr, self,
            get_ordered_robots=self.get_ordered_robot_infos)
        dlg.exec()

    # ── 录制 ──────────────────────────────────────────────

    def _on_record_toggle(self):
        if self._recording is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        from backend import STATUS_CONNECTED
        # 录制保留完整设备列表顺序：每个位置都会成为一条轨道，
        # 没有操作到的位置自然是空轨道，文件里如实记录布局。
        robot_infos   = self.get_ordered_robot_infos()
        connected     = [r for r in robot_infos if r.status == STATUS_CONNECTED]

        if not robot_infos:
            QMessageBox.warning(self, "无法录制", "列表中没有机器人，请先添加并连接机器人。")
            return
        if not connected:
            QMessageBox.warning(self, "注意",
                                "当前没有已连接的机器人。录制会记录设备列表的布局，"
                                "但至少需要连接一台机器人才能实际捕获动作。\n\n"
                                "录制已开始，连接机器人后的操作将被记录。")

        self._recording = RecordingSession(robot_infos)
        self._mgr.set_recording_hook(self._recording.on_event)
        self._rec_btn.setText("⏹ 停止录制")
        self._rec_btn.setStyleSheet(self._rec_btn._style_active)
        # 录制期间禁用编排/编排库，防止同时播放编排导致录制内容混乱
        self._choreo_btn.setEnabled(False)
        self._lib_btn.setEnabled(False)
        logger.info("[录制] 开始录制，机器人顺序：%s",
                    [f"#{i+1} {r.robot_type} {r.name}"
                     for i, r in enumerate(robot_infos)])

    def _stop_recording(self):
        if self._recording is None:
            return
        self._mgr.clear_recording_hook()
        self._recording.flush_joystick()

        self._rec_btn.setText("⏺ 录制")
        self._rec_btn.setStyleSheet(self._rec_btn._style_idle)
        self._choreo_btn.setEnabled(True)
        self._lib_btn.setEnabled(True)

        script = self._recording.build_script()
        self._recording = None

        # 如果录制期间没有任何操作，提示用户并跳过保存
        if not script.has_any_steps():
            logger.info("[录制] 录制内容为空，跳过保存")
            QMessageBox.information(
                self, "录制为空",
                "录制期间没有捕获到任何操作，未保存文件。\n"
                "请确认在录制期间有对机器人执行动作（移动、sport 指令等）。")
            return

        # 保存（名字做一次过滤，防止里面的非法字符影响文件名或逃出目录）
        safe = _sanitize_filename(script.name)
        save_path = os.path.join(CHOREO_AUTO_DIR, f"{safe}.json")
        try:
            script.save(save_path)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return

        logger.info("[录制] 录制完成，已保存：%s", save_path)

        box = QMessageBox(self)
        box.setWindowTitle("录制完成")
        box.setText(f"录制已保存：\n{save_path}")
        box.setInformativeText("是否立即在编排编辑器中打开以查看或继续编辑？")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        if box.exec() == QMessageBox.StandardButton.Yes:
            loaded = ChoreoScript.load(save_path)
            dlg = ChoreoEditorDialog(
                self._mgr, self,
                initial_script=loaded,
                get_ordered_robots=self.get_ordered_robot_infos)
            dlg.exec()

    def _connect_signals(self):
        m = self._mgr
        m.robot_added.connect(self._on_robot_added)
        m.robot_removed.connect(self._on_robot_removed)
        m.robot_status_changed.connect(self._on_status_changed)
        m.robot_battery_updated.connect(self._on_battery_updated)
        m.scan_progress.connect(self._on_scan_progress)
        m.scan_finished.connect(self._on_scan_finished)

    def _on_robot_added(self, robot_id: str):
        robot = self._mgr.get_robot(robot_id)
        if not robot:
            return
        item   = QListWidgetItem()
        widget = RobotListItemWidget(robot)
        widget.reconnectRequested.connect(self._on_item_reconnect)
        item.setSizeHint(QSize(0, 50))
        item.setData(Qt.ItemDataRole.UserRole, robot_id)
        self._list.addItem(item)
        self._list.setItemWidget(item, widget)
        self._item_map[robot_id] = item
        self._widget_map[robot_id] = widget
        self._update_sel_all_btn()

    def _on_order_changed(self):
        """拖拽排序后 Qt 会清掉 setItemWidget，重新绑定所有条目的 widget。
        同时重建 _item_map —— InternalMove 可能创建新的 QListWidgetItem 对象，
        旧引用会失效，必须用 item.data(UserRole) 里存储的 robot_id 来匹配。"""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            rid = item.data(Qt.ItemDataRole.UserRole)
            if rid and rid in self._widget_map:
                self._item_map[rid] = item          # 刷新引用
                self._list.setItemWidget(item, self._widget_map[rid])

    def get_ordered_robot_ids(self) -> List[str]:
        """返回按列表视觉顺序排列的 robot_id 列表。"""
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            rid = item.data(Qt.ItemDataRole.UserRole)
            if rid:
                result.append(rid)
        return result

    def get_ordered_robot_infos(self) -> List[RobotInfo]:
        """返回按列表视觉顺序排列的 RobotInfo 列表（编排按位置映射用）。"""
        infos: List[RobotInfo] = []
        for rid in self.get_ordered_robot_ids():
            r = self._mgr.get_robot(rid)
            if r is not None:
                infos.append(r)
        return infos

    def _on_item_reconnect(self, robot_id: str):
        robot = self._mgr.get_robot(robot_id)
        if robot:
            self._mgr.log_user_action(f"列表重连 [{robot.name}]")
            self._mgr.reconnect_robot(robot_id)

    def _on_robot_removed(self, robot_id: str):
        item = self._item_map.pop(robot_id, None)
        self._widget_map.pop(robot_id, None)
        if item:
            self._list.takeItem(self._list.row(item))
        self._update_sel_all_btn()
        self._emit_selection()

    def _on_status_changed(self, robot_id: str, status: str, error_msg: str):
        item = self._item_map.get(robot_id)
        if not item:
            return
        w = self._list.itemWidget(item)
        if isinstance(w, RobotListItemWidget):
            w.update_status(status, error_msg)

    def _on_battery_updated(self, robot_id: str, pct: int):
        item = self._item_map.get(robot_id)
        if not item:
            return
        w = self._list.itemWidget(item)
        if isinstance(w, RobotListItemWidget):
            w.update_battery(pct)

    def _on_selection_changed(self):
        sel   = self._list.selectedItems()
        total = self._list.count()
        has_sel = bool(sel)
        self._del_btn.setEnabled(has_sel)
        # 全选按钮：有机器人时始终可用
        self._sel_all_btn.setEnabled(total > 0)
        # 全选按钮文字随实时状态更新
        if total > 0 and len(sel) == total:
            self._sel_all_btn.setText("☐ 取消全选")
        else:
            self._sel_all_btn.setText("☑ 全选")
        # 计数标签
        if has_sel:
            self._sel_count_lbl.setText(f"已选 {len(sel)} / {total}")
        else:
            self._sel_count_lbl.setText("")
        self._emit_selection()

    def _update_sel_all_btn(self):
        self._sel_all_btn.setEnabled(self._list.count() > 0)

    def _emit_selection(self):
        self.selectionChanged.emit(self._selected_ids())

    def _selected_ids(self) -> List[str]:
        ids = []
        for item in self._list.selectedItems():
            w = self._list.itemWidget(item)
            if isinstance(w, RobotListItemWidget):
                ids.append(w.robot_id)
        return ids

    def _on_select_all(self):
        """全选：若已全选则取消全选（toggle）。"""
        total = self._list.count()
        sel   = len(self._list.selectedItems())
        if sel == total and total > 0:
            # 全部已选 → 取消全选
            logger.info("[用户操作] 取消全选")
            self._list.clearSelection()
            self._sel_all_btn.setText("☑ 全选")
        else:
            # 否则全选
            logger.info("[用户操作] 全选 (%d 台)", total)
            self._list.selectAll()
            self._sel_all_btn.setText("☐ 取消全选")

    # ── 按钮处理 ──

    def _on_add_ip(self):
        logger.info("[用户操作] 点击 IP 手动添加")
        dlg = AddByIPDialog(config=self._config, parent=self)
        if dlg.exec() and dlg.result:
            r = dlg.result
            logger.info("[用户操作] 确认手动添加：name=%s type=%s ip=%s sn=%s aes=%s",
                        r["name"], r["robot_type"], r.get("ip"), r.get("sn"),
                        "*" * 8 if r.get("aes_128_key") else "(空)")
            # 不再自动写入 saved_robots —— 用户通过「保存配置」显式保存当前列表
            self._mgr.add_robot(
                name=r["name"], robot_type=r["robot_type"],
                ip=r.get("ip"), sn=r.get("sn"), token=r.get("token", ""),
                aes_128_key=r.get("aes_128_key", ""))

    def _on_auto_add(self):
        logger.info("[用户操作] 点击扫描添加")
        if self._auto_dlg and self._auto_dlg.isVisible():
            self._auto_dlg.raise_()
            return
        self._auto_dlg = AutoAddDialog(self._config, self)
        self._auto_dlg.scan_requested.connect(self._start_scan)
        if self._auto_dlg.exec():
            for dev in self._auto_dlg.selected_devices:
                logger.info("[用户操作] 扫描添加：name=%s type=%s ip=%s sn=%s",
                            dev["name"], dev["robot_type"], dev["ip"], dev.get("sn"))
                self._mgr.add_robot(
                    name=dev["name"], robot_type=dev["robot_type"],
                    ip=dev["ip"], sn=dev.get("sn"), token=dev.get("token", ""),
                    aes_128_key=dev.get("aes_128_key", ""))

    def _on_save_config(self):
        """保存当前机器列表（IP / SN / AES 密钥）为一个命名配置。"""
        logger.info("[用户操作] 点击保存配置")
        # 把当前列表里的机器人按可见顺序快照下来
        snapshot: List[dict] = []
        for rid in self.get_ordered_robot_ids():
            robot = self._mgr.get_robot(rid)
            if not robot:
                continue
            snapshot.append(dict(
                name=robot.name,
                robot_type=robot.robot_type,
                ip=robot.ip or "",
                sn=robot.sn or "",
                token=robot.token or "",
                aes_128_key=robot.aes_128_key or "",
            ))
        if not snapshot:
            QMessageBox.information(self, "提示",
                "当前机器人列表为空，请先添加机器人再保存配置。")
            return
        existing = [c.get("name", "") for c in self._config.get_saved_configs()]
        dlg = SaveConfigDialog(snapshot, existing_names=existing, parent=self)
        if dlg.exec() and dlg.config_name:
            self._config.save_config(dlg.config_name, snapshot)
            QMessageBox.information(self, "已保存",
                f"配置「{dlg.config_name}」已保存（{len(snapshot)} 台机器人）。")

    def _on_config_connect(self):
        """从已保存的配置中选一个，遍历其中的 (ip, aes_128_key) 全部连接。"""
        logger.info("[用户操作] 点击配置连接")
        dlg = ConfigPickerDialog(self._config, self)
        if dlg.exec() and dlg.selected_config:
            cfg = dlg.selected_config
            robots = cfg.get("robots", [])
            logger.info("[用户操作] 加载配置「%s」：%d 台机器人",
                        cfg.get("name"), len(robots))
            for dev in robots:
                name = dev.get("name") or "?"
                robot_type = dev.get("robot_type")
                if not robot_type:
                    logger.warning("配置 %s 中机器人 %s 缺 robot_type，跳过",
                                   cfg.get("name"), name)
                    continue
                self._mgr.add_robot(
                    name=name, robot_type=robot_type,
                    ip=dev.get("ip") or None,
                    sn=dev.get("sn") or None,
                    token=dev.get("token", ""),
                    aes_128_key=dev.get("aes_128_key", ""))

    def _start_scan(self, sns: List[str], save: bool, timeout: float):
        self._pending_scan_sns = sns
        self._mgr.scan_network(timeout)

    def _on_scan_progress(self, msg: str):
        if self._auto_dlg:
            self._auto_dlg.on_scan_progress(msg)

    def _on_scan_finished(self, result: dict):
        if self._auto_dlg:
            self._auto_dlg.on_scan_finished(result, self._pending_scan_sns)

    def _on_delete(self):
        ids   = self._selected_ids()
        # 保持 id 和 robot 配对，过滤掉已不存在的
        pairs = [(i, self._mgr.get_robot(i)) for i in ids]
        pairs = [(i, r) for i, r in pairs if r]
        if not pairs:
            return
        names = [r.name for _, r in pairs]
        logger.info("[用户操作] 请求删除：%s", names)
        dlg = ConfirmDeleteDialog(names, self)
        if dlg.exec():
            for rid, robot in pairs:
                if robot.sn:
                    self._config.remove_robot_by_sn(robot.sn)
                    self._config.remove_saved_entry_by_sn(robot.sn)
                elif robot.cfg_id:
                    self._config.remove_saved_robot(robot.cfg_id)
                self._mgr.remove_robot(rid)

    def _on_list_context_menu(self, pos: QPoint):
        item = self._list.itemAt(pos)
        if item is None:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        robot = self._mgr.get_robot(rid) if rid else None
        if not robot:
            return

        menu = QMenu(self)
        edit_aes = menu.addAction("🔑 编辑 AES 密钥（新固件）…")
        chosen = menu.exec(self._list.viewport().mapToGlobal(pos))
        if chosen is edit_aes:
            self._edit_aes_key(robot)

    def _edit_aes_key(self, robot: RobotInfo):
        from dialogs import UnitreeCloudLoginDialog
        if not robot.sn:
            QMessageBox.information(self, "需要 SN",
                "此机器人没有 SN，无法从云端拉取 AES 密钥。"
                "请先删除后用「IP 添加」重新创建并填写 SN。")
            return
        dlg = UnitreeCloudLoginDialog(
            sn=robot.sn, robot_type=robot.robot_type,
            config=self._config, parent=self)
        if dlg.exec() and dlg.fetched_key:
            robot.aes_128_key = dlg.fetched_key
            if robot.cfg_id:
                self._config.update_saved_robot_aes_key(
                    robot.cfg_id, dlg.fetched_key)
            QMessageBox.information(self, "已更新",
                "AES 密钥已更新，请尝试重新连接此机器人。")
            logger.info("[用户操作] 已为 %s 更新 AES 密钥", robot.name)


# ──────────────────────────────────────────────────────────
# ActionButton（带日志的动作按钮）
# ──────────────────────────────────────────────────────────
class ActionButton(QPushButton):
    def __init__(self, label: str, callback, log_label: str = "",
                 manager: Optional[RobotManager] = None, parent=None):
        super().__init__(label, parent)
        self.setStyleSheet(_ACTION_BTN)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(38)
        self._log_label  = log_label or label
        self._manager    = manager

        def _on_click():
            if self._manager:
                self._manager.log_user_action(f"点击动作按钮 [{self._log_label}]")
            callback()

        self.clicked.connect(_on_click)


# ──────────────────────────────────────────────────────────
# Go2ControlTab
# ──────────────────────────────────────────────────────────
class Go2ControlTab(QWidget):
    def __init__(self, manager: RobotManager, parent=None):
        super().__init__(parent)
        self._mgr       = manager
        self._robot_ids : List[str] = []
        self._build_ui()

    def set_robots(self, ids: List[str]):
        self._robot_ids = ids

    def _send(self, api_id: int, label: str):
        self._mgr.log_user_action(
            f"Go2 动作 [{label}(api_id={api_id})]",
            f"目标={self._robot_ids}")
        self._mgr.send_sport_cmd(self._robot_ids, api_id)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        tabs = QTabWidget()
        for category, actions in GO2_ACTIONS.items():
            page = QWidget()
            grid = QGridLayout(page)
            grid.setSpacing(5)
            grid.setContentsMargins(4, 4, 4, 4)
            for idx, (api_id, label) in enumerate(actions):
                btn = ActionButton(label,
                                   lambda a=api_id, lbl=label: self._send(a, lbl),
                                   log_label=label, manager=None)
                grid.addWidget(btn, idx // 3, idx % 3)
            tabs.addTab(page, category)
        root.addWidget(tabs)

        # 高级设置
        adv = QGroupBox("高级设置")
        adv_v = QVBoxLayout(adv)
        adv_v.setSpacing(6)

        # LED 颜色
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("LED 颜色："))
        self._color_combo = QComboBox()
        for c, lbl in VUI_COLORS:
            self._color_combo.addItem(lbl, c)
        self._color_combo.setFixedWidth(70)
        set_color_btn = QPushButton("设置")
        set_color_btn.setStyleSheet(_PRIMARY_BTN)
        set_color_btn.setFixedWidth(56)
        set_color_btn.clicked.connect(self._set_color)
        color_row.addWidget(self._color_combo)
        color_row.addWidget(set_color_btn)
        color_row.addStretch()
        adv_v.addLayout(color_row)

        # 亮度
        bright_row = QHBoxLayout()
        bright_row.addWidget(QLabel("LED 亮度："))
        self._bright_slider = QSlider(Qt.Orientation.Horizontal)
        self._bright_slider.setRange(0, 10)
        self._bright_slider.setValue(5)
        self._bright_slider.setFixedWidth(110)
        self._bright_lbl = QLabel("5")
        self._bright_lbl.setFixedWidth(18)
        self._bright_slider.valueChanged.connect(
            lambda v: self._bright_lbl.setText(str(v)))
        set_bright_btn = QPushButton("设置")
        set_bright_btn.setStyleSheet(_PRIMARY_BTN)
        set_bright_btn.setFixedWidth(56)
        set_bright_btn.clicked.connect(self._set_brightness)
        bright_row.addWidget(self._bright_slider)
        bright_row.addWidget(self._bright_lbl)
        bright_row.addWidget(set_bright_btn)
        bright_row.addStretch()
        adv_v.addLayout(bright_row)

        # 运动模式
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("运动模式："))
        normal_btn = QPushButton("普通")
        ai_btn     = QPushButton("AI")
        for b in (normal_btn, ai_btn):
            b.setStyleSheet(_PRIMARY_BTN)
            b.setFixedWidth(60)
        normal_btn.clicked.connect(lambda: (
            self._mgr.log_user_action("Go2 切换运动模式 [normal]"),
            self._mgr.send_motion_mode(self._robot_ids, "normal")))
        ai_btn.clicked.connect(lambda: (
            self._mgr.log_user_action("Go2 切换运动模式 [ai]"),
            self._mgr.send_motion_mode(self._robot_ids, "ai")))
        mode_row.addWidget(normal_btn)
        mode_row.addWidget(ai_btn)
        mode_row.addStretch()
        adv_v.addLayout(mode_row)

        root.addWidget(adv)

        # ── 音乐播放 ──
        music = QGroupBox("音乐播放")
        music_v = QVBoxLayout(music)
        music_v.setSpacing(6)

        # 第一行：本地音乐直播（megaphone 模式）
        stream_row = QHBoxLayout()
        stream_lbl = QLabel("本地音乐：")
        stream_lbl.setStyleSheet("color:#a6adc8; font-size:12px;")
        stream_lbl.setFixedWidth(60)
        self._stream_file_lbl = QLabel("未选择文件")
        self._stream_file_lbl.setStyleSheet(
            "color:#585b70; font-size:11px; background:#181825; "
            "border:1px solid #313244; border-radius:3px; padding:2px 6px;")
        self._stream_file_lbl.setMinimumWidth(120)
        self._stream_select_btn = QPushButton("选择文件")
        self._stream_select_btn.setStyleSheet(_PRIMARY_BTN)
        self._stream_select_btn.setFixedWidth(70)
        self._stream_select_btn.clicked.connect(self._select_stream_file)
        self._stream_play_btn = QPushButton("▶ 播放")
        self._stream_play_btn.setStyleSheet(_PRIMARY_BTN)
        self._stream_play_btn.setFixedWidth(56)
        self._stream_play_btn.clicked.connect(self._stream_play)
        self._stream_stop_btn = QPushButton("■ 停止")
        self._stream_stop_btn.setStyleSheet(_PRIMARY_BTN)
        self._stream_stop_btn.setFixedWidth(56)
        self._stream_stop_btn.clicked.connect(self._stream_stop)
        stream_row.addWidget(stream_lbl)
        stream_row.addWidget(self._stream_file_lbl, 1)
        stream_row.addWidget(self._stream_select_btn)
        stream_row.addWidget(self._stream_play_btn)
        stream_row.addWidget(self._stream_stop_btn)
        music_v.addLayout(stream_row)

        # 进度条（流式播放 + 上传共用）
        self._upload_bar = QProgressBar()
        self._upload_bar.setFixedHeight(16)
        self._upload_bar.setVisible(False)
        self._upload_bar.setStyleSheet(
            "QProgressBar { background:#181825; border:1px solid #313244; "
            "border-radius:4px; text-align:center; color:#cdd6f4; font-size:11px; }"
            "QProgressBar::chunk { background:#89b4fa; border-radius:3px; }")
        music_v.addWidget(self._upload_bar)

        self._stream_file_path: str = ""

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#313244;")
        music_v.addWidget(sep)

        # 第二行：机器人内置音频（AudioHub）
        hub_lbl = QLabel("机器人内置音频：")
        hub_lbl.setStyleSheet("color:#a6adc8; font-size:12px;")
        music_v.addWidget(hub_lbl)

        ctrl_row = QHBoxLayout()
        self._music_refresh_btn = QPushButton("刷新列表")
        self._music_refresh_btn.setStyleSheet(_PRIMARY_BTN)
        self._music_refresh_btn.clicked.connect(self._refresh_audio_list)
        self._music_play_btn = QPushButton("▶ 播放")
        self._music_play_btn.setStyleSheet(_PRIMARY_BTN)
        self._music_play_btn.clicked.connect(self._play_selected_audio)
        self._music_pause_btn = QPushButton("⏸ 暂停")
        self._music_pause_btn.setStyleSheet(_PRIMARY_BTN)
        self._music_pause_btn.clicked.connect(self._pause_audio)
        self._music_resume_btn = QPushButton("⏵ 继续")
        self._music_resume_btn.setStyleSheet(_PRIMARY_BTN)
        self._music_resume_btn.clicked.connect(self._resume_audio)
        self._music_upload_btn = QPushButton("上传")
        self._music_upload_btn.setStyleSheet(_PRIMARY_BTN)
        self._music_upload_btn.clicked.connect(self._upload_audio)
        ctrl_row.addWidget(self._music_refresh_btn)
        ctrl_row.addWidget(self._music_play_btn)
        ctrl_row.addWidget(self._music_pause_btn)
        ctrl_row.addWidget(self._music_resume_btn)
        ctrl_row.addWidget(self._music_upload_btn)
        ctrl_row.addStretch()
        music_v.addLayout(ctrl_row)

        # 音频列表
        self._audio_list_widget = QListWidget()
        self._audio_list_widget.setFixedHeight(100)
        self._audio_list_widget.setStyleSheet(
            "QListWidget { background:#181825; color:#cdd6f4; "
            "border:1px solid #313244; border-radius:4px; font-size:12px; }"
            "QListWidget::item:selected { background:#45475a; }")
        self._audio_list_widget.doubleClicked.connect(self._play_selected_audio)
        music_v.addWidget(self._audio_list_widget)

        self._audio_items: list = []  # [{name, uuid}, ...]
        root.addWidget(music)

        # 连接信号
        self._mgr.audio_list_result.connect(self._on_audio_list_result)
        self._mgr.audio_upload_progress.connect(self._on_upload_progress)
        self._mgr.audio_upload_done.connect(self._on_upload_done)

    def _set_color(self):
        color = self._color_combo.currentData()
        self._mgr.log_user_action(f"Go2 设置 LED 颜色 [{color}]")
        self._mgr.send_vui_color(self._robot_ids, color, 5)

    def _set_brightness(self):
        level = self._bright_slider.value()
        self._mgr.log_user_action(f"Go2 设置 LED 亮度 [{level}]")
        self._mgr.send_vui_brightness(self._robot_ids, level)

    def _refresh_audio_list(self):
        if not self._robot_ids:
            return
        self._audio_list_widget.clear()
        self._audio_items.clear()
        self._audio_list_widget.addItem("正在加载…")
        self._mgr.fetch_audio_list(self._robot_ids[0])

    def _on_audio_list_result(self, robot_id: str, items: list):
        self._audio_list_widget.clear()
        self._audio_items = items
        if not items:
            self._audio_list_widget.addItem("（无音频文件）")
            return
        for item in items:
            self._audio_list_widget.addItem(item["name"])

    def _play_selected_audio(self):
        if not self._robot_ids or not self._audio_items:
            return
        row = self._audio_list_widget.currentRow()
        if row < 0 or row >= len(self._audio_items):
            return
        item = self._audio_items[row]
        self._mgr.log_user_action(
            f"Go2 播放音频 [{item['name']}]",
            f"目标={self._robot_ids}")
        self._mgr.play_audio(self._robot_ids, item["uuid"], item["name"])

    def _pause_audio(self):
        if not self._robot_ids:
            return
        self._mgr.log_user_action("Go2 暂停音频", f"目标={self._robot_ids}")
        self._mgr.pause_audio(self._robot_ids)

    def _resume_audio(self):
        if not self._robot_ids:
            return
        self._mgr.log_user_action("Go2 恢复音频", f"目标={self._robot_ids}")
        self._mgr.resume_audio(self._robot_ids)

    # ── 本地音乐流式播放 ──

    def _select_stream_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "音频文件 (*.mp3 *.wav *.flac *.ogg);;所有文件 (*)")
        if not path:
            return
        self._stream_file_path = path
        self._stream_file_lbl.setText(os.path.basename(path))
        self._stream_file_lbl.setStyleSheet(
            "color:#cdd6f4; font-size:11px; background:#181825; "
            "border:1px solid #313244; border-radius:3px; padding:2px 6px;")

    def _stream_play(self):
        if not self._robot_ids:
            return
        if not self._stream_file_path:
            self._select_stream_file()
            if not self._stream_file_path:
                return
        self._upload_bar.setValue(0)
        self._upload_bar.setVisible(True)
        self._stream_play_btn.setEnabled(False)
        name = os.path.basename(self._stream_file_path)
        self._mgr.log_user_action(
            f"Go2 流式播放 [{name}]", f"目标={self._robot_ids}")
        self._mgr.stream_audio_file(self._robot_ids, self._stream_file_path)

    def _stream_stop(self):
        if not self._robot_ids:
            return
        self._mgr.log_user_action("Go2 停止音频流", f"目标={self._robot_ids}")
        self._mgr.stop_stream_audio(self._robot_ids)
        self._upload_bar.setVisible(False)
        self._stream_play_btn.setEnabled(True)

    # ── 机器人内置音频上传 ──

    def _upload_audio(self):
        if not self._robot_ids:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "音频文件 (*.mp3 *.wav);;MP3 (*.mp3);;WAV (*.wav)")
        if not path:
            return
        self._upload_bar.setValue(0)
        self._upload_bar.setVisible(True)
        self._music_upload_btn.setEnabled(False)
        self._mgr.log_user_action(
            f"Go2 上传音频 [{os.path.basename(path)}]",
            f"目标={self._robot_ids[0]}")
        self._mgr.upload_audio(self._robot_ids[0], path)

    def _on_upload_progress(self, robot_id: str, current: int, total: int):
        self._upload_bar.setMaximum(total)
        self._upload_bar.setValue(current)
        self._upload_bar.setFormat(f"{current}/{total}")

    def _on_upload_done(self, robot_id: str, ok: bool, msg: str):
        self._upload_bar.setVisible(False)
        self._music_upload_btn.setEnabled(True)
        self._stream_play_btn.setEnabled(True)
        if ok:
            self._refresh_audio_list()


# ──────────────────────────────────────────────────────────
# G1ControlTab
# ──────────────────────────────────────────────────────────
class G1ControlTab(QWidget):
    def __init__(self, manager: RobotManager, parent=None):
        super().__init__(parent)
        self._mgr       = manager
        self._robot_ids : List[str] = []
        self._build_ui()

    def set_robots(self, ids: List[str]):
        self._robot_ids = ids

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        arm_group = QGroupBox("手臂动作")
        arm_grid  = QGridLayout(arm_group)
        arm_grid.setSpacing(5)
        arm_grid.setContentsMargins(4, 8, 4, 4)
        for idx, (data, label) in enumerate(G1_ARM_ACTIONS):
            btn = ActionButton(
                label,
                lambda d=data: self._mgr.send_g1_arm_action(self._robot_ids, d),
                log_label=label, manager=self._mgr)
            arm_grid.addWidget(btn, idx // 4, idx % 4)
        root.addWidget(arm_group)

        mode_group = QGroupBox("运动模式")
        mode_row   = QHBoxLayout(mode_group)
        mode_row.setSpacing(8)
        for code, label in G1_MOVE_MODES:
            btn = QPushButton(label)
            btn.setStyleSheet(_PRIMARY_BTN)
            btn.clicked.connect(
                lambda checked, c=code, lbl=label: (
                    self._mgr.log_user_action(f"G1 切换模式 [{lbl}({c})]"),
                    self._mgr.send_g1_switch_mode(self._robot_ids, c)))
            mode_row.addWidget(btn)
        mode_row.addStretch()
        root.addWidget(mode_group)
        root.addStretch()


# ──────────────────────────────────────────────────────────
# LogPanel — 底部日志面板
# ──────────────────────────────────────────────────────────
class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet("background:#181825; border-top:1px solid #313244;")
        bar_row = QHBoxLayout(bar)
        bar_row.setContentsMargins(8, 0, 8, 0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle_btn.setStyleSheet("border:none; color:#89b4fa;")
        self._toggle_btn.clicked.connect(self._toggle)

        bar_lbl = QLabel("日志")
        bar_lbl.setStyleSheet("color:#89b4fa; font-size:12px;")

        self._log_path_lbl = QLabel("")
        self._log_path_lbl.setStyleSheet("color:#45475a; font-size:10px;")

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#585b70;border:none;font-size:11px;}"
            "QPushButton:hover{color:#a6adc8;}")
        self._clear_btn.setFixedHeight(20)
        self._clear_btn.clicked.connect(self._clear)

        bar_row.addWidget(self._toggle_btn)
        bar_row.addWidget(bar_lbl)
        bar_row.addWidget(self._log_path_lbl)
        bar_row.addStretch()
        bar_row.addWidget(self._clear_btn)
        root.addWidget(bar)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFixedHeight(140)
        self._log_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self._log_edit)

        self._expanded = True

    def set_log_path(self, path: str):
        self._log_path_lbl.setText(f"  →  {path}")
        self._log_path_lbl.setToolTip(path)

    def _toggle(self):
        self._expanded = not self._expanded
        self._log_edit.setVisible(self._expanded)
        self._toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if self._expanded else Qt.ArrowType.RightArrow)

    def _clear(self):
        self._log_edit.clear()

    def append(self, msg: str):
        # 按内容着色
        if "✅" in msg or "✓" in msg or "成功" in msg:
            color = "#a6e3a1"
        elif "❌" in msg or "失败" in msg or "错误" in msg or "异常" in msg:
            color = "#f38ba8"
        elif "⚠" in msg or "警告" in msg or "跳过" in msg:
            color = "#f9e2af"
        elif "⏳" in msg or "▶" in msg or "发送" in msg or "正在" in msg:
            color = "#89b4fa"
        elif "🚨" in msg or "紧急" in msg:
            color = "#fab387"
        elif "用户操作" in msg:
            color = "#cba6f7"
        else:
            color = "#a6adc8"

        self._log_edit.append(
            f'<span style="color:{color};">{msg}</span>')
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())


# ──────────────────────────────────────────────────────────
# ControlPanel — 右面板
# ──────────────────────────────────────────────────────────
class ControlPanel(QWidget):
    def __init__(self, manager: RobotManager, log_panel: LogPanel, parent=None):
        super().__init__(parent)
        self._mgr        = manager
        self._log        = log_panel
        self._robot_ids  : List[str] = []
        self._lx = self._ly = self._rx = self._ry = 0.0

        # 100ms 定时器持续推送摇杆
        self._joystick_timer = QTimer(self)
        self._joystick_timer.setInterval(100)
        self._joystick_timer.timeout.connect(self._tick_joystick)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部信息栏
        self._header = QWidget()
        self._header.setFixedHeight(44)
        self._header.setStyleSheet(
            "background:#181825; border-bottom:1px solid #313244;")
        h_row = QHBoxLayout(self._header)
        h_row.setContentsMargins(12, 0, 12, 0)
        self._header_lbl = QLabel("请在左侧选择机器人")
        self._header_lbl.setStyleSheet("color:#a6adc8; font-size:13px;")
        h_row.addWidget(self._header_lbl)
        h_row.addStretch()

        self._reconnect_btn = QPushButton("↺ 重连")
        self._reconnect_btn.setStyleSheet(_PRIMARY_BTN)
        self._reconnect_btn.setVisible(False)
        self._reconnect_btn.clicked.connect(self._on_reconnect)
        h_row.addWidget(self._reconnect_btn)
        root.addWidget(self._header)

        # 内容堆叠
        self._stack = QStackedWidget()

        # Page 0: 空状态
        empty = QWidget()
        ev    = QVBoxLayout(empty)
        ev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el = QLabel("← 在左侧选择机器人\n"
                    "单选：显示该机器人全部控制\n"
                    "多选（Ctrl/Shift）：显示通用移动控制")
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.setStyleSheet("color:#45475a; font-size:13px; line-height:1.8;")
        ev.addWidget(el)
        self._stack.addWidget(empty)         # idx 0

        # Page 1: Go2
        self._go2_page = self._build_robot_page("go2")
        self._stack.addWidget(self._go2_page)  # idx 1

        # Page 2: G1
        self._g1_page = self._build_robot_page("g1")
        self._stack.addWidget(self._g1_page)   # idx 2

        # Page 3: 混合
        self._mixed_page = self._build_mixed_page()
        self._stack.addWidget(self._mixed_page) # idx 3

        root.addWidget(self._stack, 1)

    def _make_movement_panel(self, tag: str) -> MovementButtonPanel:
        panel = MovementButtonPanel()
        panel.joystickChanged.connect(self._on_joystick_changed)
        panel.emergencyStop.connect(self._on_emergency_stop)  # ← 直接调后端
        setattr(self, f"_mvpanel_{tag}", panel)
        return panel

    def _build_robot_page(self, robot_type: str) -> QWidget:
        page = QWidget()
        v    = QVBoxLayout(page)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        move_group = QGroupBox("移动控制 (W/S/A/D + Q/E 旋转 | Z/X 侧走 | Space 停止)")
        mg_v       = QVBoxLayout(move_group)
        mg_v.setContentsMargins(4, 8, 4, 4)
        panel = self._make_movement_panel(robot_type)
        mg_v.addWidget(panel)
        v.addWidget(move_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        if robot_type == "go2":
            self._go2_tab = Go2ControlTab(self._mgr)
            scroll.setWidget(self._go2_tab)
        else:
            self._g1_tab = G1ControlTab(self._mgr)
            scroll.setWidget(self._g1_tab)
        v.addWidget(scroll, 1)
        return page

    def _build_mixed_page(self) -> QWidget:
        page = QWidget()
        v    = QVBoxLayout(page)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        note = QLabel("ℹ️  同时选中了 Go2 和 G1 机器人 — 混合模式下仅显示移动控制")
        note.setStyleSheet("color:#fab387; font-size:12px;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(note)

        move_group = QGroupBox("移动控制（全部选中的机器人）")
        mg_v       = QVBoxLayout(move_group)
        mg_v.setContentsMargins(4, 8, 4, 4)
        panel = self._make_movement_panel("mixed")
        mg_v.addWidget(panel)
        v.addWidget(move_group)
        v.addStretch()
        return page

    def _connect_signals(self):
        self._mgr.robot_status_changed.connect(self._on_any_status_changed)
        self._mgr.command_result.connect(self._on_command_result)

    # ── 公开 API ──

    def on_selection_changed(self, robot_ids: List[str]):
        # 切换前释放旧面板的按键，防止残留命令发给新机器人
        old_panel = self.get_active_panel()
        if old_panel:
            old_panel.release_all()

        self._robot_ids = robot_ids

        if not robot_ids:
            self._stack.setCurrentIndex(0)
            self._header_lbl.setText("请在左侧选择机器人")
            self._reconnect_btn.setVisible(False)
            self._joystick_timer.stop()
            return

        robots = [self._mgr.get_robot(i) for i in robot_ids
                  if self._mgr.get_robot(i)]
        types  = {r.robot_type for r in robots}
        names  = "、".join(r.name for r in robots[:3])
        if len(robots) > 3:
            names += f" 等 {len(robots)} 台"
        self._header_lbl.setText(names)

        any_bad = any(r.status in (STATUS_ERROR, STATUS_DISCONNECTED)
                      for r in robots)
        self._reconnect_btn.setVisible(any_bad)

        go2_ids = [r.id for r in robots if r.is_go2]
        g1_ids  = [r.id for r in robots if r.is_g1]

        if len(types) == 1 and ROBOT_TYPE_GO2 in types:
            self._go2_tab.set_robots(go2_ids)
            self._stack.setCurrentIndex(1)
        elif len(types) == 1 and ROBOT_TYPE_G1 in types:
            self._g1_tab.set_robots(g1_ids)
            self._stack.setCurrentIndex(2)
        else:
            self._stack.setCurrentIndex(3)

        self._joystick_timer.start()

    def get_active_panel(self) -> Optional[MovementButtonPanel]:
        idx = self._stack.currentIndex()
        if idx == 1:
            return getattr(self, "_mvpanel_go2", None)
        if idx == 2:
            return getattr(self, "_mvpanel_g1", None)
        if idx == 3:
            return getattr(self, "_mvpanel_mixed", None)
        return None

    # ── 摇杆 ──

    def _on_joystick_changed(self, lx: float, ly: float, rx: float, ry: float):
        self._lx, self._ly, self._rx, self._ry = lx, ly, rx, ry
        if lx != 0.0 or ly != 0.0 or rx != 0.0 or ry != 0.0:
            self._zero_send_count = 0

    def _tick_joystick(self):
        if not self._robot_ids:
            return
            
        if self._lx == 0.0 and self._ly == 0.0 and self._rx == 0.0 and self._ry == 0.0:
            self._zero_send_count = getattr(self, "_zero_send_count", 0) + 1
            if self._zero_send_count > 3:
                return  # Stop spamming 0.0 to allow choreography/scripts to move the robot
                
        connected = [rid for rid in self._robot_ids
                     if self._mgr.get_robot(rid) and
                     self._mgr.get_robot(rid).status == STATUS_CONNECTED]
        if connected:
            self._mgr.send_joystick(connected,
                                    self._lx, self._ly, self._rx, self._ry)

    def _on_emergency_stop(self):
        """摇杆面板的紧急停止按钮按下 → 立即调后端。"""
        self._lx = self._ly = self._rx = self._ry = 0.0
        self._zero_send_count = 0
        connected = [rid for rid in self._robot_ids
                     if self._mgr.get_robot(rid) and
                     self._mgr.get_robot(rid).status == STATUS_CONNECTED]
        if connected:
            self._mgr.log_user_action("🚨 紧急停止",
                                      f"目标={connected}")
            self._mgr.emergency_stop_robots(connected)

    # ── 状态 ──

    def _on_any_status_changed(self, robot_id: str, status: str, _msg: str):
        if robot_id not in self._robot_ids:
            return
        robots  = [self._mgr.get_robot(i) for i in self._robot_ids
                   if self._mgr.get_robot(i)]
        any_bad = any(r.status in (STATUS_ERROR, STATUS_DISCONNECTED)
                      for r in robots)
        self._reconnect_btn.setVisible(any_bad)

    def _on_reconnect(self):
        for rid in self._robot_ids:
            robot = self._mgr.get_robot(rid)
            if robot and robot.status in (STATUS_ERROR, STATUS_DISCONNECTED):
                self._mgr.log_user_action(f"手动重连 [{robot.name}]")
                self._mgr.reconnect_robot(rid)

    def _on_command_result(self, robot_id: str, ok: bool, msg: str):
        if not ok and robot_id in self._robot_ids:
            robot = self._mgr.get_robot(robot_id)
            name  = robot.name if robot else robot_id
            self._log.append(
                f"[{time.strftime('%H:%M:%S')}] ❌ 指令失败 [{name}]: {msg}")


# ──────────────────────────────────────────────────────────
# MainWindow
# ──────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unitree 多机器人控制台")
        self.resize(1200, 760)
        self.setMinimumSize(880, 580)
        self.setStyleSheet(APP_STYLE)

        self._config  = ConfigManager()
        self._manager = RobotManager(parent=self, config=self._config)

        self._build_ui()
        self._install_keyboard_filter()

        # 状态栏刷新
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2000)
        self._status_timer.timeout.connect(self._refresh_statusbar)
        self._status_timer.start()

        self._manager.command_result.connect(self._on_command_result_sb)
        self._manager.robot_status_changed.connect(self._on_status_change_sb)
        self._manager.log_message.connect(self._log_panel.append)

        # 在日志面板显示文件路径
        from backend import _LOG_FILE
        self._log_panel.set_log_path(_LOG_FILE)
        logger.info("主窗口初始化完成，日志文件：%s", _LOG_FILE)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer   = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.setHandleWidth(3)

        self._list_panel = RobotListPanel(self._manager, self._config)
        h_splitter.addWidget(self._list_panel)

        # 右侧：控制面板 + 日志（竖向）
        right_widget = QWidget()
        right_v      = QVBoxLayout(right_widget)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(0)

        self._log_panel     = LogPanel()
        self._control_panel = ControlPanel(self._manager, self._log_panel)

        right_v.addWidget(self._control_panel, 1)
        right_v.addWidget(self._log_panel)

        h_splitter.addWidget(right_widget)
        h_splitter.setSizes([280, 920])
        h_splitter.setCollapsible(0, False)
        h_splitter.setCollapsible(1, False)

        outer.addWidget(h_splitter, 1)

        self._list_panel.selectionChanged.connect(
            self._control_panel.on_selection_changed)

        # 状态栏
        sb = self.statusBar()
        self._sb_robots_lbl = QLabel("机器人：0")
        self._sb_conn_lbl   = QLabel("已连接：0")
        self._sb_cmd_lbl    = QLabel("")
        sb.addWidget(self._sb_robots_lbl)
        sb.addWidget(QLabel("  |  "))
        sb.addWidget(self._sb_conn_lbl)
        sb.addPermanentWidget(self._sb_cmd_lbl)

    def _install_keyboard_filter(self):
        self._kb_filter = KeyboardMoveFilter(parent=self)

        def _update_panel():
            self._kb_filter.set_panel(
                self._control_panel.get_active_panel())

        self._control_panel._stack.currentChanged.connect(
            lambda _: _update_panel())
        self.installEventFilter(self._kb_filter)

    def _refresh_statusbar(self):
        robots = self._manager.robots
        total  = len(robots)
        conn   = sum(1 for r in robots.values()
                     if r.status == STATUS_CONNECTED)
        self._sb_robots_lbl.setText(f"机器人：{total}")
        self._sb_conn_lbl.setText(f"已连接：{conn}")

    def _on_command_result_sb(self, robot_id: str, ok: bool, msg: str):
        robot = self._manager.get_robot(robot_id)
        name  = robot.name if robot else robot_id
        if ok:
            self._sb_cmd_lbl.setText(f"✓ {name} 指令成功")
        else:
            self._sb_cmd_lbl.setText(f"✗ {name}: {msg[:50]}")
        QTimer.singleShot(3000, lambda: self._sb_cmd_lbl.setText(""))

    def _on_status_change_sb(self, robot_id: str, status: str, msg: str):
        robot = self._manager.get_robot(robot_id)
        name  = robot.name if robot else robot_id
        if status == STATUS_ERROR:
            self._sb_cmd_lbl.setText(f"⚠ {name}: {msg[:50]}")
            QTimer.singleShot(6000, lambda: self._sb_cmd_lbl.setText(""))
        elif status == STATUS_CONNECTED:
            self._sb_cmd_lbl.setText(f"✓ {name} 已连接")
            QTimer.singleShot(3000, lambda: self._sb_cmd_lbl.setText(""))

    def changeEvent(self, event):
        """窗口失焦时释放所有按键，防止机器人在后台继续移动。"""
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange and not self.isActiveWindow():
            panel = self._control_panel.get_active_panel()
            if panel:
                panel.release_all()

    def closeEvent(self, event):
        logger.info("应用关闭，断开所有连接")
        self._manager.shutdown()
        event.accept()
