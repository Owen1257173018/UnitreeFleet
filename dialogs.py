"""
dialogs.py — 所有对话框
  AddByIPDialog      : 手动填 IP 添加机器人
  AutoAddDialog      : 通过 SN 号自动扫描添加
  ScanResultDialog   : 展示扫描结果，供用户勾选并确认
"""

from __future__ import annotations

from typing import List, Optional, Dict

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
    QCheckBox, QComboBox, QFrame, QWidget, QProgressBar,
    QButtonGroup, QSpinBox
)

from backend import (
    ConfigManager, RobotManager,
    ROBOT_TYPE_GO2, ROBOT_TYPE_G1,
)
from i18n import tr

import logging
import threading

logger = logging.getLogger("MultiRobotApp.dialogs")


# ──────────────────────────────────────────────────────────
# 通用样式助手
# ──────────────────────────────────────────────────────────
_DIALOG_STYLE = """
    QDialog {
        background: #1e1e2e;
    }
    QLabel {
        color: #cdd6f4;
    }
    QLineEdit, QTextEdit, QComboBox, QSpinBox {
        background: #2a2a3e;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: #585b70;
    }
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
        border: 1px solid #89b4fa;
    }
    QGroupBox {
        color: #89b4fa;
        border: 1px solid #45475a;
        border-radius: 6px;
        margin-top: 10px;
        padding-top: 6px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
    }
    QPushButton {
        background: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 5px 14px;
        min-width: 80px;
    }
    QPushButton:hover  { background: #45475a; }
    QPushButton:pressed { background: #585b70; }
    QPushButton#primaryBtn {
        background: #89b4fa;
        color: #1e1e2e;
        font-weight: bold;
        border: none;
    }
    QPushButton#primaryBtn:hover  { background: #74c7ec; }
    QPushButton#primaryBtn:disabled { background: #45475a; color: #6c7086; }
    QCheckBox { color: #cdd6f4; }
    QCheckBox::indicator { width: 14px; height: 14px; }
    QRadioButton { color: #cdd6f4; }
    QListWidget {
        background: #181825;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
    }
    QListWidget::item:selected { background: #313244; }
    QListWidget::item:hover    { background: #2a2a3e; }
    QProgressBar {
        background: #2a2a3e;
        border: 1px solid #45475a;
        border-radius: 3px;
        height: 8px;
        text-align: center;
    }
    QProgressBar::chunk { background: #89b4fa; border-radius: 3px; }
    QScrollArea { border: none; }
"""


def _make_button(text: str, primary: bool = False) -> QPushButton:
    btn = QPushButton(text)
    if primary:
        btn.setObjectName("primaryBtn")
    return btn


