# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 —— 跨平台 onefile 模式
使用方法：
    pyinstaller MultiRobotApp.spec

产物：
    Windows → dist/MultiRobotApp.exe
    macOS   → dist/MultiRobotApp.app（.app bundle）
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
is_mac = sys.platform == 'darwin'
is_win = sys.platform == 'win32'

# ── 项目根目录 ──
ROOT = os.path.dirname(os.path.abspath(SPEC))

# ── 收集 unitree_webrtc_connect 的全部子模块（含 lidar 等）──
uwc_hiddenimports = collect_submodules('unitree_webrtc_connect')

# ── 需要被 PyInstaller 识别的隐式导入 ──
hidden_imports = [
    # 项目自身模块（PyInstaller 可能扫不到延迟导入的模块）
    'backend',
    'main_window',
    'choreography',
    'joystick',
    'dialogs',
    # unitree 库
    *uwc_hiddenimports,
    # aiortc 及其依赖
    'aiortc',
    'aiortc.codecs',
    'aiortc.contrib.media',
    'av',
    # 加密
    'Crypto',
    'Crypto.Cipher.AES',
    'Crypto.Cipher.PKCS1_v1_5',
    'Crypto.PublicKey.RSA',
    'Crypto.PublicKey.ECC',
    # 其他可能被动态导入的包
    'engineio.async_drivers.threading',
    'sounddevice',
    'numpy',
    'lz4.frame',
    'lz4.block',
    'cv2',
    'requests',
    'wasmtime',
    # 新版 unitree_webrtc_connect 云端登录依赖（拉 AES-128 密钥用）
    'curl_cffi',
    'curl_cffi.requests',
]

# ── 需要打包的数据文件 ──
datas = [
    # .wasm 文件（lidar 解码器需要）
    (os.path.join(ROOT, 'unitree_webrtc_connect-master',
                  'unitree_webrtc_connect', 'lidar', 'libvoxel.wasm'),
     os.path.join('unitree_webrtc_connect', 'lidar')),
]

# 收集 wasmtime 的数据文件（.wasm engine 等）
try:
    datas += collect_data_files('wasmtime')
except Exception:
    pass

# 收集 certifi 的 CA 证书（requests/HTTPS 需要）
try:
    datas += collect_data_files('certifi')
except Exception:
    pass

# 收集 curl_cffi 的 native 库（libcurl-impersonate）
try:
    datas += collect_data_files('curl_cffi')
except Exception:
    pass

a = Analysis(
    [os.path.join(ROOT, 'MultiRobotApp.py')],
    pathex=[
        ROOT,
        os.path.join(ROOT, 'unitree_webrtc_connect-master'),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大包，减小体积
        'matplotlib',
        'scipy',
        'pandas',
        'tkinter',
        'test',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── onefile 模式：所有内容打进一个可执行文件 ──
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,          # onefile: 把 binaries 塞进 exe
    a.zipfiles,          # onefile: 把 zipfiles 塞进 exe
    a.datas,             # onefile: 把 datas 塞进 exe
    [],
    name='MultiRobotApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=is_mac,          # macOS 可以 strip 减小体积
    upx=is_win,            # UPX 仅 Windows；macOS arm64 兼容性差
    upx_exclude=[],
    runtime_tmpdir=None,   # None = 用系统默认临时目录解压
    console=False,         # False = 不弹命令行黑窗口（GUI 应用）
    # icon='app.ico',      # Windows 图标（.ico）
)

# ── macOS：打成 .app bundle，双击即可运行 ──
if is_mac:
    app = BUNDLE(
        exe,
        name='MultiRobotApp.app',
        icon=None,             # 有 .icns 图标就填路径
        bundle_identifier='com.unitree.multirobot',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': '1.0.0',
        },
    )
