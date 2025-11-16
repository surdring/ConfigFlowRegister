# -*- mode: python ; coding: utf-8 -*-
"""
WindSurf账号批量注册工具 - PyInstaller配置文件

使用方法:
    pyinstaller windsurf_tool.spec
    
输出:
    dist/WindSurfRegTool.exe (Windows)
    dist/WindSurfRegTool (Linux/macOS)
"""

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['.'],  # 使用当前目录
    binaries=[],
    datas=[
        ('config.json.template', '.'),
    ],
    hiddenimports=[
        # Selenium（使用系统ChromeDriver）
        'selenium',
        'selenium.webdriver',
        'selenium.webdriver.chrome',
        'selenium.webdriver.chrome.service',
        'selenium.webdriver.common.by',
        'selenium.webdriver.support',
        'selenium.webdriver.support.wait',
        'selenium.webdriver.support.expected_conditions',
        # 所有src子模块
        'src',
        'src.automation',
        'src.automation.browser_handler',
        'src.data',
        'src.data.data_manager',
        'src.gui',
        'src.gui.main_window',
        'src.utils',
        'src.utils.logger',
        'src.utils.exceptions',
        'src.utils.config_loader',
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
    name='WindSurfRegTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 临时启用控制台窗口用于调试
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件路径
)
