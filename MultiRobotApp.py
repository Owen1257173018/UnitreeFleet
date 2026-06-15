"""
MultiRobotApp.py — Unitree 多机器人群控客户端
入口文件：设置 sys.path、运行 PyQt6 应用。

运行：
    python MultiRobotApp.py

Windows 打包（PyInstaller）：
    pyinstaller MultiRobotApp.spec
    （详见 FEATURES.md 的打包说明）
"""

import sys
import os
import logging

# ── 把本地的 unitree_webrtc_connect-master 加入搜索路径 ──
# 这样无论是直接运行还是打包后都能找到库
_ROOT = os.path.dirname(os.path.abspath(__file__))
_LIB  = os.path.join(_ROOT, "unitree_webrtc_connect-master")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

# ── Windows：必须在 import asyncio 之前设置事件循环策略 ──
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── 日志系统在 backend.py 导入时自动初始化（RotatingFileHandler）──
# 这里只确保 import backend 触发日志初始化，不再手动 basicConfig
# （避免重复添加 handler）

# ── 提前 import backend 触发文件日志 handler 注册 ──
import backend  # noqa: F401  (side-effect: sets up RotatingFileHandler)

# ── Qt 高 DPI 适配（必须在 QApplication 之前）──
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

_startup_logger = logging.getLogger("unitree.app")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Unitree 多机器人控制台")
    app.setOrganizationName("Unitree")
    app.setOrganizationDomain("unitree.com")

    # Fusion 风格（跨平台一致，避免 macOS/Windows 外观差异）
    app.setStyle("Fusion")

    # 默认字体（优先 PingFang SC → Segoe UI → 系统默认）
    font = QFont()
    font.setFamilies(["PingFang SC", "Microsoft YaHei", "Segoe UI", "Arial"])
    font.setPointSize(13)
    app.setFont(font)

    _startup_logger.info("Qt 应用启动  Python=%s  Platform=%s",
                         sys.version, sys.platform)

    # 延迟导入主窗口（避免 sys.path 未就绪时 import 失败）
    from main_window import MainWindow

    window = MainWindow()
    window.show()

    _startup_logger.info("主窗口已显示")
    ret = app.exec()
    _startup_logger.info("应用退出，code=%d", ret)
    sys.exit(ret)


if __name__ == "__main__":
    main()
