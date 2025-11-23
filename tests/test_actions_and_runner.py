from __future__ import annotations

import sys
from pathlib import Path
import types
import pytest

# ensure src on path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engine import actions as act  # type: ignore
from engine.flow_engine import FlowRunner  # type: ignore
from engine.models import Flow, Selector, Step  # type: ignore


class FakeEl:
    def __init__(self):
        self.cleared = False
        self.sent = []
        self.clicked = False

    def clear(self):
        self.cleared = True

    def send_keys(self, v):
        self.sent.append(v)

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self):
        self.urls = []
        self.scripts = []
        self.quit_called = False

    def get(self, url: str):
        self.urls.append(url)

    def execute_script(self, script, *args):
        self.scripts.append((script, args))

    def quit(self):
        self.quit_called = True


# ---------------- 10.5 动作执行（mock WebDriver） ----------------

def test_actions_navigate_calls_get(monkeypatch):
    d = FakeDriver()
    act.navigate(d, "https://example.com")
    assert d.urls == ["https://example.com"]


def test_actions_type_send_keys_and_clear(monkeypatch):
    d = FakeDriver()
    el = FakeEl()
    monkeypatch.setattr(act, "_wait_for_state", lambda *a, **k: el)
    act.type(d, ("id", "email"), "abc")
    assert el.cleared is True
    assert el.sent == ["abc"]


def test_actions_type_js_fallback(monkeypatch):
    d = FakeDriver()
    el = FakeEl()

    def bad_send(v):
        raise Exception("fail send_keys")

    el.send_keys = bad_send  # type: ignore
    monkeypatch.setattr(act, "_wait_for_state", lambda *a, **k: el)
    act.type(d, ("id", "email"), "abc")
    assert len(d.scripts) == 1
    script, args = d.scripts[0]
    assert "arguments[0].value" in script
    assert args[1] == "abc"


def test_actions_click(monkeypatch):
    d = FakeDriver()
    el = FakeEl()
    monkeypatch.setattr(act, "_wait_for_state", lambda *a, **k: el)
    act.click(d, ("id", "btn"))
    assert el.clicked is True


# ---------------- 10.6 optional 步骤：失败后继续 ----------------

def test_optional_step_continue(monkeypatch):
    # Build a flow: navigate -> click(optional True) -> sleep
    flow = Flow(
        name="opt",
        start_url="https://example.com",
        selectors={"btn": Selector(by="id", value="x")},
        steps=[
            Step(action="navigate"),
            Step(action="click", target="btn", optional=True),
            Step(action="sleep", value="10"),
        ],
    )

    # Patch actions in flow_engine to raise on click, but still allow navigate/sleep
    import engine.flow_engine as fe  # type: ignore

    calls = {"navigate": 0, "click": 0, "sleep": 0}

    def fake_nav(driver, url):
        calls["navigate"] += 1

    def fake_click(driver, locator):
        calls["click"] += 1
        raise RuntimeError("boom")

    def fake_sleep(ms):
        calls["sleep"] += 1

    monkeypatch.setattr(fe.act, "navigate", fake_nav)
    monkeypatch.setattr(fe.act, "click", fake_click)
    monkeypatch.setattr(fe.act, "sleep", fake_sleep)

    d = FakeDriver()
    # Should not raise because click is optional
    FlowRunner.execute(flow, d, account={}, context={})

    assert calls == {"navigate": 1, "click": 1, "sleep": 1}


def test_non_optional_step_raises(monkeypatch):
    flow = Flow(
        name="err",
        start_url="https://example.com",
        selectors={"btn": Selector(by="id", value="x")},
        steps=[Step(action="click", target="btn")],  # 非可选
    )

    import engine.flow_engine as fe  # type: ignore

    def boom(driver, locator):
        raise RuntimeError("boom")

    monkeypatch.setattr(fe.act, "click", boom)

    d = FakeDriver()
    with pytest.raises(RuntimeError):
        FlowRunner.execute(flow, d, account={}, context={})


# ---------------- 10.5 expect：超时抛出 ----------------

def test_actions_expect_timeout_raises_validationerror(monkeypatch):
    d = FakeDriver()

    class FakeTimeout(Exception):
        pass

    # 让 expect 捕获我们伪造的超时异常
    monkeypatch.setattr(act, "TimeoutException", FakeTimeout)

    def raise_timeout(*a, **k):
        raise FakeTimeout()

    monkeypatch.setattr(act, "_wait_for_state", raise_timeout)

    with pytest.raises(act.ValidationError):
        act.expect(d, ("id", "x"), "visible")
