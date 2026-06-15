# Unitree MultiRobot Control · 宇树多机器人控制台

一个用于**同时控制多台宇树机器人**（Go2 四足、G1 人形）的 PyQt6 桌面应用，通过 WebRTC datachannel 直连，支持 LAN 群控、动作编排和实时录制。

> 🐕🤖 一台电脑、一个界面、N 台机器人。

![PyQt6](https://img.shields.io/badge/PyQt6-6.4+-blue) ![Python](https://img.shields.io/badge/Python-3.10+-green) ![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey) ![License](https://img.shields.io/badge/License-MIT-blue)

---

## ✨ 主要特性

- **多机器人并发**：任意数量 Go2 / G1 混编群控，命令通过 `asyncio.gather` 并发下发
- **新固件支持**：兼容 Go2 ≥ 1.1.15 / G1 ≥ 1.5.1 的 `data2=3` 加密握手；内置宇树账号云端登录一键拉取 AES-128 密钥
- **三种添加方式**：
  - `+ IP 添加`：手动填 IP / SN / AES 密钥
  - `📡 扫描添加`：UDP 多播自动发现局域网内机器人
  - `📂 配置连接`：从已保存的配置一键加载多台机器人
- **配置保存**：当前机器人列表可命名保存，方便不同演出场景一键还原
- **动作编排**：
  - 多轨道时间线编辑器，按位置映射到机器人
  - Go2 sport 动作（含舞蹈、特技）与 G1 手臂/运动模式固定时长，自动避免漂移
  - 支持并行追加多个编排文件
- **实时录制**：抓取用户实时操作（动作、移动、模式切换），自动转成可重放的 `ChoreoScript`
- **键盘 + 触屏**：`WASD` 前后转向、`Z/X` 侧移、`Space` 紧急停止；按钮全部触摸友好（已在 Surface Pro 上验证）

---

## 📦 安装

### 1. 安装 Python 依赖

```bash
git clone https://github.com/Owen1257173018/Unitree_MultiRobotControl.git
cd Unitree_MultiRobotControl

# 安装本地 WebRTC 库（已包含本地修改：EC 公钥兼容 + 中文 Windows headers 修复）
pip install -e unitree_webrtc_connect-master/

# 安装应用依赖
pip install -r requirements.txt
```

### 2. 启动应用

```bash
python MultiRobotApp.py
```

### 3. (可选) 打包成 Windows 单文件 exe

```bash
pip install pyinstaller
pyinstaller MultiRobotApp.spec
# 产物：dist/MultiRobotApp.exe
```

---

## 🚀 快速上手

### 第一次连机器人（老固件 Go2 < 1.1.15 / G1 < 1.5.1）

1. 让电脑和机器人在同一个 Wi-Fi 网段（或直连机器人热点）
2. 启动应用 → 点 `📡 扫描添加` → 「开始扫描」（SN 框留空可扫到所有在线机器人）
3. 勾选要添加的设备 → `✅ 添加选中设备` → 自动连接

### 第一次连新固件机器人（data2=3）

新固件需要一把 **per-device AES-128 密钥**，存在宇树云端。两种获取方式：

- **方式 A（推荐）应用内拉取**：扫描结果或 IP 添加对话框里点 `☁` → 输入宇树官方账号 → 自动写入密钥
- **方式 B 命令行**：`python -m unitree_webrtc_connect._cli --email <你的邮箱> --sn <机器人SN>`

拉到密钥后，机器人连上之后**这把密钥已经存在本地配置里了**，后续不需要再次登录。

### 保存 / 还原配置

把添加好的机器人组合命名保存：`💾 保存配置` → 输入名称（例：「演出A组」）。
下次直接 `📂 配置连接` → 选择配置 → 一键连接所有机器人。

---

## 🏗 架构

```
MultiRobotApp.py  →  main_window.py  →  backend.py  →  unitree_webrtc_connect-master/
   (入口)             (PyQt6 UI)        (异步管理)         (WebRTC 库)
```

- **`backend.py`** 跑独立的 asyncio 事件循环线程，所有机器人连接和命令在那执行；通过 `pyqtSignal` 把结果送回 UI 线程
- **`main_window.py`** 左侧机器人列表 + 右侧控制面板，根据选中机器人类型切换 Go2 / G1 / 混合 UI
- **`choreography.py`** 编排编辑器 + 播放器 + 录制 (`RecordingSession`)
- **`unitree_webrtc_connect-master/`** 是宇树官方库的本地分叉，加了几处本地补丁（见 [CLAUDE.md](CLAUDE.md) 详述）

---

## 🛠 配置文件

应用首次运行会在程序目录创建 `unitree_robots_config.json`，结构示意：

```json
{
  "saved_configs": [
    {
      "name": "演出A组",
      "robots": [
        {"name": "狗A", "robot_type": "go2", "ip": "192.168.1.100",
         "aes_128_key": "abc...32-hex...", "sn": "B42D..."}
      ]
    }
  ],
  "unitree_email": "you@example.com"
}
```

> **注意**：密码绝不写入；只记忆邮箱用于下次登录预填。AES 密钥存储为明文，配置文件**不要分享**给他人。

---

## ⚠️ 已知限制

- 新固件需要先用宇树官方 App 完成首次激活/绑定，账号 → 设备列表里能看到才能从云端拉密钥
- 多播扫描依赖路由器允许 UDP 多播 + 同子网；部分企业/酒店网络会被拦
- WebRTC 视频流和雷达数据通道目前只做了基本订阅，没做完整可视化
- 极少数情况下 Qt 的 `InternalMove` 拖拽会清掉自定义 widget，已通过 `RobotListPanel._on_order_changed()` 兜底重绑

---

## 🤝 致谢

- 上游 WebRTC 库：**[unitree_webrtc_connect](https://github.com/legion1581/unitree_webrtc_connect)** by Konstantin Severov（MIT License）— 本仓库内含其本地分叉，包含以下本地修改：
  - `encryption.py` 加入 EC 公钥兼容路径
  - `unitree_cloud.py` 修复中文 Windows 上 `time.strftime("%Z")` 触发 latin-1 header 编码错误的 bug
  - 引入结构化异常 + AES-128 密钥流（本地与上游同步）
- 界面配色采用 [Catppuccin Mocha](https://github.com/catppuccin/catppuccin) 主题
- Unitree 机器人官方文档与 SDK

---

## 📄 License

本仓库以 **MIT License** 发布。`unitree_webrtc_connect-master/` 子目录保留其原始 MIT License，归 Konstantin Severov 所有。
