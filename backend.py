"""
backend.py — RobotManager + ConfigManager
所有的 asyncio 连接/指令逻辑都在这里，完全在后台线程运行，
通过 Qt 信号把结果安全地推回 UI 线程。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
import uuid
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

# ──────────────────────────────────────────────────────────
# 路径：让 PyInstaller 打包后也能找到库
# ──────────────────────────────────────────────────────────
# PyInstaller 打包后 __file__ 指向 _internal/ 子目录，
# 而 .exe 和 choreo_auto/、logs/ 等在上一层。
# getattr(sys, '_MEIPASS', None) 在打包环境下指向解压的临时目录。
def _app_root() -> str:
    """返回应用根目录：开发时 = 脚本所在目录，打包后 = .exe 所在目录。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，sys.executable 是 .exe 的绝对路径
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

APP_ROOT = _app_root()

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "unitree_webrtc_connect-master")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from unitree_webrtc_connect import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD, VUI_COLOR, AUDIO_API, DATA_CHANNEL_TYPE

# 新版库的结构化异常（旧版没有，导入失败说明库还是旧的）
try:
    from unitree_webrtc_connect import (
        AesKeyRequiredError, AesKeyRejectedError,
        LocalSignalingPortError, RobotBusyError,
        NoSdpAnswerError, DataChannelTimeoutError,
    )
    _NEW_LIB_ERRORS = True
except ImportError:
    # 旧库降级：用占位类避免 isinstance 报错；除 Exception 之外永远不会被命中
    class _Placeholder(Exception):
        pass
    AesKeyRequiredError = AesKeyRejectedError = _Placeholder
    LocalSignalingPortError = RobotBusyError = _Placeholder
    NoSdpAnswerError = DataChannelTimeoutError = _Placeholder
    _NEW_LIB_ERRORS = False

# ──────────────────────────────────────────────────────────
# 日志系统：同时输出到控制台 + 滚动日志文件
# ──────────────────────────────────────────────────────────
_LOG_DIR  = os.path.join(APP_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

# 根 logger
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)

