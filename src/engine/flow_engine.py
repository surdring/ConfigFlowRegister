from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import logging
import os
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

try:  # Python 3.11+
    import tomllib as toml  # type: ignore
except Exception:  # Python <3.11
    try:
        import tomli as toml  # type: ignore
    except Exception:  # pragma: no cover - dependency missing
        toml = None  # type: ignore

from .models import Flow, Step, Selector
from . import actions as act
try:
    from utils.exceptions import ValidationError  # type: ignore
except Exception:
    try:
        from ..utils.exceptions import ValidationError
    except Exception:
        try:
            from src.utils.exceptions import ValidationError  # type: ignore
        except Exception:
            class ValidationError(Exception):
                pass

logger = logging.getLogger(__name__)


class FlowLoader:
    @staticmethod
    def load(path: str | Path) -> Flow:
        if toml is None:
            raise RuntimeError("TOML parser not available. Install 'tomli' for Python <3.11.")
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        with p.open("rb") as f:
            data: Dict[str, Any] = toml.load(f)  # type: ignore[arg-type]
        flow = _parse_flow_dict(data)
        _validate_flow(data, flow)
        return flow


class VariableResolver:
    @staticmethod
    def resolve(text: str, context: Dict[str, Any]) -> str:
        """Resolve placeholders like {config.xxx}, {account.email}, {env.HOME}, {flow.start_url}.

        Unknown variables raise ValidationError.
        """
        if text is None:
            return text
        if not isinstance(text, str):
            return text  # type: ignore[return-value]

        pattern = re.compile(r"\{([a-zA-Z_]+)\.([^{}]+)\}")

        def repl(match: re.Match[str]) -> str:
            ns = match.group(1)
            keypath = match.group(2)
            try:
                if ns == "env":
                    val = os.environ.get(keypath)
                    if val is None:
                        raise KeyError(keypath)
                    return str(val)
                source = context.get(ns, {}) if isinstance(context, dict) else {}
                val = _get_by_path(source, keypath)
                return "" if val is None else str(val)
            except KeyError:
                raise ValidationError(f"变量不存在: {{{ns}.{keypath}}}")

        return pattern.sub(repl, text)

    @staticmethod
    def resolve_obj(obj: Any, context: Dict[str, Any]) -> Any:
        """Recursively resolve variables within str/list/dict objects."""
        if isinstance(obj, str):
            return VariableResolver.resolve(obj, context)
        if isinstance(obj, list):
            return [VariableResolver.resolve_obj(v, context) for v in obj]
        if isinstance(obj, dict):
            return {k: VariableResolver.resolve_obj(v, context) for k, v in obj.items()}
        return obj


