from __future__ import annotations

from typing import Any, Optional, Tuple
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

try:
    from ..utils.exceptions import ValidationError
except Exception:  # fallback if import path differs in packaging
    class ValidationError(Exception):
        pass


def navigate(driver: Any, url: str) -> None:  # noqa: D401
    driver.get(url)


def wait(driver: Any, locator: Tuple[str, str], state: str, timeout_ms: int | None = None):
    return _wait_for_state(driver, locator, state, timeout_ms or 10000)


def type(driver: Any, locator: Tuple[str, str], value: str) -> None:  # noqa: A001 - keep action name
    def _do():
        el = _wait_for_state(driver, locator, "visible", 10000)
        try:
            el.clear()
        except Exception:
            pass
        try:
            el.send_keys(value)
        except Exception:
            driver.execute_script("arguments[0].value = arguments[1];", el, value)

    _retry_on_stale(_do)


def click(driver: Any, locator: Tuple[str, str]) -> None:
    def _do():
        el = _wait_for_state(driver, locator, "clickable", 10000)
        el.click()

    _retry_on_stale(_do)


def sleep(ms: int) -> None:
    time.sleep(max(0, int(ms)) / 1000.0)


def expect(driver: Any, locator: Tuple[str, str], condition: str) -> None:
    try:
        _wait_for_state(driver, locator, condition or "visible", 10000)
    except TimeoutException:
        by, val = locator
        raise ValidationError(f"期望未满足: locator=({by}, {val}) condition={condition}")


def _wait_for_state(driver: Any, locator: Tuple[str, str], state: Optional[str], timeout_ms: int):
    wait = WebDriverWait(driver, max(1, int(timeout_ms / 1000)))
    by, val = locator
    if state == "visible":
        return wait.until(EC.visibility_of_element_located((by, val)))
    if state == "clickable":
        return wait.until(EC.element_to_be_clickable((by, val)))
    # default present
    return wait.until(EC.presence_of_element_located((by, val)))


def _retry_on_stale(func, retries: int = 3, delay: float = 0.5) -> None:
    for i in range(retries):
        try:
            func()
            return
        except StaleElementReferenceException:
            if i == retries - 1:
                raise
            time.sleep(delay)
