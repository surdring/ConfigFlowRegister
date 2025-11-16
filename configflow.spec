# -*- mode: python ; coding: utf-8 -*-
"""
ConfigFlowRegister - PyInstaller 配置

用法:
    python -m PyInstaller --clean --noconfirm configflow.spec
输出:
    dist/ConfigFlowRegister.exe (Windows)
    dist/ConfigFlowRegister (Linux/macOS)
"""

block_cipher = None


a = Analysis(
    ['src/cli.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config.json.template', '.'),
        ('flows/*.toml', 'flows'),
    ],
    hiddenimports=[
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
    name='ConfigFlowRegister',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 为 CLI 显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
