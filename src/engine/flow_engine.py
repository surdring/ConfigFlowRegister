from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import logging
import os
import re
import time
import threading
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
from ..utils.email_otp_fetcher import build_and_fetch_from_dict
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
        auto_mode = False
        if isinstance(ctx, dict):
            try:
                auto_mode = bool(ctx.get("auto_mode"))
            except Exception:
                auto_mode = False
        if not auto_mode:
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

    if action == "wait_otp":
        auto_mode = bool(ctx.get("auto_mode")) if isinstance(ctx, dict) else False
        if not auto_mode:
            logger.info("wait_otp 在非自动模式下跳过")
            return

        if not isinstance(ctx, dict):
            raise ValidationError("wait_otp 缺少上下文")

        config = ctx.get("config") or {}
        email_cfg = ctx.get("email_cfg") or (config.get("email") if isinstance(config, dict) else {})
        if not isinstance(email_cfg, dict):
            raise ValidationError("wait_otp 缺少 email 配置")
        if not (email_cfg.get("address") and email_cfg.get("password")):
            raise ValidationError("wait_otp: email 配置不完整，无法自动获取验证码")

        account_ctx = ctx.get("account") or {}
        if not isinstance(account_ctx, dict):
            raise ValidationError("wait_otp: 缺少 account 上下文")
        account_email = account_ctx.get("email")
        if not account_email:
            raise ValidationError("wait_otp: 缺少 account.email")

        verification = ctx.get("verification")
        if not isinstance(verification, dict):
            raise ValidationError("wait_otp: 缺少 verification 状态")

        stop_event = ctx.get("stop_event")
        if stop_event is None:
            raise ValidationError("wait_otp: 缺少 stop_event")

        cb = ctx.get("on_verification_code")
        if not callable(cb):
            raise ValidationError("wait_otp: 缺少 on_verification_code 回调")

        def _stop_flag() -> bool:
            try:
                return bool(stop_event.is_set())  # type: ignore[call-arg]
            except Exception:
                return False

        # 若尚未有验证码，则启动监听线程
        if not verification.get("code"):
            threading.Thread(
                target=build_and_fetch_from_dict,
                args=(email_cfg, account_email, cb, _stop_flag),
                daemon=True,
            ).start()
            logger.info("🔍 已启动验证码监听线程（全自动模式）")

        logger.info("⏳ 正在等待邮箱验证码（全自动模式）...")
        wait_deadline = time.time() + 180
        while not verification.get("code") and not _stop_flag() and time.time() < wait_deadline:
            time.sleep(1.0)

        if _stop_flag():
            raise ValidationError("任务已被用户停止（等待验证码时）")

        code = verification.get("code")
        if not code:
            raise ValidationError("在全自动模式下等待验证码超时或未获取到验证码")

        logger.info("🔐 已获取验证码（全自动模式）")
        return

    if action == "wait_onboarding_source":
        auto_mode = bool(ctx.get("auto_mode")) if isinstance(ctx, dict) else False
        if not auto_mode:
            logger.info("wait_onboarding_source 在非自动模式下跳过")
            return

        profile_url = "https://windsurf.com/profile"
        timeout = 15

        logger.info("⏳ 等待页面跳转到 %s ...", profile_url)
        end_ts = time.time() + timeout

        while time.time() < end_ts:
            try:
                url = getattr(driver, "current_url", None)  # type: ignore[attr-defined]
                if isinstance(url, str) and url.startswith(profile_url):
                    logger.info("✅ 页面已跳转到 %s，注册成功", url)
                    time.sleep(2)  # 等待2秒后开始新一轮注册
                    return
            except Exception:
                pass
            time.sleep(1.0)

        logger.error("❌ 等待页面跳转超时，跳过此账号")
        raise ValidationError(
            "验证码验证失败: 页面未跳转到profile，将重启浏览器继续下个账号"
        )

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
        by, val = locator
        logger.info("[步骤] 点击元素: %s=%s", by, val)
        try:
            act.click(driver, locator)
        except ValidationError as e:
            logger.error("[步骤失败] 点击 %s=%s 时出错: %s", by, val, str(e))
            raise
        return

    if action == "type":
        if not step.target:
            raise ValidationError("type 步骤需要 target")
        locator = _get_locator(flow, step.target)
        text = value or ""
        by, val = locator
        logger.info("[步骤] 输入文本到: %s=%s", by, val)
        try:
            act.type(driver, locator, text)
        except ValidationError as e:
            logger.error("[步骤失败] 输入 %s=%s 时出错: %s", by, val, str(e))
            raise
        return

    if action == "type_otp_digits":
        if not step.target:
            raise ValidationError("type_otp_digits 步骤需要 target")
        locator = _get_locator(flow, step.target)
        text = value or ""
        by, val = locator
        logger.info("[步骤] 逐位输入验证码到: %s=%s", by, val)
        try:
            act.type_otp_digits(driver, locator, text)
        except ValidationError as e:
            logger.error("[步骤失败] 逐位输入验证码 %s=%s 时出错: %s", by, val, str(e))
            raise
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
    max_retries: int = 2,
) -> Dict[str, Any]:
    """批量执行 Flow，返回结果统计与明细。

    Args:
        flow: 已加载的 Flow 对象
        accounts: 账号列表（dict，至少包含 email/password 等字段）
        interval_seconds: 每个账号之间的等待时间（秒）
        driver_factory: 可调用对象，返回一个可用的 WebDriver 实例
        driver_cleanup: 可调用对象，接收 driver，负责清理（可选）
        base_context: 传递给执行器的基础上下文（可选）
        max_retries: 失败时最大重试次数（默认2次，共3次尝试）
    Returns:
        { 'results': [...], 'success': int, 'failed': int, 'total': int, 'elapsed_s': float }
    """
    t0 = time.time()
    results: list[Dict[str, Any]] = []
    success = failed = 0

    for i, acc in enumerate(accounts, start=1):
        acc_id = acc.get("email") or f"#{i}"
        logger.info("开始账号执行: %s (%d/%d)", acc_id, i, len(accounts))

        # 重试逻辑
        attempt = 0
        max_attempts = max_retries + 1
        ok = True
        err: Optional[str] = None
        elapsed_ms = 0

        while attempt < max_attempts:
            attempt += 1
            driver = None
            t1 = time.time()
            ok = True
            err = None

            if attempt > 1:
                logger.info("🔄 账号 %s 第 %d/%d 次重试...", acc_id, attempt, max_attempts)
                time.sleep(2)  # 重试前等待2秒

            try:
                driver = driver_factory()
                ctx = dict(base_context or {})
                ctx.setdefault("config", {})
                FlowRunner.execute(flow, driver, account=acc, context=ctx)
                break  # 成功，退出重试循环
            except Exception as e:
                ok = False
                err = str(e)
                logger.error("账号执行失败 (尝试 %d/%d): %s - %s", attempt, max_attempts, acc_id, err)
            finally:
                try:
                    if driver_cleanup is not None:
                        driver_cleanup(driver)
                    else:
                        try:
                            driver.quit()  # type: ignore
                        except Exception:
                            pass
                except Exception:
                    pass

                elapsed_ms = int((time.time() - t1) * 1000)

        # 记录最终结果
        results.append({
            "account": acc_id,
            "success": ok,
            "error": err,
            "elapsed_ms": elapsed_ms,
            "attempts": attempt,
        })
        if ok:
            success += 1
            logger.info("✅ 账号 %s 注册成功", acc_id)
        else:
            failed += 1
            logger.error("❌ 账号 %s 注册失败（已重试%d次）: %s", acc_id, max_attempts, err)

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

    valid_actions = {"navigate", "wait", "type", "type_otp_digits", "click", "sleep", "expect", "pause_for_manual", "wait_otp", "wait_onboarding_source"}
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