# ──────────────────────────────────────────────────────────
# AddByIPDialog
# ──────────────────────────────────────────────────────────
class AddByIPDialog(QDialog):
    """
    手动填写 IP 地址、选择机器人类型来添加设备。
    accepted → self.result 包含 (name, robot_type, ip, sn, token, aes_128_key)
    """

    def __init__(self, config: Optional[ConfigManager] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("手动添加机器人"))
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(440)
        self.result: Optional[dict] = None
        self._config = config
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── 基本信息 ──
        form_group = QGroupBox(tr("设备信息"))
        form = QFormLayout(form_group)
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("例：机器狗A  /  G1铁柱"))
        form.addRow(tr("名称："), self._name_edit)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText(tr("例：192.168.88.10"))
        form.addRow(tr("IP 地址："), self._ip_edit)

        self._sn_edit = QLineEdit()
        self._sn_edit.setPlaceholderText(tr("选填，新固件拉取 AES 密钥时必需"))
        form.addRow(tr("SN："), self._sn_edit)

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText(tr("选填（LocalSTA 通常不需要）"))
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("Token："), self._token_edit)

        # AES 密钥行 + 从云端获取按钮
        aes_row = QHBoxLayout()
        aes_row.setSpacing(6)
        self._aes_edit = QLineEdit()
        self._aes_edit.setPlaceholderText(tr("32 位 16 进制（仅新固件需要，留空=老固件）"))
        aes_row.addWidget(self._aes_edit, 1)
        self._aes_fetch_btn = QPushButton(tr("☁ 从云端获取"))
        self._aes_fetch_btn.clicked.connect(self._on_fetch_aes)
        aes_row.addWidget(self._aes_fetch_btn)
        form.addRow(tr("AES 密钥："), aes_row)

        root.addWidget(form_group)

        # ── 机器人类型 ──
        type_group = QGroupBox(tr("机器人类型"))
        type_row = QHBoxLayout(type_group)
        self._go2_radio = QRadioButton(tr("🐕  Go2 机器狗"))
        self._g1_radio  = QRadioButton(tr("🤖  G1 人形机器人"))
        self._go2_radio.setChecked(True)
        type_row.addWidget(self._go2_radio)
        type_row.addWidget(self._g1_radio)
        root.addWidget(type_group)

        # ── 确认 / 取消 ──
        btn_row = QHBoxLayout()
        cancel = _make_button(tr("取消"))
        ok     = _make_button(tr("连接"), primary=True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_ok)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        root.addLayout(btn_row)

    def _on_fetch_aes(self):
        # 不再要求先在外层填好 SN / 选好类型：直接进云端对话框，里面独立填 SN + 选类型，
        # 成功后把 AES 密钥、SN、类型一并回填到本对话框。
        sn = self._sn_edit.text().strip()
        robot_type = ROBOT_TYPE_GO2 if self._go2_radio.isChecked() else ROBOT_TYPE_G1
        dlg = UnitreeCloudLoginDialog(sn=sn, robot_type=robot_type,
                                      config=self._config, parent=self)
        if dlg.exec() and dlg.fetched_key:
            self._aes_edit.setText(dlg.fetched_key)
            if dlg.fetched_sn:
                self._sn_edit.setText(dlg.fetched_sn)
            if dlg.fetched_type == ROBOT_TYPE_G1:
                self._g1_radio.setChecked(True)
            else:
                self._go2_radio.setChecked(True)

    def _on_ok(self):
        name  = self._name_edit.text().strip()
        ip    = self._ip_edit.text().strip()
        sn    = self._sn_edit.text().strip()
        token = self._token_edit.text().strip()
        aes   = self._aes_edit.text().strip()

        if not name:
            QMessageBox.warning(self, tr("缺少名称"), tr("请输入机器人名称。"))
            return
        if not ip:
            QMessageBox.warning(self, tr("缺少 IP"), tr("请填写机器人的 IP 地址。"))
            return

        robot_type = ROBOT_TYPE_GO2 if self._go2_radio.isChecked() else ROBOT_TYPE_G1
        self.result = dict(name=name, robot_type=robot_type,
                           ip=ip, sn=sn or None, token=token,
                           aes_128_key=aes)
        self.accept()


