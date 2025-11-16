# -*- mode: python ; coding: utf-8 -*-
"""
ConfigFlowRegister GUI - PyInstaller 配置（带控制台日志）

用法:
    python -m PyInstaller --clean --noconfirm configflow_gui.spec
输出:
    dist/ConfigFlowRegisterGUI/ConfigFlowRegisterGUI.exe
说明:
    - 采用 one-dir 布局，flows/ 会自动出现在 EXE 同级目录
    - console=True，启动 GUI 的同时保留控制台以查看日志
"""

block_cipher = None


a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config.json.template', '.'),
        ('flows/*.toml', 'flows'),
    ],
    hiddenimports=[
        # GUI 入口依赖
        'tkinter',
        'tkinter.ttk',
        # 引擎与工具
        'src',
        'src.engine',
        'src.engine.actions',
        'src.engine.flow_engine',
        'src.engine.models',
        'src.browser',
        'src.browser.provider',
        'src.utils',
        'src.utils.logger',
        'src.utils.exceptions',
        'src.utils.config',
        'src.utils.config_loader',
        'src.utils.path',
        'src.data',
        'src.data.data_manager',
        'src.models.account',
        # 依赖库
        'undetected_chromedriver',
        'selenium',
        'selenium.webdriver',
        'selenium.webdriver.chrome',
        'selenium.webdriver.chrome.service',
        'selenium.webdriver.common.by',
        'selenium.webdriver.support',
        'selenium.webdriver.support.wait',
        'selenium.webdriver.support.expected_conditions',
        # Python <3.11 时的 tomli 解析
        'tomli',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'pandas',
        'numpy',
        'PIL',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ConfigFlowRegisterGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # GUI + 控制台日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ConfigFlowRegisterGUI'
)
