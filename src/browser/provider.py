from __future__ import annotations

from typing import Any, Optional
from pathlib import Path
import shutil
import tempfile
import time
import os
import logging
import subprocess

import undetected_chromedriver as uc

try:  # preferred relative import
    from ..utils.logger import default_logger as logger
    from ..utils.exceptions import BrowserError
except Exception:  # fallbacks for various execution contexts
    try:
        from src.utils.logger import default_logger as logger  # type: ignore
        from src.utils.exceptions import BrowserError  # type: ignore
    except Exception:  # last resort
        logger = logging.getLogger(__name__)
        class BrowserError(RuntimeError):  # type: ignore
            pass


class BrowserProvider:
    """Browser lifecycle manager with stealth defaults (undetected-chromedriver)."""

    @staticmethod
    def start_browser(*, headless: bool = False, window_size: str = "1920,1080") -> Any:
        """Start and return an undetected Chrome driver configured for anti-detection.

        Args:
            headless: Whether to start in headless mode. Not recommended for CAPTCHA.
            window_size: Window size string, e.g. "1920,1080".
        Raises:
            BrowserError: When the browser fails to start.
        """
        try:
            logger.info("=" * 70)
            logger.info("启动Chrome浏览器（临时目录模式 / 反检测）")
            logger.info("=" * 70)

            # 1) Proactively close existing Chrome processes (Windows only semantics)
            logger.info("\n步骤1: 关闭现有Chrome进程……")
            BrowserProvider._kill_chrome_processes()

            # 2) Chrome options (lean config, let UC apply stealth defaults)
            logger.info("\n步骤2: 配置Chrome选项（反检测模式）……")
            chrome_options = uc.ChromeOptions()
            chrome_options.add_experimental_option(
                "prefs",
                {
                    "profile.default_content_setting_values.notifications": 2,
                    "credentials_enable_service": False,
                    "profile.password_manager_enabled": False,
                },
            )
            chrome_options.add_argument(f"--window-size={window_size}")

            # 3) Temporary user-data-dir to reduce fingerprint reuse
            temp_profile_dir = BrowserProvider._create_temp_profile_dir()
            chrome_options.add_argument(f"--user-data-dir={temp_profile_dir}")
            chrome_options.add_argument("--profile-directory=Default")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--disable-default-apps")

            if headless:
                logger.warning("⚠️ 无头模式下人机验证通过率低，建议关闭 headless")
                chrome_options.add_argument("--headless=new")
            else:
                logger.info("✓ 使用有头模式（推荐，人机验证通过率更高）")

            logger.info("✓ Chrome 选项配置完成")

            # 4) Prefer system chromedriver, fallback to UC auto-download
            logger.info("\n步骤3: 启动Chrome浏览器……")
            driver_kwargs: dict[str, Any] = {
                "options": chrome_options,
                "use_subprocess": True,
                "version_main": None,  # auto-detect
                "headless": headless,
                "suppress_welcome": True,
                "no_sandbox": True,
            }

            system_driver = shutil.which("chromedriver")
            if system_driver:
                system_driver_path = Path(system_driver)
                logger.info(f"✓ 检测到系统 ChromeDriver: {system_driver_path}")
                # 在 Windows 下，某些库会在不区分大小写时再次追加 .exe，
                # 若路径以 .EXE 结尾，会变成 EXE.exe，导致找不到文件。
                # 统一规范为小写 .exe 以避免重复追加。
                sanitized_path = system_driver_path
                try:
                    if os.name == "nt":
                        # 统一规范为 .exe（小写），避免上游再次追加 .exe 形成 EXE.exe
                        sanitized_path = system_driver_path.with_suffix(".exe")
                except Exception:
                    pass
                if os.path.exists(str(sanitized_path)) and os.access(str(sanitized_path), os.X_OK | os.R_OK):
                    logger.info(f"✓ 使用系统 ChromeDriver 路径: {sanitized_path}")
                    driver_kwargs["driver_executable_path"] = str(sanitized_path)
                    driver_kwargs.pop("version_main", None)
                else:
                    logger.warning("⚠️ 系统 ChromeDriver 不可访问或无执行权限，改用 UC 自动下载")
            else:
                logger.warning("未检测到系统 ChromeDriver，使用 UC 自动下载匹配版本")

            start_time = time.time()
            try:
                driver = uc.Chrome(**driver_kwargs)
            except Exception as e:  # refine error messages
                elapsed = time.time() - start_time
                msg = str(e)
                logger.error(f"✗ Chrome WebDriver 创建失败 (耗时: {elapsed:.2f}s): {msg}")
                if "session not created" in msg.lower():
                    if "version mismatch" in msg.lower() or "mismatch" in msg.lower():
                        raise BrowserError("ChromeDriver 与 Chrome 版本不匹配")
                    if "chrome not reachable" in msg.lower():
                        raise BrowserError("Chrome 启动后无法连接，请关闭所有 Chrome 进程重试")
                raise BrowserError(f"Chrome WebDriver 创建失败: {msg}")

            elapsed = time.time() - start_time
            logger.info(f"✓ Undetected Chrome 启动成功 (耗时: {elapsed:.2f}s)")

            # Attach temp profile path to driver for later cleanup
            try:
                setattr(driver, "_cf_temp_profile_dir", temp_profile_dir)
            except Exception:
                pass

            # Basic stealth verification + enhanced script
            try:
                webdriver_value = driver.execute_script("return navigator.webdriver")
                if webdriver_value in (None, False):
                    logger.info("✓ navigator.webdriver 已隐藏")
                else:
                    logger.warning(f"⚠️ navigator.webdriver={webdriver_value}")
            except Exception:
                pass

            BrowserProvider._apply_enhanced_stealth(driver)
            driver.implicitly_wait(5)

            logger.info("=" * 70)
            logger.info("✅ Chrome 浏览器已启动（临时目录模式，反检测已启用）")
            logger.info(f"   - 临时用户数据目录: {temp_profile_dir}")
            logger.info("   - 干净环境，无历史和 Cookie")
            logger.info("=" * 70)
            return driver

        except BrowserError:
            raise
        except Exception as e:
            raise BrowserError(f"浏览器启动失败: {e}")

    @staticmethod
    def cleanup(driver: Any) -> None:
        """Cleanup browser resources and temporary profile directory."""
        try:
            if driver is not None:
                try:
                    driver.quit()  # type: ignore[attr-defined]
                except Exception:
                    pass
                # attempt to remove temp profile dir
                temp_dir: Optional[str] = getattr(driver, "_cf_temp_profile_dir", None)
                if temp_dir and os.path.isdir(temp_dir):
                    for _ in range(3):  # retry a few times in case of file locks
                        try:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            break
                        except Exception:
                            time.sleep(0.5)
        except Exception:
            pass

    # ------------------------- helpers -------------------------
    @staticmethod
    def _create_temp_profile_dir() -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(tempfile.gettempdir(), f"windsurf_chrome_{ts}")
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _kill_chrome_processes() -> None:
        try:
            # Windows taskkill; on non-Windows it will likely fail harmlessly
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True, timeout=5)
            time.sleep(1.5)
        except Exception:
            pass

    @staticmethod
    def _apply_enhanced_stealth(driver: Any) -> None:
        try:
            driver.execute_script(
                """
                // Remove webdriver flag
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

                // Fake plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { filename: 'internal-pdf-viewer', name: 'Chrome PDF Plugin', length: 1,
                          0: {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format'},
                          description: 'Portable Document Format' },
                        { filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', name: 'Chrome PDF Viewer', length: 1,
                          0: {type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
                          description: 'Portable Document Format' }
                    ]
                });

                // Languages
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

                // window.chrome object
                window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };

                // Permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Hardware hints
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'connection', { get: () => ({ effectiveType: '4g', rtt: 100, downlink: 10 }) });
                """
            )
            logger.info("✓ 增强反检测脚本完成")
        except Exception:
            pass