# ──────────────────────────────────────────────────────────
# AutoAddDialog — 填写多个 SN，自动扫描并添加
# ──────────────────────────────────────────────────────────
class AutoAddDialog(QDialog):
    """
    输入多个 SN，点击"开始扫描"，扫到的设备进入结果列表，
    用户确认后批量添加。SN 列表可选择保存到本地配置。
    """

    # 携带扫描任务给 MainWindow：(sn_list, save_flag, timeout)
    scan_requested = pyqtSignal(list, bool, float)

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("自动扫描添加"))
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(460)
        self.setMinimumHeight(520)
        self._config = config
        self._scan_result: Dict[str, str] = {}   # sn -> ip
        self._row_widgets: List[dict] = []        # 结果行控件

        self._build_ui()
        self._load_saved()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # ── SN 输入区 ──
        sn_group = QGroupBox(tr("目标 SN 列表（每行一个）"))
        sn_layout = QVBoxLayout(sn_group)

        self._sn_text = QTextEdit()
        self._sn_text.setPlaceholderText(
            "B42D2000P4Q89986\nB42D2000P45A5383\n...")
        self._sn_text.setMinimumHeight(100)
        self._sn_text.setMaximumHeight(140)
        sn_layout.addWidget(self._sn_text)

        opts_row = QHBoxLayout()
        self._save_cb = QCheckBox(tr("保存此 SN 列表，下次自动填入"))
        self._save_cb.setChecked(True)
        opts_row.addWidget(self._save_cb)
        opts_row.addStretch()

        timeout_lbl = QLabel(tr("超时："))
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(2, 30)
        self._timeout_spin.setValue(3)
        self._timeout_spin.setSuffix(tr(" 秒"))
        self._timeout_spin.setFixedWidth(80)
        opts_row.addWidget(timeout_lbl)
        opts_row.addWidget(self._timeout_spin)
        sn_layout.addLayout(opts_row)

        root.addWidget(sn_group)

        # ── 扫描按钮 + 进度 ──
        scan_row = QHBoxLayout()
        self._scan_btn = _make_button(tr("📡  开始扫描"), primary=True)
        self._scan_btn.clicked.connect(self._start_scan)
        scan_row.addStretch()
        scan_row.addWidget(self._scan_btn)
        root.addLayout(scan_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # 不确定模式
        self._progress.setVisible(False)
        self._progress.setFixedHeight(8)
        root.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#a6e3a1; font-size:12px;")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status_lbl)

        # ── 结果列表 ──
        result_group = QGroupBox(tr("扫描结果（勾选要添加的设备）"))
        result_v = QVBoxLayout(result_group)

        self._result_scroll = QScrollArea()
        self._result_scroll.setWidgetResizable(True)
        self._result_inner = QWidget()
        self._result_vlay  = QVBoxLayout(self._result_inner)
        self._result_vlay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._result_vlay.setSpacing(4)
        self._result_scroll.setWidget(self._result_inner)
        self._result_scroll.setMinimumHeight(140)
        result_v.addWidget(self._result_scroll)

        root.addWidget(result_group)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        cancel = _make_button(tr("关闭"))
        self._add_btn = _make_button(tr("✅  添加选中设备"), primary=True)
        self._add_btn.setEnabled(False)
        cancel.clicked.connect(self.reject)
        self._add_btn.clicked.connect(self._on_add)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(self._add_btn)
        root.addLayout(btn_row)

    def _load_saved(self):
        entries = self._config.get_saved_entries()
        if entries:
            sns = [e["sn"] for e in entries if e.get("sn")]
            self._sn_text.setPlainText("\n".join(sns))

    def _start_scan(self):
        raw  = self._sn_text.toPlainText().strip()
        sns  = [s.strip() for s in raw.splitlines() if s.strip()]
        save = self._save_cb.isChecked()
        tout = float(self._timeout_spin.value())

        if not sns:
            QMessageBox.information(self, tr("提示"), tr(
                "请在上方输入至少一个序列号。\n"
                "如果想扫描网络中所有设备，可不填 SN 直接扫描。"))

        # 保存 SN：完整替换，确保删掉的 SN 不会残留
        if save:
            self._config.replace_saved_entries(sns)

        self._clear_results()
        self._set_scanning(True)
        self.scan_requested.emit(sns, save, tout)

    def _set_scanning(self, on: bool):
        self._scan_btn.setEnabled(not on)
        self._progress.setVisible(on)
        if on:
            self._status_lbl.setText(tr("扫描中…"))
        else:
            pass

    def _clear_results(self):
        for i in reversed(range(self._result_vlay.count())):
            w = self._result_vlay.itemAt(i).widget()
            if w:
                w.deleteLater()
        self._row_widgets.clear()
        self._add_btn.setEnabled(False)

    def on_scan_finished(self, sn_to_ip: Dict[str, str],
                         target_sns: List[str]):
        """由 MainWindow 在扫描完成后调用。"""
        self._set_scanning(False)
        self._scan_result = sn_to_ip
        self._clear_results()

        if not sn_to_ip:
            self._status_lbl.setText(tr("❌  未发现任何设备，请检查网络连接"))
            return

        # 目标列表与扫描结果的交集
        if target_sns:
            matched   = {sn: ip for sn, ip in sn_to_ip.items() if sn in target_sns}
            unmatched = [sn for sn in target_sns if sn not in sn_to_ip]
        else:
            matched   = dict(sn_to_ip)
            unmatched = []

        total = len(matched)
        self._status_lbl.setText(
            tr("✅  发现 {n} 台设备，目标命中 {hit} 台", n=len(sn_to_ip), hit=total)
            + (tr("，{n} 台未在线", n=len(unmatched)) if unmatched else ""))

        for sn, ip in matched.items():
            self._add_result_row(sn, ip)

        # 标出未在线的目标
        for sn in unmatched:
            self._add_result_row(sn, "", offline=True)

        self._add_btn.setEnabled(bool(matched))

    def _add_result_row(self, sn: str, ip: str, offline: bool = False):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background:#252535; border-radius:4px; padding:2px 6px; }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(8)

        cb = QCheckBox()
        cb.setChecked(not offline)
        cb.setEnabled(not offline)
        row.addWidget(cb)

        # 类型
        from backend import RobotManager
        rtype = RobotManager.detect_type_from_sn(sn) or ROBOT_TYPE_GO2
        combo = QComboBox()
        combo.addItem(tr("🐕 Go2 机器狗"),  ROBOT_TYPE_GO2)
        combo.addItem(tr("🤖 G1 人形机器人"), ROBOT_TYPE_G1)
        combo.setCurrentIndex(0 if rtype == ROBOT_TYPE_GO2 else 1)
        combo.setEnabled(not offline)
        combo.setFixedWidth(130)
        row.addWidget(combo)

        sn_lbl = QLabel(sn)
        sn_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
        row.addWidget(sn_lbl)

        ip_lbl = QLabel(ip if ip else tr("离线"))
        ip_lbl.setStyleSheet(
            "color:#a6e3a1;" if ip else "color:#f38ba8;")
        ip_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(ip_lbl)

        # 名称
        name_edit = QLineEdit()
        name_edit.setPlaceholderText(tr("设备名称"))
        name_edit.setText(sn[-6:])   # 默认用 SN 后 6 位
        name_edit.setFixedWidth(90)
        name_edit.setEnabled(not offline)
        row.addWidget(name_edit)

        # AES 密钥状态 + 行内 fetch 按钮
        existing_key = ""
        for saved in self._config.get_saved_robots():
            if saved.get("sn") == sn:
                existing_key = saved.get("aes_128_key", "") or ""
                break

        key_lbl = QLabel()
        key_lbl.setFixedWidth(78)
        key_lbl.setStyleSheet("font-size:11px;")
        fetch_btn = QPushButton("☁")
        fetch_btn.setToolTip(tr("从宇树云端拉取此设备的 AES-128 密钥"))
        fetch_btn.setFixedWidth(28)
        fetch_btn.setEnabled(not offline)

        row_state = dict(cb=cb, combo=combo, sn=sn, ip=ip,
                         name_edit=name_edit,
                         aes_128_key=existing_key,
                         key_lbl=key_lbl)

        def _refresh_key_label():
            if row_state["aes_128_key"]:
                key_lbl.setText(tr("✓ 已有密钥"))
                key_lbl.setStyleSheet("color:#a6e3a1; font-size:11px;")
            else:
                key_lbl.setText(tr("⚠ 需获取"))
                key_lbl.setStyleSheet("color:#f9e2af; font-size:11px;")

        def _on_fetch():
            dtype = ROBOT_TYPE_GO2 if combo.currentData() == ROBOT_TYPE_GO2 else ROBOT_TYPE_G1
            dlg = UnitreeCloudLoginDialog(sn=sn, robot_type=dtype,
                                          config=self._config, parent=self)
            if dlg.exec() and dlg.fetched_key:
                row_state["aes_128_key"] = dlg.fetched_key
                _refresh_key_label()

        fetch_btn.clicked.connect(_on_fetch)
        _refresh_key_label()

        row.addWidget(key_lbl)
        row.addWidget(fetch_btn)

        self._result_vlay.addWidget(frame)
        self._row_widgets.append(row_state)

    def _on_add(self):
        self._selected = []
        for row in self._row_widgets:
            if row["cb"].isChecked() and row["ip"]:
                self._selected.append(dict(
                    name        = row["name_edit"].text().strip() or row["sn"][-6:],
                    robot_type  = row["combo"].currentData(),
                    ip          = row["ip"],
                    sn          = row["sn"],
                    token       = "",
                    aes_128_key = row.get("aes_128_key", ""),
                ))
        if not self._selected:
            QMessageBox.information(self, tr("提示"), tr("没有选中任何在线设备。"))
            return
        self.accept()

    @property
    def selected_devices(self) -> List[dict]:
        return getattr(self, "_selected", [])

    def on_scan_progress(self, msg: str):
        self._status_lbl.setText(msg)


# ──────────────────────────────────────────────────────────
# ConfirmDeleteDialog
# ──────────────────────────────────────────────────────────
class ConfirmDeleteDialog(QDialog):
    def __init__(self, names: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("确认删除"))
        self.setStyleSheet(_DIALOG_STYLE)
        self.setFixedWidth(300)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        msg = QLabel(tr("确定要断开并删除以下 {n} 台设备吗？", n=len(names)))
        msg.setWordWrap(True)
        root.addWidget(msg)

        lst = "\n".join(f"  • {n}" for n in names)
        detail = QLabel(lst)
        detail.setStyleSheet("color:#f38ba8;")
        root.addWidget(detail)

        btn_row = QHBoxLayout()
        cancel = _make_button(tr("取消"))
        ok     = _make_button(tr("删除"), primary=True)
        ok.setStyleSheet(
            "QPushButton#primaryBtn { background:#f38ba8; color:#1e1e2e; }"
        )
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        root.addLayout(btn_row)


# ──────────────────────────────────────────────────────────
# UnitreeCloudLoginDialog — 用宇树账号拉取设备 AES-128 密钥
# ──────────────────────────────────────────────────────────
class UnitreeCloudLoginDialog(QDialog):
    """
    用宇树账号登录云端、根据 SN 拉取该机器人的 AES-128 密钥。
    成功后通过 self.fetched_key 返回 32 位 16 进制密钥；密码绝不持久化。
    """

    # 跨线程把结果送回 UI 线程
    _result_ready = pyqtSignal(bool, str)   # ok, key_or_error

    def __init__(self, sn: str, robot_type: str,
                 config: Optional[ConfigManager] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("从宇树云端获取 AES 密钥"))
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(420)
        self._sn = sn
        self._robot_type = robot_type
        self._config = config
        self.fetched_key: str = ""
        # SN 和设备类型现在都在本对话框里独立填/选，成功后一并回传给外层。
        self.fetched_sn: str = ""
        self.fetched_type: str = robot_type
        self._build_ui()
        self._result_ready.connect(self._on_fetch_result)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        info = QLabel(tr(
            "在这里直接填 <b>SN</b> 和选 <b>设备类型</b>，再用您的 <b>宇树官方账号</b> 登录，<br>"
            "一次性拉取该设备的 AES-128 密钥（持久化在本地配置，密码不会保存）。"
        ))
        info.setStyleSheet("color:#a6adc8; font-size:12px;")
        info.setWordWrap(True)
        root.addWidget(info)

        # ── 凭据 ──
        form = QFormLayout()
        form.setSpacing(8)

        # SN 独立输入（不再依赖外层先填好）
        self._sn_edit = QLineEdit()
        self._sn_edit.setText(self._sn or "")
        self._sn_edit.setPlaceholderText(tr("机器人电池仓/机身贴纸上的序列号"))
        form.addRow(tr("SN："), self._sn_edit)

        self._email_edit = QLineEdit()
        self._email_edit.setPlaceholderText("you@example.com")
        if self._config:
            self._email_edit.setText(self._config.get_unitree_email() or "")
        form.addRow(tr("邮箱："), self._email_edit)

        self._pwd_edit = QLineEdit()
        self._pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pwd_edit.setPlaceholderText(tr("不会保存到本地"))
        form.addRow(tr("密码："), self._pwd_edit)

        self._region_combo = QComboBox()
        self._region_combo.addItem(tr("cn（中国）"), "cn")
        self._region_combo.addItem(tr("global（国际）"), "global")
        self._region_combo.setCurrentIndex(0)   # 默认国内
        form.addRow(tr("区域："), self._region_combo)

        self._dtype_combo = QComboBox()
        self._dtype_combo.addItem("Go2", "Go2")
        self._dtype_combo.addItem("G1", "G1")
        self._dtype_combo.setCurrentIndex(0 if self._robot_type == ROBOT_TYPE_GO2 else 1)
        form.addRow(tr("设备类型："), self._dtype_combo)

        root.addLayout(form)

        # ── 状态 ──
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#a6adc8; font-size:12px;")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setMinimumHeight(36)
        root.addWidget(self._status_lbl)

        # ── 按钮 ──
        btn_row = QHBoxLayout()
        cancel = _make_button(tr("取消"))
        self._fetch_btn = _make_button(tr("获取密钥"), primary=True)
        cancel.clicked.connect(self.reject)
        self._fetch_btn.clicked.connect(self._on_fetch)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(self._fetch_btn)
        root.addLayout(btn_row)

    def _on_fetch(self):
        sn    = self._sn_edit.text().strip()
        email = self._email_edit.text().strip()
        pwd   = self._pwd_edit.text()
        if not sn:
            self._status_lbl.setText(tr("⚠ 请填写 SN 序列号"))
            self._status_lbl.setStyleSheet("color:#f9e2af; font-size:12px;")
            return
        if not email:
            self._status_lbl.setText(tr("⚠ 请填写邮箱"))
            self._status_lbl.setStyleSheet("color:#f9e2af; font-size:12px;")
            return
        if not pwd:
            self._status_lbl.setText(tr("⚠ 请填写密码"))
            self._status_lbl.setStyleSheet("color:#f9e2af; font-size:12px;")
            return

        region = self._region_combo.currentData()
        dtype  = self._dtype_combo.currentData()
        # 记下这次用的 SN / 类型，成功后回传给外层对话框自动回填。
        self._sn = sn
        self.fetched_sn = sn
        self.fetched_type = ROBOT_TYPE_GO2 if dtype == "Go2" else ROBOT_TYPE_G1

        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText(tr("获取中…"))
        self._status_lbl.setText(tr("⏳ 正在连接宇树云端，请稍候…"))
        self._status_lbl.setStyleSheet("color:#89b4fa; font-size:12px;")

        threading.Thread(
            target=self._do_fetch_in_thread,
            args=(email, pwd, sn, region, dtype),
            daemon=True, name="UnitreeCloudFetch"
        ).start()

    def _do_fetch_in_thread(self, email: str, password: str, sn: str,
                            region: str, device_type: str):
        try:
            from unitree_webrtc_connect import fetch_aes_key
        except ImportError as e:
            self._result_ready.emit(
                False, tr("库不支持此功能（请确认已升级到新版）：{err}", err=e))
            return
        try:
            key = fetch_aes_key(email, password, sn,
                                region=region, device_type=device_type)
            if not key:
                self._result_ready.emit(
                    False, tr("云端未返回密钥（SN 可能未绑定到此账号）"))
                return
            # 成功：记住邮箱（密码绝不持久化）
            if self._config:
                self._config.set_unitree_email(email)
            self._result_ready.emit(True, key)
        except Exception as e:
            logger.exception("fetch_aes_key 失败")
            self._result_ready.emit(False, f"{type(e).__name__}: {e}")

    def _on_fetch_result(self, ok: bool, payload: str):
        self._fetch_btn.setEnabled(True)
        self._fetch_btn.setText(tr("获取密钥"))
        if ok:
            self.fetched_key = payload
            self._status_lbl.setText(tr("✅ 获取成功：{key}", key=payload))
            self._status_lbl.setStyleSheet("color:#a6e3a1; font-size:12px;")
            # 让用户看清楚再关闭
            QTimer.singleShot(600, self.accept)
        else:
            self._status_lbl.setText(tr("❌ {msg}", msg=payload))
            self._status_lbl.setStyleSheet("color:#f38ba8; font-size:12px;")