# ---- 屏蔽第三方库的高频噪音 ----
for _noisy in ("aiortc", "aioice", "asyncio", "urllib3",
               "urllib3.connectionpool", "websockets"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ---- 过滤器：屏蔽高频重复消息（心跳/摇杆/lowstate）----
class _NoiseFilter(logging.Filter):
    _SKIP = (
        "> message sent:",           # 摇杆/心跳每100ms发一次
        "Received message on data channel:",  # lowstate 完整 JSON
        "电量=",                      # 每次 lowstate 都打
    )
    # 编排播放期间临时开启 verbose，把摇杆/数据通道收发都打出来用于排查
    _VERBOSE = False

    @classmethod
    def set_verbose(cls, on: bool):
        cls._VERBOSE = bool(on)

    def filter(self, record: logging.LogRecord) -> bool:
        if _NoiseFilter._VERBOSE:
            return True
        msg = record.getMessage()
        return not any(s in msg for s in self._SKIP)


def set_playback_verbose_logging(on: bool):
    """编排播放时临时把摇杆/数据通道收发等高频日志放出来，便于诊断。"""
    _NoiseFilter.set_verbose(on)
    logger.info("[playback verbose] %s", "ON" if on else "OFF")

# ---- 文件 handler（带滚动：单个文件最大 5MB，最多保留 5 个）----
_fh = logging.handlers.RotatingFileHandler(
    _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5,
    encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"))
_fh.addFilter(_NoiseFilter())
_root_logger.addHandler(_fh)

# ---- 控制台 handler（WARNING 及以上）----
_ch = logging.StreamHandler(sys.stdout)
_ch.setLevel(logging.WARNING)
_ch.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"))
_root_logger.addHandler(_ch)

logger = logging.getLogger("unitree.backend")
logger.info("=" * 60)
logger.info("Unitree 多机器人控制台 启动  log→%s", _LOG_FILE)
logger.info("=" * 60)


# ──────────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────────
ROBOT_TYPE_GO2 = "go2"
ROBOT_TYPE_G1  = "g1"

STATUS_CONNECTING    = "connecting"
STATUS_CONNECTED     = "connected"
STATUS_DISCONNECTED  = "disconnected"
STATUS_RECONNECTING  = "reconnecting"
STATUS_ERROR         = "error"

GO2_SN_PREFIXES = ("B42D",)
G1_SN_PREFIXES  = ("B42F", "G100", "G1")

# G1 手臂动作
G1_ARM_ACTIONS = [
    (27, "握手"),
    (18, "击掌"),
    (19, "拥抱"),
    (26, "高挥手"),
    (17, "鼓掌"),
    (25, "脸旁挥手"),
    (12, "左飞吻"),
    (20, "手心爱心"),
    (21, "右爱心"),
    (15, "双手举起"),
    (24, "X光造型"),
    (23, "右手举起"),
    (22, "拒绝"),
    (99, "收手/取消"),
]

# G1 运动模式
G1_MOVE_MODES = [
    (500, "走路"),
    (501, "走路(腰控)"),
    (801, "跑步"),
]

# Go2 动作分组
GO2_ACTIONS: Dict[str, List[tuple]] = {
    "基本姿态": [
        (SPORT_CMD["RecoveryStand"], "归正"),
        (SPORT_CMD["StandUp"],       "正常站立"),
        (SPORT_CMD["StandDown"],     "趴下"),
        (SPORT_CMD["Sit"],           "坐下"),
        (SPORT_CMD["BalanceStand"],  "平衡站"),
        (SPORT_CMD["StopMove"],      "停止移动"),
        (SPORT_CMD["Damp"],          "阻尼模式"),
    ],
    "舞蹈动作": [
        (SPORT_CMD["Dance1"],        "舞蹈1"),
        (SPORT_CMD["Dance2"],        "舞蹈2"),
        (SPORT_CMD["WiggleHips"],    "扭臀"),
        (SPORT_CMD["MoonWalk"],      "太空步"),
        (SPORT_CMD["CrossStep"],     "交叉步"),
        (SPORT_CMD["OnesidedStep"],  "单侧步"),
        (SPORT_CMD["Bound"],         "跳跃奔跑"),
    ],
    "高难特技": [
        (SPORT_CMD["FrontFlip"],    "前空翻"),
        (SPORT_CMD["BackFlip"],     "后空翻"),
        (SPORT_CMD["LeftFlip"],     "左空翻"),
        (SPORT_CMD["RightFlip"],    "右空翻"),
        (SPORT_CMD["FrontJump"],    "向前跳"),
        (SPORT_CMD["FrontPounce"],  "前扑"),
        (SPORT_CMD["Handstand"],    "倒立"),
    ],
    "互动动作": [
        (SPORT_CMD["Hello"],        "打招呼"),
        (SPORT_CMD["Stretch"],      "伸展"),
        (SPORT_CMD["FingerHeart"],  "比心"),
        (SPORT_CMD["Wallow"],       "打滚"),
        (SPORT_CMD["Scrape"],       "挠头"),
        (SPORT_CMD["Content"],      "满足"),
        (SPORT_CMD["Pose"],         "造型"),
        (SPORT_CMD["RiseSit"],      "坐立"),
    ],
}

VUI_COLORS = [
    (VUI_COLOR.WHITE,  "白"),
    (VUI_COLOR.RED,    "红"),
    (VUI_COLOR.YELLOW, "黄"),
    (VUI_COLOR.BLUE,   "蓝"),
    (VUI_COLOR.GREEN,  "绿"),
    (VUI_COLOR.CYAN,   "青"),
    (VUI_COLOR.PURPLE, "紫"),
]


# ──────────────────────────────────────────────────────────
# ConfigManager — 保存 / 读取用户配置
# ──────────────────────────────────────────────────────────
class ConfigManager:
    """
    持久化配置到 ~/.unitree_multicontrol/config.json。
    包含两类数据：
      saved_entries  — 自动扫描用的 SN 列表（原有）
      saved_robots   — 用户手动/扫描添加的完整机器人配置，供快速重连
    """

    DEFAULT_PATH = os.path.join(os.path.expanduser("~"),
                                ".unitree_multicontrol", "config.json")

    def __init__(self, path: Optional[str] = None):
        self._path = path or self.DEFAULT_PATH
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data: dict = self._load()
        logger.info("ConfigManager 初始化，配置文件：%s", self._path)

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info("加载配置成功，saved_robots=%d",
                                len(data.get("saved_robots", [])))
                    return data
            except Exception as e:
                logger.warning("配置文件损坏，重置：%s", e)
        return {"saved_entries": [], "saved_robots": []}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.debug("配置已写入 %s", self._path)
        except Exception as e:
            logger.error("保存配置失败: %s", e)

    # ---- SN 扫描列表（供 AutoAddDialog）----
    def get_saved_entries(self) -> List[dict]:
        return list(self._data.get("saved_entries", []))

    def save_entry(self, sn: str, name: str = "", token: str = "",
                   robot_type: str = ROBOT_TYPE_GO2):
        entries = self._data.setdefault("saved_entries", [])
        for e in entries:
            if e.get("sn") == sn:
                e.update(name=name, token=token, robot_type=robot_type)
                self._save()
                return
        entries.append(dict(sn=sn, name=name, token=token, robot_type=robot_type))
        self._save()

    def replace_saved_entries(self, sns: List[str]):
        """用文本框当前内容完整替换 saved_entries，多余的会被删除。"""
        def _detect(sn: str) -> str:
            if any(sn.upper().startswith(p) for p in G1_SN_PREFIXES):
                return ROBOT_TYPE_G1
            return ROBOT_TYPE_GO2

        new_entries = []
        for sn in sns:
            # 保留旧条目中已有的额外字段（name/token），仅补全缺失
            old = next((e for e in self._data.get("saved_entries", [])
                        if e.get("sn") == sn), {})
            new_entries.append(dict(
                sn=sn,
                robot_type=old.get("robot_type", _detect(sn)),
                name=old.get("name", ""),
                token=old.get("token", ""),
            ))
        self._data["saved_entries"] = new_entries
        logger.info("覆盖保存 SN 列表：%s", sns)
        self._save()

    def remove_saved_entry_by_sn(self, sn: str):
        entries = self._data.get("saved_entries", [])
        before = len(entries)
        self._data["saved_entries"] = [e for e in entries if e.get("sn") != sn]
        if len(self._data["saved_entries"]) < before:
            logger.info("删除已保存 SN 条目：%s", sn)
            self._save()

    # ---- 完整机器人配置（供快速重连）----
    def get_saved_robots(self) -> List[dict]:
        """
        返回已保存的完整机器人配置列表。
        每项格式：{cfg_id, name, robot_type, ip, sn, token, aes_128_key}
        老配置缺 aes_128_key 字段默认空串（即按老固件处理）。
        """
        return list(self._data.get("saved_robots", []))

    def save_robot(self, name: str, robot_type: str,
                   ip: Optional[str], sn: Optional[str], token: str = "",
                   aes_128_key: str = "") -> str:
        """
        保存一条机器人配置，若 ip+name 或 sn 已存在则更新。
        返回 cfg_id（内部唯一 ID，与 RobotManager 的 robot_id 无关）。

        注意：aes_128_key 传空串时**不会覆盖**已保存的旧值，避免扫描添加等
        路径误删用户之前手动获取的密钥。要清空请用 update_saved_robot_aes_key。
        """
        robots = self._data.setdefault("saved_robots", [])
        # 同 SN 视为同一台
        for r in robots:
            if sn and r.get("sn") == sn:
                update = dict(name=name, robot_type=robot_type,
                              ip=ip, token=token)
                if aes_128_key:
                    update["aes_128_key"] = aes_128_key
                r.update(update)
                self._save()
                logger.info("更新已保存机器人：%s (SN=%s)", name, sn)
                return r["cfg_id"]
            if not sn and ip and r.get("ip") == ip and r.get("name") == name:
                update = dict(robot_type=robot_type, token=token)
                if aes_128_key:
                    update["aes_128_key"] = aes_128_key
                r.update(update)
                self._save()
                logger.info("更新已保存机器人：%s (IP=%s)", name, ip)
                return r["cfg_id"]

        cfg_id = uuid.uuid4().hex[:8]
        robots.append(dict(cfg_id=cfg_id, name=name, robot_type=robot_type,
                           ip=ip, sn=sn, token=token,
                           aes_128_key=aes_128_key))
        self._save()
        logger.info("新保存机器人：%s (cfg_id=%s, IP=%s, SN=%s)",
                    name, cfg_id, ip, sn)
        return cfg_id

    def update_saved_robot_aes_key(self, cfg_id: str, aes_128_key: str):
        """单独更新某台机器人的 AES-128 密钥（用于「编辑 AES 密钥」入口）。"""
        robots = self._data.get("saved_robots", [])
        for r in robots:
            if r.get("cfg_id") == cfg_id:
                r["aes_128_key"] = aes_128_key
                self._save()
                logger.info("更新机器人 AES 密钥 cfg_id=%s", cfg_id)
                return True
        return False

    # ── 宇树云端登录记忆（只存邮箱，密码绝不持久化）──
    def get_unitree_email(self) -> str:
        return self._data.get("unitree_email", "")

    def set_unitree_email(self, email: str):
        self._data["unitree_email"] = email
        self._save()

    # ── 命名配置：一次性保存当前列表的所有机器人（含 IP / AES 密钥），
    # 之后用「配置连接」一键把整个配置加回来。结构：
    #     saved_configs: [
    #         {"name": "客厅3只", "created_at": 1716...,
    #          "robots": [{name, robot_type, ip, sn, token, aes_128_key}, ...]},
    #         ...
    #     ]
    def get_saved_configs(self) -> List[dict]:
        return list(self._data.get("saved_configs", []))

    def save_config(self, name: str, robots: List[dict]) -> bool:
        """保存或覆盖一个命名配置。robots 里每项至少包含 ip + robot_type，
        建议同时附带 name / sn / aes_128_key / token。"""
        if not name:
            return False
        configs = self._data.setdefault("saved_configs", [])
        entry = dict(name=name, created_at=int(time.time()),
                     robots=list(robots))
        for i, c in enumerate(configs):
            if c.get("name") == name:
                configs[i] = entry
                self._save()
                logger.info("覆盖配置：%s（%d 台机器人）", name, len(robots))
                return True
        configs.append(entry)
        self._save()
        logger.info("新增配置：%s（%d 台机器人）", name, len(robots))
        return True

    def delete_saved_config(self, name: str) -> bool:
        configs = self._data.get("saved_configs", [])
        before = len(configs)
        self._data["saved_configs"] = [c for c in configs if c.get("name") != name]
        if len(self._data["saved_configs"]) < before:
            self._save()
            logger.info("删除配置：%s", name)
            return True
        return False

    def remove_saved_robot(self, cfg_id: str):
        robots = self._data.get("saved_robots", [])
        before = len(robots)
        self._data["saved_robots"] = [r for r in robots if r.get("cfg_id") != cfg_id]
        if len(self._data["saved_robots"]) < before:
            logger.info("删除已保存机器人 cfg_id=%s", cfg_id)
        self._save()

    def remove_robot_by_sn(self, sn: str):
        """删除 saved_robots 中对应 SN 的记录（保留 saved_entries）"""
        robots = self._data.get("saved_robots", [])
        before = len(robots)
        self._data["saved_robots"] = [r for r in robots if r.get("sn") != sn]
        if len(self._data["saved_robots"]) < before:
            logger.info("删除已保存机器人 SN=%s", sn)
        self._save()

    def clear_saved_robots(self):
        self._data["saved_robots"] = []
        self._save()
        logger.info("已清空所有保存的机器人配置")

    @property
    def config_path(self) -> str:
        return self._path


# ──────────────────────────────────────────────────────────
# RobotInfo — 单台机器人的数据模型
# ──────────────────────────────────────────────────────────
class RobotInfo:
    def __init__(self, robot_id: str, name: str, robot_type: str,
                 ip: Optional[str] = None, sn: Optional[str] = None,
                 token: str = "", aes_128_key: str = ""):
        self.id         = robot_id
        self.name       = name
        self.robot_type = robot_type
        self.ip         = ip
        self.sn         = sn
        self.token      = token
        # 新固件 (data2=3) 的 per-device AES-128 key（32 位十六进制字符串）
        self.aes_128_key = aes_128_key
        self.status     = STATUS_DISCONNECTED
        self.battery: Optional[int] = None
        self.error_msg  = ""
        self.conn: Optional[UnitreeWebRTCConnection] = None
        # 对应的 ConfigManager cfg_id（可选，已保存的机器人才有）
        self.cfg_id: Optional[str] = None
        # Go2 姿态标记：趴下/坐下/站立等姿态指令后置 True，
        # 下次摇杆移动前自动发 RecoveryStand 恢复行走模式
        self.needs_recovery: bool = False
        # 对讲通话状态：True = 正在双向音频通话
        self.audio_active: bool = False

    @property
    def is_go2(self) -> bool:
        return self.robot_type == ROBOT_TYPE_GO2

    @property
    def is_g1(self) -> bool:
        return self.robot_type == ROBOT_TYPE_G1

    @property
    def display_name(self) -> str:
        prefix = "🐕" if self.is_go2 else "🤖"
        return f"{prefix} {self.name}"


# ──────────────────────────────────────────────────────────
# RobotManager — 核心后台管理器
# ──────────────────────────────────────────────────────────
class RobotManager(QObject):
    """
    在后台 asyncio 线程中管理所有机器人的 WebRTC 连接。
    通过 Qt 信号向 UI 报告状态变化，完全线程安全。
    """

    # ── Qt 信号 ──
    robot_added           = pyqtSignal(str)           # robot_id
    robot_removed         = pyqtSignal(str)           # robot_id
    robot_status_changed  = pyqtSignal(str, str, str) # id, status, error_msg
    robot_battery_updated = pyqtSignal(str, int)      # id, battery_%
    scan_progress         = pyqtSignal(str)           # 进度文字
    scan_finished         = pyqtSignal(dict)          # sn -> ip
    command_result        = pyqtSignal(str, bool, str) # id, ok, msg
    log_message           = pyqtSignal(str)           # UI 日志（带时间戳）
    audio_list_result     = pyqtSignal(str, list)     # robot_id, [{name, uuid}, ...]
    audio_upload_progress = pyqtSignal(str, int, int)  # robot_id, current, total
    audio_upload_done     = pyqtSignal(str, bool, str) # robot_id, ok, msg
    audio_call_changed    = pyqtSignal(str, bool)      # robot_id, active

    # 执行后会脱离行走模式的 sport 指令 api_id 集合。
    # 发送这些指令后，需要在下次摇杆移动前先发 RecoveryStand 恢复行走。
    _POSTURE_BREAK_CMDS = {
        SPORT_CMD["StandDown"],      # 趴下
        SPORT_CMD["StandUp"],        # 站立（非行走姿态）
        SPORT_CMD["Sit"],            # 坐下
        SPORT_CMD["BalanceStand"],   # 平衡站
        SPORT_CMD["Damp"],           # 阻尼模式
        SPORT_CMD["RiseSit"],        # 坐立
        # 动作与舞蹈类（执行后会导致无法行走，需要自动恢复）
        SPORT_CMD["Dance1"],
        SPORT_CMD["Dance2"],
        SPORT_CMD["Hello"],
        SPORT_CMD["Stretch"],
        SPORT_CMD["Wallow"],
        SPORT_CMD["Pose"],
        SPORT_CMD["Scrape"],
        SPORT_CMD["FrontFlip"],
        SPORT_CMD["LeftFlip"],
        SPORT_CMD["RightFlip"],
        SPORT_CMD["BackFlip"],
        SPORT_CMD["FrontJump"],
        SPORT_CMD["FrontPounce"],
        SPORT_CMD["WiggleHips"],
        SPORT_CMD["FingerHeart"],
        SPORT_CMD["Bound"],
        SPORT_CMD["MoonWalk"],
        SPORT_CMD["OnesidedStep"],
        SPORT_CMD["CrossStep"],
        SPORT_CMD["Handstand"],
        SPORT_CMD["StandOut"],
    }

    def __init__(self, parent: Optional[QObject] = None,
                 config: Optional["ConfigManager"] = None):
        super().__init__(parent)
        self._robots: Dict[str, RobotInfo] = {}
        self._config = config
        self._lock   = threading.Lock()
        # 按 IP/SN 键追踪正在清理中的旧连接，避免删除后立即重新连接时端口冲突
        self._pending_cleanup: Dict[str, object] = {}
        # 看门狗代际编号：每次新建看门狗时递增，旧看门狗检测到不匹配后自动退出
        self._watchdog_gen: Dict[str, int] = {}
        # 录制钩子：(event, robot_ids, **kw) 可选回调
        self._rec_hook = None

        self._loop   = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="UnitreeAsyncLoop")
        self._thread.start()

        # 对讲桥（懒加载：第一次 start_call 时才真正打开音频设备）
        self._audio_bridge = None  # type: Optional["AudioBridge"]
        self._audio_bridge_err: str = ""

    # ── 事件循环线程 ──
    def _run_loop(self):
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            # 优雅地清理所有的异步生成器和悬空任务，确保底层连接完全释放
            tasks = asyncio.all_tasks(self._loop)
            for t in tasks:
                t.cancel()
            if tasks:
                self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            if hasattr(self._loop, "shutdown_default_executor"):
                self._loop.run_until_complete(self._loop.shutdown_default_executor())
            self._loop.close()

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def shutdown(self):
        logger.info("RobotManager 关闭，断开所有连接…")
        # 关掉对讲桥（关闭麦克风/扬声器流 + 各 track）
        if self._audio_bridge is not None:
            try:
                self._audio_bridge.shutdown()
            except Exception as e:
                logger.debug("AudioBridge.shutdown 异常：%s", e)
        future = self._submit(self._disconnect_all())
        try:
            future.result(timeout=3.0)   # 最多等 3 秒让断开完成
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    async def _disconnect_all(self):
        tasks = [r.conn.disconnect()
                 for r in self._robots.values() if r.conn]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── 日志辅助 ──
    def _log(self, msg: str, level: str = "info"):
        ts = time.strftime("%H:%M:%S")
        ui_msg = f"[{ts}] {msg}"
        getattr(logger, level)(msg)
        self.log_message.emit(ui_msg)

    def log_user_action(self, action: str, detail: str = ""):
        """从 UI 线程记录用户操作（点击按钮等）。"""
        full = f"[用户操作] {action}" + (f" | {detail}" if detail else "")
        logger.info(full)
        ts = time.strftime("%H:%M:%S")
        self.log_message.emit(f"[{ts}] {full}")

    # ── 公开 API（Qt 线程调用）──

    @property
    def robots(self) -> Dict[str, RobotInfo]:
        return self._robots

    def get_robot(self, robot_id: str) -> Optional[RobotInfo]:
        return self._robots.get(robot_id)

    def add_robot(self, name: str, robot_type: str,
                  ip: Optional[str] = None,
                  sn: Optional[str] = None,
                  token: str = "",
                  cfg_id: Optional[str] = None,
                  aes_128_key: str = "") -> str:
        """添加机器人并开始连接，返回 robot_id。"""
        robot_id = uuid.uuid4().hex[:8]
        robot = RobotInfo(robot_id, name, robot_type, ip=ip, sn=sn,
                          token=token, aes_128_key=aes_128_key)
        robot.status = STATUS_CONNECTING
        robot.cfg_id = cfg_id
        with self._lock:
            self._robots[robot_id] = robot
        logger.info("添加机器人：name=%s type=%s ip=%s sn=%s robot_id=%s",
                    name, robot_type, ip, sn, robot_id)
        self.robot_added.emit(robot_id)
        self._submit(self._connect_robot(robot_id))
        return robot_id

    def remove_robot(self, robot_id: str):
        # 若正在通话，先解注册对讲（在删除之前，因为需要 conn 引用来 removeTrack）
        pre = self._robots.get(robot_id)
        if pre and pre.audio_active and self._audio_bridge is not None:
            try:
                self._audio_bridge.unregister_call(robot_id)
            except Exception as e:
                logger.debug("remove_robot: unregister_call 异常：%s", e)
            pre.audio_active = False
            self.audio_call_changed.emit(robot_id, False)

        with self._lock:
            robot = self._robots.pop(robot_id, None)
        if robot:
            logger.info("删除机器人：%s (robot_id=%s)", robot.name, robot_id)
            # 使旧看门狗失效
            self._watchdog_gen.pop(robot_id, None)
            if robot.conn:
                # 按 IP/SN 登记"清理中"，让后续同 IP 连接等待清理完成
                cleanup_key = robot.ip or robot.sn or robot_id
                self._pending_cleanup[cleanup_key] = robot.conn
                self._submit(self._cleanup_conn_async(cleanup_key, robot.conn))
        self.robot_removed.emit(robot_id)

    async def _cleanup_conn_async(self, cleanup_key: str, conn):
        """等待旧连接完全断开后，从 pending_cleanup 中移除。"""
        try:
            await conn.disconnect()
            logger.info("旧连接已释放 [key=%s]", cleanup_key)
        except Exception as e:
            logger.debug("旧连接清理异常 [%s]: %s", cleanup_key, e)
        finally:
            self._pending_cleanup.pop(cleanup_key, None)

    def reconnect_robot(self, robot_id: str):
        robot = self._robots.get(robot_id)
        if robot:
            logger.info("手动重连：%s", robot.name)
            robot.status = STATUS_RECONNECTING
            self.robot_status_changed.emit(robot_id, STATUS_RECONNECTING, "")
            self._submit(self._attempt_reconnect(robot_id, max_attempts=5))

    def set_recording_hook(self, hook):
        """注册录制钩子。hook(event, robot_ids, **kw) 将在每次发送指令时被调用。"""
        self._rec_hook = hook

    def clear_recording_hook(self):
        self._rec_hook = None

    def send_sport_cmd(self, robot_ids: List[str], api_id: int,
                       parameter: Optional[dict] = None):
        """向指定 Go2 机器人发送运动指令（每个 robot 独立 options 对象）。"""
        if self._rec_hook:
            self._rec_hook("sport", list(robot_ids), api_id=api_id)
        self._submit(self._send_sport_cmd_async(
            list(robot_ids), api_id,
            dict(parameter) if parameter else None))

    def send_sport_cmd_fire_and_forget(self, robot_ids: List[str], api_id: int,
                                       parameter: Optional[dict] = None):
        """
        发射后不管版 sport 指令，不等待机器人回复。
        专为编排播放设计：避免 publish_request_new 阻塞 18 秒等待舞蹈响应。
        """
        self._submit(self._send_sport_cmd_ff_async(
            list(robot_ids), api_id,
            dict(parameter) if parameter else None))

    def send_joystick(self, robot_ids: List[str],
                      lx: float, ly: float, rx: float, ry: float = 0.0):
        if self._rec_hook:
            self._rec_hook("joystick", list(robot_ids), lx=lx, ly=ly, rx=rx, ry=ry)
        self._submit(self._send_joystick_async(list(robot_ids), lx, ly, rx, ry))

    def emergency_stop_robots(self, robot_ids: List[str]):
        """立即停止（发零值摇杆 + Go2 StopMove），优先级最高。"""
        logger.info("🚨 紧急停止 → %s", robot_ids)
        self._submit(self._emergency_stop_async(list(robot_ids)))

    def emergency_stop_all(self):
        """紧急停止所有已连接机器人（编排播放器急停用）。"""
        all_ids = [
            rid for rid, r in self._robots.items()
            if r.status == STATUS_CONNECTED
        ]
        if all_ids:
            logger.info("🚨 全体紧急停止 → %d 台", len(all_ids))
            self._submit(self._emergency_stop_async(all_ids))
        else:
            logger.info("🚨 全体紧急停止：当前无已连接机器人")

    def stop_choreography(self, robot_ids: List[str]):
        """编排结束/停止的收尾指令：强制中断舞蹈 + 恢复可控移动。

        Go2 的 StopMove API 只能停"移动"，不能中断正在播放的舞蹈动画。
        真正的办法是切 MOTION_SWITCHER 重置状态机，然后 RecoveryStand
        把机器狗带回站立姿态，让它重新能接收摇杆指令。
        """
        logger.info("[编排] 收尾停止 → %s", robot_ids)
        self._submit(self._stop_choreography_async(list(robot_ids)))

    def send_g1_arm_action(self, robot_ids: List[str], action_data: int):
        if self._rec_hook:
            self._rec_hook("arm", list(robot_ids), action_data=action_data)
        self._submit(self._send_g1_arm_action_async(list(robot_ids), action_data))

    def send_g1_switch_mode(self, robot_ids: List[str], mode_data: int):
        if self._rec_hook:
            self._rec_hook("g1_mode", list(robot_ids), mode_data=mode_data)
        self._submit(self._send_g1_switch_mode_async(list(robot_ids), mode_data))

    def send_vui_color(self, robot_ids: List[str], color: str, duration: int = 5):
        self._submit(self._send_go2_vui_async(
            list(robot_ids), 1007, {"color": color, "time": duration}))

    def send_vui_brightness(self, robot_ids: List[str], level: int):
        self._submit(self._send_go2_vui_async(
            list(robot_ids), 1005, {"brightness": level}))

    def send_motion_mode(self, robot_ids: List[str], mode: str):
        self._submit(self._send_go2_motion_mode_async(list(robot_ids), mode))

    # ── 音频控制（AudioHub）──

    def fetch_audio_list(self, robot_id: str):
        """获取指定机器人上的音频列表（结果通过 audio_list_result 信号返回）。"""
        self._submit(self._fetch_audio_list_async(robot_id))

    def play_audio(self, robot_ids: List[str], audio_uuid: str, audio_name: str):
        """在指定机器人上播放音频。"""
        self._submit(self._play_audio_async(list(robot_ids), audio_uuid, audio_name))

    def pause_audio(self, robot_ids: List[str]):
        """暂停音频播放。"""
        self._submit(self._pause_audio_async(list(robot_ids)))

    def resume_audio(self, robot_ids: List[str]):
        """恢复音频播放。"""
        self._submit(self._resume_audio_async(list(robot_ids)))

    def upload_audio(self, robot_id: str, file_path: str):
        """上传音频文件到机器人（MP3 自动转 WAV）。"""
        self._submit(self._upload_audio_async(robot_id, file_path))

    def stream_audio_file(self, robot_ids: List[str], file_path: str):
        """用 megaphone 模式把本地音频文件流式推送到机器人播放。"""
        self._submit(self._stream_audio_file_async(
            list(robot_ids), file_path))

    def stop_stream_audio(self, robot_ids: List[str]):
        """停止 megaphone 音频流。"""
        self._submit(self._stop_stream_audio_async(list(robot_ids)))

    # ── 双向对讲 (WebRTC audio) ──────────────────────────────────

    def _ensure_audio_bridge(self):
        """懒加载 AudioBridge；返回 (bridge, err_msg)。"""
        if self._audio_bridge is not None:
            return self._audio_bridge, ""
        if self._audio_bridge_err:
            return None, self._audio_bridge_err
        try:
            from audio_bridge import AudioBridge  # 延迟导入，避免启动即失败
            self._audio_bridge = AudioBridge(self._loop)
            return self._audio_bridge, ""
        except Exception as e:
            msg = f"对讲功能不可用：{e}"
            self._audio_bridge_err = msg
            logger.error(msg)
            return None, msg

    def start_call(self, robot_id: str):
        """开启该机器人的双向音频通话。仅 Go2 支持（G1 未验证）。
        UI 层用 audio_call_changed 信号监听状态；错误通过 command_result 报。"""
        robot = self._robots.get(robot_id)
        if not robot:
            return
        if not robot.is_go2:
            self.command_result.emit(robot_id, False, "对讲当前仅支持 Go2")
            return
        if robot.status != STATUS_CONNECTED or not robot.conn:
            self.command_result.emit(robot_id, False, "机器人未连接，无法开启对讲")
            return
        if robot.audio_active:
            return
        bridge, err = self._ensure_audio_bridge()
        if not bridge:
            self.command_result.emit(robot_id, False, err)
            return
        # 在 asyncio 线程中注册（addTrack 会触发 SDP renegotiation，需要在 loop 上跑）
        self._submit(self._start_call_async(robot_id))

    def stop_call(self, robot_id: str):
        robot = self._robots.get(robot_id)
        if not robot or not robot.audio_active:
            return
        self._submit(self._stop_call_async(robot_id))

    def is_call_active(self, robot_id: str) -> bool:
        r = self._robots.get(robot_id)
        return bool(r and r.audio_active)

    def stop_all_calls(self):
        for rid, r in list(self._robots.items()):
            if r.audio_active:
                self.stop_call(rid)

    def set_mic_muted(self, muted: bool):
        b, _ = self._ensure_audio_bridge()
        if b is not None:
            b.set_mic_muted(muted)

    def is_mic_muted(self) -> bool:
        if self._audio_bridge is None:
            return True
        return self._audio_bridge.is_mic_muted()

    def set_playback_volume(self, v: float):
        b, _ = self._ensure_audio_bridge()
        if b is not None:
            b.set_playback_volume(v)

    def playback_volume(self) -> float:
        if self._audio_bridge is None:
            return 0.6
        return self._audio_bridge.playback_volume()

    async def _start_call_async(self, robot_id: str):
        robot = self._robots.get(robot_id)
        if not robot or not robot.conn:
            return
        try:
            self._audio_bridge.register_call(robot_id, robot.conn)
        except Exception as e:
            logger.exception("register_call 失败 [%s]", robot.name)
            self.command_result.emit(robot_id, False, f"开启对讲失败：{e}")
            return
        robot.audio_active = True
        self._log(f"🎙 [{robot.name}] 开启对讲")
        self.audio_call_changed.emit(robot_id, True)

    async def _stop_call_async(self, robot_id: str):
        robot = self._robots.get(robot_id)
        if not robot:
            return
        try:
            if self._audio_bridge is not None:
                self._audio_bridge.unregister_call(robot_id)
        except Exception as e:
            logger.debug("unregister_call 异常 [%s]：%s", robot.name, e)
        robot.audio_active = False
        self._log(f"🎙 [{robot.name}] 结束对讲")
        self.audio_call_changed.emit(robot_id, False)

    def scan_network(self, timeout: float = 3.0):
        self._submit(self._scan_network_async(timeout))

    @staticmethod
    def detect_type_from_sn(sn: str) -> Optional[str]:
        upper = sn.upper()
        for p in GO2_SN_PREFIXES:
            if upper.startswith(p):
                return ROBOT_TYPE_GO2
        for p in G1_SN_PREFIXES:
            if upper.startswith(p):
                return ROBOT_TYPE_G1
        return None

    # ── 内部异步实现 ──

    async def _connect_robot(self, robot_id: str):
        robot = self._robots.get(robot_id)
        if not robot:
            return
        addr = robot.ip or robot.sn or "?"

        # 等待同 IP/SN 的旧连接清理完成，避免端口冲突（最多等 5 秒）
        cleanup_key = robot.ip or robot.sn or robot_id
        if cleanup_key in self._pending_cleanup:
            self._log(f"⏳ 等待旧连接释放 [{robot.name}]…")
            for _ in range(50):
                if cleanup_key not in self._pending_cleanup:
                    break
                await asyncio.sleep(0.1)
            # 如果超时仍未清理，强制移除并短暂等待
            if cleanup_key in self._pending_cleanup:
                logger.warning("旧连接清理超时，强制继续 [key=%s]", cleanup_key)
                self._pending_cleanup.pop(cleanup_key, None)
                await asyncio.sleep(0.5)

        try:
            self._log(f"⏳ 正在连接 [{robot.name}] ({robot.robot_type}) @ {addr}…")

            aes_key = robot.aes_128_key or None
            if robot.ip:
                conn = UnitreeWebRTCConnection(
                    WebRTCConnectionMethod.LocalSTA, ip=robot.ip,
                    aes_128_key=aes_key)
            elif robot.sn:
                conn = UnitreeWebRTCConnection(
                    WebRTCConnectionMethod.LocalSTA, serialNumber=robot.sn,
                    aes_128_key=aes_key)
            else:
                raise ValueError("没有提供 IP 或 SN，无法连接")

            if robot.token:
                conn.token = robot.token

            await asyncio.wait_for(conn.connect(), timeout=15.0)
            robot.conn = conn

            # 等待数据通道就绪
            await asyncio.sleep(1.2)

            robot.status    = STATUS_CONNECTED
            robot.error_msg = ""
            self._log(f"✅ [{robot.name}] 连接成功！"
                      f"  IP={addr}  type={robot.robot_type}")
            self.robot_status_changed.emit(robot_id, STATUS_CONNECTED, "")

            if robot.is_go2:
                await self._setup_go2_monitoring(robot_id)

            gen = self._watchdog_gen.get(robot_id, 0) + 1
            self._watchdog_gen[robot_id] = gen
            asyncio.ensure_future(self._connection_watchdog(robot_id, gen))

        except asyncio.TimeoutError:
            msg = f"连接超时（15 秒），请检查 {addr} 是否在线"
            self._log(f"❌ [{robot.name}] {msg}", "error")
            self._set_error(robot_id, msg)
        except AesKeyRequiredError:
            msg = ("此机器人为新固件 (data2=3)，需要 AES-128 密钥。"
                   "请右键机器人 → 编辑 AES 密钥，从云端拉取。")
            self._log(f"❌ [{robot.name}] {msg}", "error")
            self._set_error(robot_id, msg)
        except AesKeyRejectedError as e:
            msg = (f"AES 密钥不匹配（机器人重置/重置 SN 后会重新分配）。"
                   f"请重新从云端拉取。详情：{e}")
            self._log(f"❌ [{robot.name}] {msg}", "error")
            self._set_error(robot_id, msg)
        except LocalSignalingPortError as e:
            msg = f"无法连接机器人 9991/8081 端口，请检查电源 / 网络（{e}）"
            self._log(f"❌ [{robot.name}] {msg}", "error")
            self._set_error(robot_id, msg)
        except RobotBusyError:
            msg = "机器人已被其它客户端占用（手机 APP 等），请断开后重试"
            self._log(f"❌ [{robot.name}] {msg}", "error")
            self._set_error(robot_id, msg)
        except (NoSdpAnswerError, DataChannelTimeoutError) as e:
            msg = f"握手超时，机器人可能掉线：{e}"
            self._log(f"❌ [{robot.name}] {msg}", "error")
            self._set_error(robot_id, msg)
        except ConnectionError as e:
            # 库返回的明确连接错误（旧 API / 兜底）
            self._log(f"❌ [{robot.name}] {e}", "error")
            self._set_error(robot_id, str(e))
        except ValueError as e:
            self._log(f"❌ [{robot.name}] 配置错误：{e}", "error")
            self._set_error(robot_id, str(e))
        except Exception as e:
            logger.exception("[%s] 连接异常详情", robot.name)
            self._log(f"❌ [{robot.name}] 连接异常：{type(e).__name__}: {e}", "error")
            self._set_error(robot_id, f"连接失败：{e}")

    def _set_error(self, robot_id: str, msg: str):
        robot = self._robots.get(robot_id)
        if robot:
            robot.status    = STATUS_ERROR
            robot.error_msg = msg
            # 掉线时若正在通话，主动清理，避免 audio track 悬空
            if robot.audio_active and self._audio_bridge is not None:
                try:
                    self._audio_bridge.unregister_call(robot_id)
                except Exception as e:
                    logger.debug("_set_error 中 unregister_call 异常：%s", e)
                robot.audio_active = False
                self.audio_call_changed.emit(robot_id, False)
        self.robot_status_changed.emit(robot_id, STATUS_ERROR, msg)

    async def _setup_go2_monitoring(self, robot_id: str):
        robot = self._robots.get(robot_id)
        if not robot or not robot.conn:
            return

        def _on_low_state(message):
            try:
                data = message.get("data", {})
                bms  = data.get("bms_state", {})
                soc  = bms.get("soc")
                if soc is not None:
                    # 修复P2：处理不同格式的电池值（int/float/str）
                    if isinstance(soc, (int, float)):
                        robot.battery = int(soc)
                    elif isinstance(soc, str) and soc.isdigit():
                        robot.battery = int(soc)
                    else:
                        logger.warning("[%s] 未知电池格式: %s (type=%s)",
                                      robot.name, soc, type(soc))
                        return
                    self.robot_battery_updated.emit(robot_id, robot.battery)
                    logger.debug("[%s] 电量=%d%%", robot.name, robot.battery)
            except Exception as e:
                logger.debug("LOW_STATE 解析错误：%s", e)

        try:
            robot.conn.datachannel.pub_sub.subscribe(
                RTC_TOPIC["LOW_STATE"], _on_low_state)
            logger.info("[%s] 已订阅 LOW_STATE", robot.name)
        except Exception as e:
            logger.warning("[%s] 订阅 LOW_STATE 失败: %s", robot.name, e)

    async def _connection_watchdog(self, robot_id: str, gen: int):
        await asyncio.sleep(5)
        while robot_id in self._robots:
            # 代际检查：如果有新的看门狗产生，旧的自动退出
            if self._watchdog_gen.get(robot_id) != gen:
                logger.debug("[watchdog] robot_id=%s gen=%d 已过期，退出",
                             robot_id, gen)
                return

            robot = self._robots.get(robot_id)
            if not robot:
                break

            if robot.status == STATUS_CONNECTED and robot.conn:
                try:
                    pc = robot.conn.pc
                    if pc and pc.connectionState in ("disconnected", "failed", "closed"):
                        msg = f"WebRTC 连接中断（{pc.connectionState}）"
                        self._log(f"⚠️ [{robot.name}] {msg}，启动自动重连…", "warning")
                        robot.status    = STATUS_RECONNECTING
                        robot.error_msg = msg
                        self.robot_status_changed.emit(
                            robot_id, STATUS_RECONNECTING, msg)
                        await self._attempt_reconnect(robot_id)
                        return
                except Exception as e:
                    logger.debug("[%s] watchdog 检查异常: %s", robot.name, e)

            await asyncio.sleep(5)

    async def _attempt_reconnect(self, robot_id: str, max_attempts: int = 3):
        robot = self._robots.get(robot_id)
        if not robot:
            return

        for attempt in range(1, max_attempts + 1):
            if robot_id not in self._robots:
                return

            msg = f"重连中 ({attempt}/{max_attempts})…"
            self._log(f"🔄 [{robot.name}] {msg}", "info")
            robot.status    = STATUS_RECONNECTING
            robot.error_msg = msg
            self.robot_status_changed.emit(robot_id, STATUS_RECONNECTING, msg)

            try:
                if not robot.ip and robot.sn:
                    scanned = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: _do_multicast_scan(2.0))
                    if robot.sn in scanned:
                        new_ip = scanned[robot.sn]
                        logger.info("[%s] 重扫到新 IP=%s", robot.name, new_ip)
                        robot.ip   = new_ip
                        robot.conn = None
                        # 持久化新 IP（ConfigManager 由外部持有，这里仅更新内存）
                        if hasattr(self, '_config') and self._config:
                            self._config.save_robot(
                                name=robot.name,
                                robot_type=robot.robot_type,
                                ip=new_ip,
                                sn=robot.sn
                            )

                if robot.conn:
                    # 如果底层 PC 已彻底关闭，直接创建新连接（不能 reconnect 死连接）
                    pc_state = None
                    try:
                        pc = robot.conn.pc
                        pc_state = pc.connectionState if pc else None
                    except Exception:
                        pass
                    if pc_state in ("failed", "closed"):
                        logger.info("[%s] 旧连接已死（%s），创建新连接", robot.name, pc_state)
                        try:
                            await robot.conn.disconnect()
                        except Exception:
                            pass
                        robot.conn = None
                        await self._connect_robot(robot_id)
                        # _connect_robot 内部处理了异常，检查结果决定是否重试
                        if robot.status == STATUS_CONNECTED:
                            return
                        raise ConnectionError("新建连接失败")
                    # Bug4 修复：不用 wait_for，直接 await 避免 Future cancelled 问题
                    await robot.conn.reconnect()
                else:
                    await self._connect_robot(robot_id)
                    if robot.status == STATUS_CONNECTED:
                        return
                    raise ConnectionError("新建连接失败")

                robot.status    = STATUS_CONNECTED
                robot.error_msg = ""
                self._log(f"✅ [{robot.name}] 重连成功")
                self.robot_status_changed.emit(robot_id, STATUS_CONNECTED, "")

                if robot.is_go2:
                    await self._setup_go2_monitoring(robot_id)
                gen = self._watchdog_gen.get(robot_id, 0) + 1
                self._watchdog_gen[robot_id] = gen
                asyncio.ensure_future(self._connection_watchdog(robot_id, gen))
                return

            except Exception as e:
                logger.warning("[%s] 重连第 %d 次失败: %s", robot.name, attempt, e)
                await asyncio.sleep(3)

        msg = f"重连 {max_attempts} 次均失败，请检查设备是否在线"
        self._log(f"❌ [{robot.name}] {msg}", "error")
        self._set_error(robot_id, msg)

    # ─────────────── 指令实现 ───────────────
    # ⚠️ 核心规则：
    #   - 不使用 asyncio.wait_for 包裹 publish_request_new！
    #     wait_for 取消协程 → 库内 Future 进入 cancelled 态 →
    #     迟到响应触发 set_result() → InvalidStateError 刷屏。
    #   - 每个机器人独立构建 options dict（不共享对象）。
    #   - 使用 asyncio.gather(return_exceptions=True) 并发发送。

    async def _send_sport_cmd_async(self, robot_ids: List[str], api_id: int,
                                    parameter: Optional[dict]):
        cmd_name = next((k for k, v in SPORT_CMD.items() if v == api_id),
                        str(api_id))
        valid_ids   = []
        valid_names = []
        tasks       = []

        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot:
                logger.warning("send_sport_cmd: robot_id=%s 不存在", robot_id)
                continue
            if not robot.is_go2:
                logger.debug("[%s] 非 Go2，跳过 sport cmd", robot.name)
                continue
            if robot.status != STATUS_CONNECTED:
                self._log(f"⚠️ [{robot.name}] 未连接（状态={robot.status}），"
                          f"跳过指令 [{cmd_name}]", "warning")
                self.command_result.emit(robot_id, False,
                                         f"未连接（{robot.status}）")
                continue
            if not robot.conn:
                logger.warning("[%s] conn 为 None，跳过", robot.name)
                continue

            # 每个机器人独立构建 options dict（避免 dict 被共享/修改）
            opts: dict = {"api_id": api_id}
            if parameter:
                opts["parameter"] = dict(parameter)

            tasks.append(robot.conn.datachannel.pub_sub.publish_request_new(
                topic=RTC_TOPIC["SPORT_MOD"], options=opts))
            valid_ids.append(robot_id)
            valid_names.append(robot.name)

        if not tasks:
            logger.warning("send_sport_cmd [%s]: 没有可发送的目标", cmd_name)
            return

        self._log(f"▶ 发送 [{cmd_name}(api_id={api_id})] → "
                  f"{', '.join(valid_names)}")

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for robot_id, name, result in zip(valid_ids, valid_names, results):
            if isinstance(result, Exception):
                self._log(f"❌ [{name}] 指令 [{cmd_name}] 失败："
                          f"{type(result).__name__}: {result}", "error")
                self.command_result.emit(robot_id, False, str(result))
            else:
                logger.info("[%s] 指令 [%s] 成功，响应：%s",
                            name, cmd_name, result)
                self.command_result.emit(robot_id, True, "")
                # 标记姿态变化：下次摇杆移动前需先 RecoveryStand
                robot = self._robots.get(robot_id)
                if robot and robot.is_go2:
                    if api_id in self._POSTURE_BREAK_CMDS:
                        robot.needs_recovery = True
                    elif api_id == SPORT_CMD["RecoveryStand"]:
                        robot.needs_recovery = False

        # 修复“普通站立后无法移动”的Bug
        # 如果下发的是普通站立 (StandUp) 或者 平衡站，这两个指令会让狗进入静态模式
        # 我们需要在动作完成后，自动帮你补一个 RecoveryStand 把它切回可行走状态。
        if api_id in (SPORT_CMD["StandUp"], SPORT_CMD["BalanceStand"]):
            async def _auto_recover():
                await asyncio.sleep(1.5)  # 等待前置姿态站稳
                # 直接沿用可靠的 UI 按键相同底层的发送逻辑，附带正常接收回执，确保不会被固件降级过滤
                logger.info("后台接力: 准备为 StandUp 发送 RecoveryStand...")
                await self._send_sport_cmd_async(valid_ids, SPORT_CMD["RecoveryStand"], None)
            self._submit(_auto_recover())

    async def _send_sport_cmd_ff_async(self, robot_ids: List[str], api_id: int,
                                       parameter: Optional[dict]):
        """Fire-and-forget: 用 publish_without_callback 发送，不等待回复。"""
        cmd_name = next((k for k, v in SPORT_CMD.items() if v == api_id),
                        str(api_id))
        sent_names = []
        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_go2:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            # 构建与 publish_request_new 相同格式的 payload
            import random as _rnd
            generated_id = int(time.time() * 1000) % 2147483648 + _rnd.randint(0, 1000)
            request_payload = {
                "header": {"identity": {"id": generated_id, "api_id": api_id}},
                "parameter": ""
            }
            if parameter:
                request_payload["parameter"] = json.dumps(parameter) if not isinstance(parameter, str) else parameter
            try:
                robot.conn.datachannel.pub_sub.publish_without_callback(
                    RTC_TOPIC["SPORT_MOD"], request_payload,
                    DATA_CHANNEL_TYPE["REQUEST"])
                sent_names.append(robot.name)
                # 标记姿态变化
                if api_id in self._POSTURE_BREAK_CMDS:
                    robot.needs_recovery = True
                elif api_id == SPORT_CMD["RecoveryStand"]:
                    robot.needs_recovery = False
            except Exception as e:
                logger.warning("[%s] fire-and-forget 发送失败: %s", robot.name, e)

        if api_id in (SPORT_CMD["StandUp"], SPORT_CMD["BalanceStand"]) and sent_names:
            async def _auto_recover_ff():
                await asyncio.sleep(1.5)
                logger.info("后台接力(ff): 准备为 StandUp 发送 RecoveryStand...")
                await self._send_sport_cmd_ff_async(robot_ids, SPORT_CMD["RecoveryStand"], None)
            self._submit(_auto_recover_ff())
        if sent_names:
            self._log(f"▶ 发送(ff) [{cmd_name}(api_id={api_id})] → "
                      f"{', '.join(sent_names)}")

    async def _emergency_stop_async(self, robot_ids: List[str]):
        """紧急停止：零值摇杆 + StopMove + 切换运动模式（强制中断舞蹈动画）。

        StopMove / RecoveryStand 只能停移动，无法中断正在播放的舞蹈。
        真正中断舞蹈的方法是切换 MOTION_SWITCHER 模式，让状态机强制重置。
        """
        payload = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "keys": 0}
        all_tasks  = []   # (robot_id, name, cmd_label, task)
        go2_names  = []

        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            try:
                robot.conn.datachannel.pub_sub.publish_without_callback(
                    RTC_TOPIC["WIRELESS_CONTROLLER"], payload)
            except Exception as e:
                logger.debug("[%s] 紧急停止摇杆失败: %s", robot.name, e)

            if robot.is_go2:
                pub = robot.conn.datachannel.pub_sub
                generated_id = int(time.time() * 1000) & 0x7fffffff
                try:
                    pub.publish_without_callback(
                        RTC_TOPIC["SPORT_MOD"],
                        {"header": {"identity": {"id": generated_id, "api_id": SPORT_CMD["StopMove"]}}})
                    pub.publish_without_callback(
                        RTC_TOPIC["SPORT_MOD"],
                        {"header": {"identity": {"id": generated_id+1, "api_id": SPORT_CMD["BalanceStand"]}}})
                    go2_names.append(robot.name)
                except Exception as e:
                    logger.debug("[%s] 紧急停止运动指令下发失败: %s", robot.name, e)

        if go2_names:
            self._log(f"🚨 紧急停止 StopMove+BalanceStand → {', '.join(go2_names)}")

        # 第二步：切换运动模式以强制中断舞蹈/动画
        # 思路：先切到 "Damp"（阻尼，立即停止一切电机输出），稍等后恢复 "normal"
        mode_tasks = []
        mode_names = []
        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            if robot.is_go2:
                mode_tasks.append(
                    robot.conn.datachannel.pub_sub.publish_request_new(
                        RTC_TOPIC["MOTION_SWITCHER"],
                        {"api_id": 1002, "parameter": {"name": "normal"}}))
                mode_names.append(robot.name)

        if mode_tasks:
            self._log(f"🚨 强制切换运动模式 → normal: {', '.join(mode_names)}")
            results = await asyncio.gather(*mode_tasks, return_exceptions=True)
            for name, result in zip(mode_names, results):
                if isinstance(result, Exception):
                    logger.warning("[%s] 运动模式切换失败: %s", name, result)
                else:
                    logger.info("[%s] 运动模式切换成功", name)

        # 第三步：恢复动作切换（直接通过 fire-and-forget 下发 RecoveryStand）
        await asyncio.sleep(0.3)  # 更短的等待，仅为了确保 mode 切换成功后再发 stand
        stand_names = []
        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            if robot.is_go2:
                try:
                    generated_id = int(time.time() * 1000) & 0x7fffffff
                    robot.conn.datachannel.pub_sub.publish_without_callback(
                        RTC_TOPIC["SPORT_MOD"],
                        {"header": {"identity": {"id": generated_id, "api_id": SPORT_CMD["RecoveryStand"]}}})
                    stand_names.append(robot.name)
                except Exception as e:
                    logger.debug("[%s] RecoveryStand 失败: %s", robot.name, e)

        if stand_names:
            logger.info("紧急停止完成 RecoveryStand → %s", ", ".join(stand_names))
    async def _stop_choreography_async(self, robot_ids: List[str]):
        """编排收尾：强制中断舞蹈 + 恢复站立。相对紧急停止更温和、无日志告警。

        流程（只处理 Go2；G1 暂不支持"停动作"）：
          1) 发一次零摇杆（fire & forget）
          2) StopMove（fire & forget）
          3) 切 MOTION_SWITCHER → normal，强制中断正在播放的舞蹈
          4) 等 300ms 让模式切换生效
          5) RecoveryStand，把机器狗带回可控站立
        """
        go2_robots = []
        for rid in robot_ids:
            r = self._robots.get(rid)
            if r and r.is_go2 and r.status == STATUS_CONNECTED and r.conn:
                go2_robots.append(r)
        if not go2_robots:
            return

        names = [r.name for r in go2_robots]
        self._log(f"⏹ 编排收尾停止 → {', '.join(names)}")

        # 1) 零摇杆
        zero = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "keys": 0}
        for r in go2_robots:
            try:
                r.conn.datachannel.pub_sub.publish_without_callback(
                    RTC_TOPIC["WIRELESS_CONTROLLER"], zero)
            except Exception as e:
                logger.debug("[%s] 收尾零摇杆失败: %s", r.name, e)

        # 2) StopMove（fire & forget，避免阻塞）
        for r in go2_robots:
            try:
                generated_id = int(time.time() * 1000) & 0x7fffffff
                r.conn.datachannel.pub_sub.publish_without_callback(
                    RTC_TOPIC["SPORT_MOD"],
                    {"header": {"identity": {
                         "id": generated_id,
                         "api_id": SPORT_CMD["StopMove"]}}})
            except Exception as e:
                logger.debug("[%s] 收尾 StopMove 失败: %s", r.name, e)

        # 3) 切 normal 模式，强制中断舞蹈动画
        mode_tasks = []
        for r in go2_robots:
            mode_tasks.append(
                r.conn.datachannel.pub_sub.publish_request_new(
                    RTC_TOPIC["MOTION_SWITCHER"],
                    {"api_id": 1002, "parameter": {"name": "normal"}}))
        if mode_tasks:
            results = await asyncio.gather(*mode_tasks, return_exceptions=True)
            for r, result in zip(go2_robots, results):
                if isinstance(result, Exception):
                    logger.warning("[%s] 收尾切 normal 失败: %s", r.name, result)

        # 4) 等模式切换生效
        await asyncio.sleep(0.3)

        # 5) RecoveryStand（fire & forget，让狗恢复站立 & 接受摇杆）
        for r in go2_robots:
            try:
                generated_id = int(time.time() * 1000) & 0x7fffffff
                r.conn.datachannel.pub_sub.publish_without_callback(
                    RTC_TOPIC["SPORT_MOD"],
                    {"header": {"identity": {
                         "id": generated_id,
                         "api_id": SPORT_CMD["RecoveryStand"]}}})
            except Exception as e:
                logger.debug("[%s] 收尾 RecoveryStand 失败: %s", r.name, e)
        logger.info("[编排收尾] 已发送 → %s", ", ".join(names))

    async def _send_joystick_async(self, robot_ids: List[str],
                                   lx: float, ly: float, rx: float, ry: float):
        is_moving = (abs(lx) > 0.01 or abs(ly) > 0.01 or abs(rx) > 0.01)
        # 如果有 Go2 需要恢复行走姿态，先批量发 RecoveryStand
        if is_moving:
            recovery_targets = []
            for robot_id in robot_ids:
                robot = self._robots.get(robot_id)
                if (robot and robot.is_go2 and robot.needs_recovery
                        and robot.status == STATUS_CONNECTED and robot.conn):
                    recovery_targets.append(robot)
            if recovery_targets:
                names_to_recover = [r.name for r in recovery_targets]
                ids_to_recover = [r.id for r in recovery_targets]
                for robot in recovery_targets:
                    robot.needs_recovery = False
                logger.info("摇杆触发自动 RecoveryStand -> %s", ", ".join(names_to_recover))
                # 使用标准的 ff_async 通道，确保发包格式和底层调用与 UI 一致
                self._submit(self._send_sport_cmd_ff_async(ids_to_recover, SPORT_CMD["RecoveryStand"], None))
                # 等待前置姿态站起（从趴下到站立大约需要一定时间，稍微阻塞摇杆一点，后面可连续控制）
                await asyncio.sleep(0.3)
                # 等待机器人完成姿态切换后再发摇杆（摇杆不宜卡太久）
                await asyncio.sleep(0.3)

        payload = {"lx": lx, "ly": ly, "rx": rx, "ry": ry, "keys": 0}
        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            try:
                robot.conn.datachannel.pub_sub.publish_without_callback(
                    RTC_TOPIC["WIRELESS_CONTROLLER"], payload)
            except Exception as e:
                logger.debug("摇杆发送失败 [%s]: %s", robot.name, e)

    async def _send_g1_arm_action_async(self, robot_ids: List[str], action_data: int):
        action_label = next((l for d, l in G1_ARM_ACTIONS if d == action_data),
                            str(action_data))
        valid_ids = []
        valid_names = []
        tasks = []

        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_g1:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                self._log(f"⚠️ [{robot.name}] 未连接，跳过 G1 手臂动作", "warning")
                self.command_result.emit(robot_id, False, f"未连接（{robot.status}）")
                continue
            tasks.append(robot.conn.datachannel.pub_sub.publish_request_new(
                "rt/api/arm/request",
                {"api_id": 7106, "parameter": {"data": action_data}}))
            valid_ids.append(robot_id)
            valid_names.append(robot.name)

        if not tasks:
            return

        self._log(f"▶ G1 手臂动作 [{action_label}({action_data})] → "
                  f"{', '.join(valid_names)}")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for robot_id, name, result in zip(valid_ids, valid_names, results):
            if isinstance(result, Exception):
                self._log(f"❌ [{name}] G1 动作失败：{result}", "error")
                self.command_result.emit(robot_id, False, str(result))
            else:
                logger.info("[%s] G1 动作 [%s] 成功", name, action_label)
                self.command_result.emit(robot_id, True, "")

    async def _send_g1_switch_mode_async(self, robot_ids: List[str], mode_data: int):
        mode_label = next((l for c, l in G1_MOVE_MODES if c == mode_data),
                          str(mode_data))
        valid_ids = []
        valid_names = []
        tasks = []

        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_g1:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            tasks.append(robot.conn.datachannel.pub_sub.publish_request_new(
                "rt/api/sport/request",
                {"api_id": 7101, "parameter": {"data": mode_data}}))
            valid_ids.append(robot_id)
            valid_names.append(robot.name)

        if not tasks:
            return

        self._log(f"▶ G1 切换模式 [{mode_label}({mode_data})] → "
                  f"{', '.join(valid_names)}")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for robot_id, name, result in zip(valid_ids, valid_names, results):
            if isinstance(result, Exception):
                self._log(f"❌ [{name}] 模式切换失败：{result}", "error")
                self.command_result.emit(robot_id, False, str(result))
            else:
                logger.info("[%s] G1 模式切换 [%s] 成功", name, mode_label)
                self.command_result.emit(robot_id, True, "")

    async def _send_go2_vui_async(self, robot_ids: List[str],
                                  api_id: int, parameter: dict):
        valid_ids = []
        valid_names = []
        tasks = []

        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_go2:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            tasks.append(robot.conn.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["VUI"],
                {"api_id": api_id, "parameter": dict(parameter)}))
            valid_ids.append(robot_id)
            valid_names.append(robot.name)

        if not tasks:
            return

        self._log(f"▶ VUI api_id={api_id} {parameter} → {', '.join(valid_names)}")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for robot_id, name, result in zip(valid_ids, valid_names, results):
            if isinstance(result, Exception):
                self._log(f"❌ [{name}] VUI 失败：{result}", "error")
                self.command_result.emit(robot_id, False, str(result))
            else:
                logger.info("[%s] VUI 成功", name)
                self.command_result.emit(robot_id, True, "")

    async def _send_go2_motion_mode_async(self, robot_ids: List[str], mode: str):
        valid_ids = []
        valid_names = []
        tasks = []

        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_go2:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            tasks.append(robot.conn.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["MOTION_SWITCHER"],
                {"api_id": 1001, "parameter": {"name": mode}}))
            valid_ids.append(robot_id)
            valid_names.append(robot.name)

        if not tasks:
            return

        self._log(f"▶ 切换运动模式 [{mode}] → {', '.join(valid_names)}")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for robot_id, name, result in zip(valid_ids, valid_names, results):
            if isinstance(result, Exception):
                self._log(f"❌ [{name}] 运动模式切换失败：{result}", "error")
                self.command_result.emit(robot_id, False, str(result))
            else:
                logger.info("[%s] 运动模式切换 [%s] 成功", name, mode)
                self.command_result.emit(robot_id, True, "")

    # ── 音频控制（AudioHub）内部异步实现 ──

    async def _fetch_audio_list_async(self, robot_id: str):
        robot = self._robots.get(robot_id)
        if not robot or not robot.is_go2:
            return
        if robot.status != STATUS_CONNECTED or not robot.conn:
            self._log(f"⚠️ [{robot.name}] 未连接，无法获取音频列表", "warning")
            return
        try:
            resp = await robot.conn.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["AUDIO_HUB_REQ"],
                {"api_id": AUDIO_API["GET_AUDIO_LIST"],
                 "parameter": json.dumps({})})
            # 解析响应中的音频列表
            audio_list = []
            if isinstance(resp, dict):
                data = resp.get("data", resp)
                if isinstance(data, str):
                    data = json.loads(data)
                # 常见响应格式：{..., "data": {"music_list": [...]}}
                items = (data.get("music_list")
                         or data.get("audio_list")
                         or data.get("list")
                         or [])
                for item in items:
                    if isinstance(item, dict):
                        audio_list.append({
                            "name": item.get("file_name")
                                    or item.get("name", "未知"),
                            "uuid": item.get("unique_id")
                                    or item.get("uuid", ""),
                        })
            logger.info("[%s] 音频列表：%d 首", robot.name, len(audio_list))
            self.audio_list_result.emit(robot_id, audio_list)
        except Exception as e:
            logger.warning("[%s] 获取音频列表失败: %s", robot.name, e)
            self._log(f"❌ [{robot.name}] 获取音频列表失败：{e}", "error")
            self.audio_list_result.emit(robot_id, [])

    async def _audio_hub_cmd_async(self, robot_ids: List[str],
                                   api_id: int, parameter: dict,
                                   label: str):
        """通用 AudioHub 指令发送。"""
        tasks = []
        valid_ids = []
        valid_names = []
        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_go2:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            tasks.append(robot.conn.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["AUDIO_HUB_REQ"],
                {"api_id": api_id,
                 "parameter": json.dumps(parameter)}))
            valid_ids.append(robot_id)
            valid_names.append(robot.name)

        if not tasks:
            return

        self._log(f"♪ {label} → {', '.join(valid_names)}")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for robot_id, name, result in zip(valid_ids, valid_names, results):
            if isinstance(result, Exception):
                self._log(f"❌ [{name}] {label}失败：{result}", "error")
                self.command_result.emit(robot_id, False, str(result))
            else:
                logger.info("[%s] %s 成功", name, label)
                self.command_result.emit(robot_id, True, "")

    async def _play_audio_async(self, robot_ids: List[str],
                                audio_uuid: str, audio_name: str):
        await self._audio_hub_cmd_async(
            robot_ids, AUDIO_API["SELECT_START_PLAY"],
            {"unique_id": audio_uuid}, f"播放音频 [{audio_name}]")

    async def _pause_audio_async(self, robot_ids: List[str]):
        await self._audio_hub_cmd_async(
            robot_ids, AUDIO_API["PAUSE"], {}, "暂停音频")

    async def _resume_audio_async(self, robot_ids: List[str]):
        await self._audio_hub_cmd_async(
            robot_ids, AUDIO_API["UNSUSPEND"], {}, "恢复音频")

    async def _upload_audio_async(self, robot_id: str, file_path: str):
        robot = self._robots.get(robot_id)
        if not robot or not robot.is_go2:
            self.audio_upload_done.emit(robot_id, False, "非 Go2 机器人")
            return
        if robot.status != STATUS_CONNECTED or not robot.conn:
            self.audio_upload_done.emit(robot_id, False, "未连接")
            return

        file_name = os.path.splitext(os.path.basename(file_path))[0]
        self._log(f"♪ 上传音频 [{file_name}] → [{robot.name}]")

        try:
            wav_path = file_path
            # MP3 → WAV 转换（需要 pydub + ffmpeg）
            if file_path.lower().endswith(".mp3"):
                try:
                    from pydub import AudioSegment
                    import os as _os
                    audio = AudioSegment.from_mp3(file_path)
                    audio = audio.set_frame_rate(44100)
                    # 修复P2：使用os.path.splitext解决无扩展名问题
                    base_path = _os.path.splitext(file_path)[0]
                    wav_path = base_path + ".wav"
                    audio.export(wav_path, format="wav",
                                 parameters=["-ar", "44100"])
                    logger.info("[%s] MP3 → WAV 转换完成: %s", robot.name, wav_path)
                except ImportError:
                    self._log(f"❌ MP3 转换需要 pydub 库，请 pip install pydub",
                              "error")
                    self.audio_upload_done.emit(robot_id, False,
                                                "缺少 pydub 库，无法转换 MP3")
                    return

            with open(wav_path, "rb") as f:
                audio_data = f.read()

            file_md5 = hashlib.md5(audio_data).hexdigest()
            b64_data = base64.b64encode(audio_data).decode("utf-8")

            chunk_size = 4096
            chunks = [b64_data[i:i + chunk_size]
                      for i in range(0, len(b64_data), chunk_size)]
            total = len(chunks)
            logger.info("[%s] 上传 %s: %d 块, %.1f KB",
                        robot.name, file_name, total,
                        len(audio_data) / 1024)

            pub = robot.conn.datachannel.pub_sub
            for i, chunk in enumerate(chunks, 1):
                param = {
                    "file_name": file_name,
                    "file_type": "wav",
                    "file_size": len(audio_data),
                    "current_block_index": i,
                    "total_block_number": total,
                    "block_content": chunk,
                    "current_block_size": len(chunk),
                    "file_md5": file_md5,
                    "create_time": int(time.time() * 1000),
                }
                await pub.publish_request_new(
                    RTC_TOPIC["AUDIO_HUB_REQ"],
                    {"api_id": AUDIO_API["UPLOAD_AUDIO_FILE"],
                     "parameter": json.dumps(param, ensure_ascii=True)})
                self.audio_upload_progress.emit(robot_id, i, total)
                await asyncio.sleep(0.05)

            self._log(f"✅ 音频 [{file_name}] 上传完成")
            self.audio_upload_done.emit(robot_id, True, "")
        except Exception as e:
            logger.error("[%s] 上传音频失败: %s", robot.name, e)
            self._log(f"❌ [{robot.name}] 上传音频失败：{e}", "error")
            self.audio_upload_done.emit(robot_id, False, str(e))

    # ── Megaphone 音频流 ──

    async def _stream_audio_file_async(self, robot_ids: List[str],
                                       file_path: str):
        """用 megaphone 模式把本地音频文件流式推到机器人播放。

        流程：enter_megaphone → 分块上传音频 → 自动退出。
        优点：不需要先上传到机器人存储，直接实时播放。
        """
        file_name = os.path.basename(file_path)
        self._log(f"♪ 流式播放 [{file_name}] → {len(robot_ids)} 台机器人")

        wav_path = file_path
        if file_path.lower().endswith(".mp3"):
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_mp3(file_path)
                audio = audio.set_frame_rate(44100)
                wav_path = file_path.rsplit(".", 1)[0] + "_stream.wav"
                audio.export(wav_path, format="wav",
                             parameters=["-ar", "44100"])
            except ImportError:
                self._log("❌ MP3 播放需要 pydub 库（pip install pydub）",
                          "error")
                return

        try:
            with open(wav_path, "rb") as f:
                audio_data = f.read()
        except FileNotFoundError:
            self._log(f"❌ 文件不存在: {wav_path}", "error")
            return

        b64_data = base64.b64encode(audio_data).decode("utf-8")
        chunk_size = 4096
        chunks = [b64_data[i:i + chunk_size]
                  for i in range(0, len(b64_data), chunk_size)]
        total = len(chunks)

        # 对每台机器人分别进入 megaphone 并推送
        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_go2:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            pub = robot.conn.datachannel.pub_sub

            try:
                # 进入 megaphone 模式
                await pub.publish_request_new(
                    RTC_TOPIC["AUDIO_HUB_REQ"],
                    {"api_id": AUDIO_API["ENTER_MEGAPHONE"],
                     "parameter": json.dumps({})})
                logger.info("[%s] 进入 megaphone 模式", robot.name)

                # 分块推送音频
                for i, chunk in enumerate(chunks, 1):
                    param = {
                        "current_block_size": len(chunk),
                        "block_content": chunk,
                        "current_block_index": i,
                        "total_block_number": total,
                    }
                    await pub.publish_request_new(
                        RTC_TOPIC["AUDIO_HUB_REQ"],
                        {"api_id": AUDIO_API["UPLOAD_MEGAPHONE"],
                         "parameter": json.dumps(param, ensure_ascii=True)})
                    if i % 100 == 0 or i == total:
                        self.audio_upload_progress.emit(robot_id, i, total)
                    await asyncio.sleep(0.02)

                logger.info("[%s] megaphone 音频推送完成", robot.name)
                self._log(f"✅ [{robot.name}] 播放完成")
            except Exception as e:
                logger.error("[%s] megaphone 播放失败: %s", robot.name, e)
                self._log(f"❌ [{robot.name}] 播放失败：{e}", "error")

    async def _stop_stream_audio_async(self, robot_ids: List[str]):
        """退出 megaphone 模式，停止音频流。"""
        tasks = []
        names = []
        for robot_id in robot_ids:
            robot = self._robots.get(robot_id)
            if not robot or not robot.is_go2:
                continue
            if robot.status != STATUS_CONNECTED or not robot.conn:
                continue
            tasks.append(
                robot.conn.datachannel.pub_sub.publish_request_new(
                    RTC_TOPIC["AUDIO_HUB_REQ"],
                    {"api_id": AUDIO_API["EXIT_MEGAPHONE"],
                     "parameter": json.dumps({})}))
            names.append(robot.name)

        if tasks:
            self._log(f"♪ 停止音频流 → {', '.join(names)}")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for name, result in zip(names, results):
                if isinstance(result, Exception):
                    logger.warning("[%s] 退出 megaphone 失败: %s", name, result)
                else:
                    logger.info("[%s] 退出 megaphone 成功", name)

    # ── 网络扫描 ──

    async def _scan_network_async(self, timeout: float):
        self.scan_progress.emit("正在扫描局域网设备，请稍候…")
        logger.info("开始网络扫描，timeout=%.1fs", timeout)
        try:
            result: dict = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _do_multicast_scan(timeout))
            logger.info("扫描完成，发现 %d 台设备：%s", len(result), result)
            self.scan_finished.emit(result)
        except Exception as e:
            logger.error("扫描异常：%s", e)
            self.scan_progress.emit(f"扫描出错：{e}")
            self.scan_finished.emit({})


