from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal

try:
    from ..utils.exceptions import ValidationError
except Exception:
    try:
        from src.utils.exceptions import ValidationError  # type: ignore
    except Exception:  # pragma: no cover
        class ValidationError(Exception):
            pass


SelectorBy = Literal["id", "css", "xpath"]
WaitState = Literal["visible", "present", "clickable"]
ActionName = Literal[
    "navigate",
    "wait",
    "type",
    "click",
    "sleep",
    "expect",
    "pause_for_manual",
    "wait_otp",
    "wait_onboarding_source",
]


@dataclass
class Selector:
    by: SelectorBy
    value: str
    optional: bool = False

    def __post_init__(self) -> None:
        if self.by not in ("id", "css", "xpath"):
            raise ValidationError(f"selector.by 无效: {self.by}")
        if not isinstance(self.value, str) or not self.value:
            raise ValidationError("selector.value 不能为空")
        if not isinstance(self.optional, bool):
            raise ValidationError("selector.optional 必须为布尔类型")


@dataclass
class Step:
    action: ActionName
    target: Optional[str] = None
    value: Optional[str] = None
    state: Optional[WaitState] = None
    timeout_ms: Optional[int] = None
    optional: bool = False
    message: Optional[str] = None

    def __post_init__(self) -> None:
        valid_actions = {
            "navigate",
            "wait",
            "type",
            "click",
            "sleep",
            "expect",
            "pause_for_manual",
            "wait_otp",
            "wait_onboarding_source",
        }
        if self.action not in valid_actions:
            raise ValidationError(f"不支持的 action: {self.action}")

        valid_states = {None, "visible", "present", "clickable"}
        if self.state not in valid_states:
            raise ValidationError(f"不支持的 state: {self.state}")

        if self.action in {"wait", "type", "click", "expect"}:
            if not isinstance(self.target, str) or not self.target:
                raise ValidationError(f"{self.action} 步骤需要有效的 target")

        if self.timeout_ms is not None:
            if not isinstance(self.timeout_ms, int) or self.timeout_ms < 0:
                raise ValidationError("timeout_ms 必须为非负整数")

        if not isinstance(self.optional, bool):
            raise ValidationError("optional 必须为布尔类型")


@dataclass
class Flow:
    name: str
    start_url: Optional[str] = None
    timeout_ms: int = 10000
    variables: Dict[str, Any] = field(default_factory=dict)
    selectors: Dict[str, Selector] = field(default_factory=dict)
    steps: List[Step] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValidationError("flow.name 不能为空")
        if not isinstance(self.timeout_ms, int) or self.timeout_ms < 0:
            raise ValidationError("flow.timeout_ms 必须为非负整数")
        if not isinstance(self.variables, dict):
            raise ValidationError("flow.variables 必须为对象")
        if not isinstance(self.selectors, dict):
            raise ValidationError("flow.selectors 必须为对象")
        for k, v in self.selectors.items():
            if not isinstance(k, str) or not isinstance(v, Selector):
                raise ValidationError("flow.selectors 键必须为字符串且值必须为 Selector")
        if not isinstance(self.steps, list) or any(not isinstance(s, Step) for s in self.steps):
            raise ValidationError("flow.steps 必须为 Step 列表")
        if len(self.steps) == 0:
            raise ValidationError("flow.steps 不能为空")


__all__ = ["Selector", "Step", "Flow", "SelectorBy", "WaitState", "ActionName"]
