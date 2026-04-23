from __future__ import annotations

from typing import Any, Optional, Tuple
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException, ElementNotInteractableException, WebDriverException

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
        try:
            el = _wait_for_state(driver, locator, "visible", 10000)
            try:
                el.clear()
            except Exception:
                pass
            try:
                el.send_keys(value)
            except Exception:
                driver.execute_script("arguments[0].value = arguments[1];", el, value)
        except TimeoutException as e:
            by, val = locator
            raise ValidationError(f"输入超时: 无法找到元素 ({by}, {val})")
        except ElementNotInteractableException as e:
            by, val = locator
            raise ValidationError(f"元素不可输入: ({by}, {val}) - 可能为只读或被遮挡")
        except NoSuchElementException as e:
            by, val = locator
            raise ValidationError(f"元素不存在: ({by}, {val})")

    _retry_on_stale(_do)


def type_otp_digits(driver: Any, locator: Tuple[str, str], value: str) -> None:
    """逐位输入验证码数字到多个输入框（如6个格子）。"""
    def _do():
        try:
            # 使用基础选择器找到所有匹配的输入框
            by, val = locator
            wait = WebDriverWait(driver, 10)
            if by == By.CSS_SELECTOR:
                elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, val)))
            elif by == By.XPATH:
                elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, val)))
            else:
                # 对于 id 选择器，只找一个元素
                elements = [wait.until(EC.presence_of_element_located((by, val)))]

            # 清理并验证验证码
            digits = ''.join(c for c in value if c.isdigit())
            if len(digits) != 6:
                raise ValidationError(f"验证码必须是6位数字，当前: {digits} ({len(digits)}位)")

            # 如果找到1个元素，使用普通输入方式
            if len(elements) == 1:
                el = elements[0]
                try:
                    el.clear()
                except Exception:
                    pass
                try:
                    el.send_keys(digits)
                except Exception:
                    driver.execute_script("arguments[0].value = arguments[1];", el, digits)
            # 如果找到6个元素，逐位输入
            elif len(elements) >= 6:
                for i, digit in enumerate(digits):
                    if i < len(elements):
                        el = elements[i]
                        try:
                            el.clear()
                        except Exception:
                            pass
                        try:
                            el.send_keys(digit)
                        except Exception:
                            driver.execute_script("arguments[0].value = arguments[1];", el, digit)
                        time.sleep(0.1)  # 短暂延迟模拟人类输入
            else:
                raise ValidationError(f"找到 {len(elements)} 个输入框，但需要1个或6个")

        except TimeoutException as e:
            by, val = locator
            raise ValidationError(f"输入超时: 无法找到元素 ({by}, {val})")
        except ElementNotInteractableException as e:
            by, val = locator
            raise ValidationError(f"元素不可输入: ({by}, {val}) - 可能为只读或被遮挡")
        except NoSuchElementException as e:
            by, val = locator
            raise ValidationError(f"元素不存在: ({by}, {val})")

    _retry_on_stale(_do)


def click(driver: Any, locator: Tuple[str, str]) -> None:
    def _do():
        try:
            el = _wait_for_state(driver, locator, "clickable", 10000)
            el.click()
        except TimeoutException as e:
            by, val = locator
            raise ValidationError(f"点击超时: 无法找到或点击元素 ({by}, {val})")
        except ElementNotInteractableException as e:
            by, val = locator
            raise ValidationError(f"元素不可交互: ({by}, {val}) - 可能被遮挡或未启用")
        except NoSuchElementException as e:
            by, val = locator
            raise ValidationError(f"元素不存在: ({by}, {val})")

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
    last_error = None
    for i in range(retries):
        try:
            func()
            return
        except StaleElementReferenceException as e:
            last_error = e
            if i == retries - 1:
                raise ValidationError(f"元素已过时(StaleElementReference)，重试{retries}次后失败: {str(e)}")
            time.sleep(delay)
        except ValidationError:
            raise
        except Exception as e:
            last_error = e
            if i == retries - 1:
                raise ValidationError(f"操作失败: {type(e).__name__}: {str(e)}")
            time.sleep(delay)