# ──────────────────────────────────────────────────────────
# 多播扫描（纯同步，在 executor 里运行）
# ──────────────────────────────────────────────────────────
def _do_multicast_scan(timeout: float) -> Dict[str, str]:
    """返回 {sn: ip}。兼容 Windows 多网卡。"""
    RECV_PORT       = 10134
    MULTICAST_GROUP = "231.1.1.1"
    MULTICAST_PORT  = 10131
    found: Dict[str, str] = {}

    host_name = socket.gethostname()
    try:
        _, _, ips = socket.gethostbyname_ex(host_name)
    except Exception:
        ips = []
    ips.append("0.0.0.0")

    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listen_sock.bind(("", RECV_PORT))
    except OSError as e:
        logger.error("绑定扫描端口 %d 失败: %s", RECV_PORT, e)
        listen_sock.close()  # 修复P3：socket謂江需要关閭
        return found

    for ip in ips:
        try:
            mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton(ip)
            listen_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except Exception:
            pass

    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    query = b'{"name": "unitree_dapengche"}'

    for ip in ips:
        if ip == "0.0.0.0":
            continue
        try:
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                 socket.inet_aton(ip))
            send_sock.sendto(query, (MULTICAST_GROUP, MULTICAST_PORT))
        except Exception:
            pass

    listen_sock.setblocking(False)
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            data, addr = listen_sock.recvfrom(1024)
            msg = json.loads(data.decode("utf-8"))
            if "sn" in msg:
                sn     = msg["sn"]
                ip_str = msg.get("ip", addr[0])
                if sn not in found:
                    found[sn] = ip_str
                    logger.info("扫描发现设备: SN=%s IP=%s", sn, ip_str)
        except (BlockingIOError, json.JSONDecodeError):
            time.sleep(0.05)
        except Exception:
            break

    listen_sock.close()
    send_sock.close()
    return found