class FlowRunner:
    @staticmethod
    def execute(
        flow: Flow,
        driver: Any,
        account: Optional[Dict[str, Any]] = None,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        logger.info("Starting flow: %s", flow.name)

        # Build resolution context
        ctx: Dict[str, Any] = context.copy() if isinstance(context, dict) else {}
        if "config" not in ctx:
            ctx["config"] = {}
        if account is not None:
            ctx["account"] = account
        # expose flow variables & fields
        flow_ctx: Dict[str, Any] = {"start_url": flow.start_url}
        flow_ctx.update(flow.variables or {})
        ctx["flow"] = flow_ctx

        for step in flow.steps:
            try:
                _execute_step(step, flow, driver, ctx)
            except Exception as e:
                if step.optional:
                    logger.warning("可选步骤失败已跳过: %s (%s)", step.action, e)
                    continue
                raise
        logger.info("Flow completed: %s", flow.name)


def _parse_flow_dict(data: Dict[str, Any]) -> Flow:
    flow_info: Dict[str, Any] = data.get("flow", {}) if isinstance(data.get("flow"), dict) else {}
    variables: Dict[str, Any] = data.get("variables", {}) if isinstance(data.get("variables"), dict) else {}
    selectors_in: Dict[str, Any] = data.get("selectors", {}) if isinstance(data.get("selectors"), dict) else {}
    steps_in: Any = data.get("steps") or data.get("Steps") or data.get("STEPS") or []

    selectors: Dict[str, Selector] = {}
    for key, val in selectors_in.items():
        if isinstance(val, dict):
            by = val.get("by")
            value = val.get("value")
            optional = bool(val.get("optional", False))
            if by and value:
                selectors[key] = Selector(by=by, value=value, optional=optional)

    steps: list[Step] = []
    if isinstance(steps_in, list):
        for s in steps_in:
            if isinstance(s, dict):
                steps.append(
                    Step(
                        action=s.get("action"),
                        target=s.get("target"),
                        value=s.get("value"),
                        state=s.get("state"),
                        timeout_ms=s.get("timeout") or s.get("timeout_ms"),
                        optional=bool(s.get("optional", False)),
                        message=s.get("message"),
                    )
                )

    return Flow(
        name=flow_info.get("name", "UnnamedFlow"),
        start_url=flow_info.get("start_url"),
        timeout_ms=int(flow_info.get("timeout_ms", 10000) or 10000),
        variables=variables,
        selectors=selectors,
        steps=steps,
    )


def _get_by_path(source: Any, keypath: str) -> Any:
    cur = source
    for part in keypath.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(keypath)
            cur = cur[part]
        else:
            # try attribute access
            if not hasattr(cur, part):
                raise KeyError(keypath)
            cur = getattr(cur, part)
    return cur


def _execute_step(step: Step, flow: Flow, driver: Any, ctx: Dict[str, Any]) -> None:
    action = step.action
    if not action:
        raise ValidationError("步骤缺少 action")

    # resolve text fields
    value = VariableResolver.resolve(step.value, ctx) if step.value else None
    message = VariableResolver.resolve(step.message, ctx) if step.message else None
    state = step.state
    timeout_ms = step.timeout_ms or flow.timeout_ms

    if action == "navigate":
        url = value or VariableResolver.resolve(flow.start_url or "", ctx)
        if not url:
            raise ValidationError("navigate 步骤需要提供 URL 或 flow.start_url")
        logger.info("Navigate -> %s", url)
        act.navigate(driver, url)
        return

    if action == "sleep":
        delay = int(value or 0)
        logger.info("Sleep %s ms", delay)
        act.sleep(delay)
        return

    if action == "pause_for_manual":
        logger.info(message or "请完成人机验证后在 GUI 点击'手动继续'")
        # 通知上层：已到达人机验证
        cb = ctx.get("on_reached_manual") if isinstance(ctx, dict) else None
        if callable(cb):
            try:
                cb()
            except Exception:
                pass
        # 等待用户在 GUI 中点击“手动继续”
        evt = ctx.get("manual_continue_event") if isinstance(ctx, dict) else None
        if evt is not None:
            try:
                evt.wait()
                evt.clear()
            except Exception:
                pass
        else:
            input("按回车继续...")
        return

    if action == "wait":
        if not step.target:
            raise ValidationError("wait 步骤需要 target")
        locator = _get_locator(flow, step.target)
        act.wait(driver, locator, state or "present", timeout_ms)
        return

    if action == "click":
        if not step.target:
            raise ValidationError("click 步骤需要 target")
        locator = _get_locator(flow, step.target)
        act.click(driver, locator)
        return

    if action == "type":
        if not step.target:
            raise ValidationError("type 步骤需要 target")
        locator = _get_locator(flow, step.target)
        text = value or ""
        act.type(driver, locator, text)
        return

    if action == "expect":
        if not step.target:
            raise ValidationError("expect 步骤需要 target")
        locator = _get_locator(flow, step.target)
        act.expect(driver, locator, state or "visible")
        return

    # Other actions are not implemented in this initial step
    logger.info("未实现的动作: %s（已跳过）", action)


def run_batch(
    flow: Flow,
    accounts: list[Dict[str, Any]],
    interval_seconds: float = 0,
    *,
    driver_factory: Any,
    driver_cleanup: Optional[Any] = None,
    base_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """批量执行 Flow，返回结果统计与明细。

    Args:
        flow: 已加载的 Flow 对象
        accounts: 账号列表（dict，至少包含 email/password 等字段）
        interval_seconds: 每个账号之间的等待时间（秒）
        driver_factory: 可调用对象，返回一个可用的 WebDriver 实例
        driver_cleanup: 可调用对象，接收 driver，负责清理（可选）
        base_context: 传递给执行器的基础上下文（可选）
    Returns:
        { 'results': [...], 'success': int, 'failed': int, 'total': int, 'elapsed_s': float }
    """
    t0 = time.time()
    results: list[Dict[str, Any]] = []
    success = failed = 0

    for i, acc in enumerate(accounts, start=1):
        acc_id = acc.get("email") or f"#{i}"
        logger.info("开始账号执行: %s (%d/%d)", acc_id, i, len(accounts))
        driver = None
        ok = True
        err: Optional[str] = None
        t1 = time.time()
        try:
            driver = driver_factory()
            ctx = dict(base_context or {})
            ctx.setdefault("config", {})
            FlowRunner.execute(flow, driver, account=acc, context=ctx)
        except Exception as e:
            ok = False
            err = str(e)
            logger.error("账号执行失败: %s - %s", acc_id, err)
        finally:
            try:
                if driver_cleanup is not None:
                    driver_cleanup(driver)
                else:
                    try:
                        driver.quit()  # type: ignore
                    except Exception:
                        pass
            finally:
                elapsed_ms = int((time.time() - t1) * 1000)
                results.append({
                    "account": acc_id,
                    "success": ok,
                    "error": err,
                    "elapsed_ms": elapsed_ms,
                })
                if ok:
                    success += 1
                else:
                    failed += 1
        if i < len(accounts) and interval_seconds > 0:
            time.sleep(interval_seconds)

    total = len(accounts)
    elapsed_s = round(time.time() - t0, 3)
    logger.info("批量执行完成: total=%d, success=%d, failed=%d, elapsed=%.3fs", total, success, failed, elapsed_s)
    return {"results": results, "success": success, "failed": failed, "total": total, "elapsed_s": elapsed_s}


def _get_locator(flow: Flow, target: str) -> tuple[str, str]:
    if target not in flow.selectors:
        raise ValidationError(f"未定义的 selector: {target}")
    sel = flow.selectors[target]
    by = sel.by
    value = sel.value
    if by not in ("id", "css", "xpath"):
        raise ValidationError(f"不支持的 selector.by: {by}")
    if by == "id":
        return (By.ID, value)
    if by == "css":
        return (By.CSS_SELECTOR, value)
    return (By.XPATH, value)


def _wait_for_state(driver: Any, locator: tuple[str, str], state: Optional[str], timeout_ms: int):
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


def _validate_flow(data: Dict[str, Any], flow: Flow) -> None:
    if not isinstance(data.get("flow"), dict):
        raise ValidationError("缺少 flow 段")
    if not isinstance(data.get("steps") or data.get("Steps") or data.get("STEPS"), list):
        raise ValidationError("缺少 steps 段或格式错误，应为数组")
    if not flow.steps:
        raise ValidationError("Flow.steps 不能为空")

    needs_selectors = any(bool(s.target) for s in flow.steps)
    if needs_selectors and not isinstance(data.get("selectors"), dict):
        raise ValidationError("缺少 selectors 段（存在使用 target 的步骤时必需）")

    valid_actions = {"navigate", "wait", "type", "click", "sleep", "expect", "pause_for_manual"}
    valid_states = {None, "visible", "present", "clickable"}
    for idx, s in enumerate(flow.steps):
        if s.action not in valid_actions:
            raise ValidationError(f"不支持的 action: {s.action} (index={idx})")
        if s.state not in valid_states:
            raise ValidationError(f"不支持的 state: {s.state} (index={idx})")
        if s.target and s.target not in flow.selectors:
            raise ValidationError(f"步骤引用了未定义的 selector: {s.target} (index={idx})")

    for name, sel in flow.selectors.items():
        if sel.by not in ("id", "css", "xpath"):
            raise ValidationError(f"selector '{name}' 的 by 值无效: {sel.by}")
