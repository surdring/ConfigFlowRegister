from __future__ import annotations

import sys
from pathlib import Path
import threading
import pytest

# ensure src on path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import engine.flow_engine as fe  # type: ignore
from engine.models import Flow, Selector, Step  # type: ignore


class DummyEvent:
    def __init__(self):
        self.wait_called = 0
        self.clear_called = 0

    def wait(self):
        self.wait_called += 1
        return True

    def clear(self):
        self.clear_called += 1


class DummyDriver:
    def quit(self):
        pass


def test_flowrunner_execute_all_actions(monkeypatch):
    flow = Flow(
        name="all",
        start_url="https://example.com",
        selectors={
            "email": Selector(by="id", value="email"),
            "btn": Selector(by="id", value="btn"),
        },
        steps=[
            Step(action="navigate", value="https://example.com/start"),
            Step(action="sleep", value="5"),
            Step(action="wait", target="email", state="present"),
            Step(action="type", target="email", value="{account.email}"),
            Step(action="click", target="btn"),
            Step(action="expect", target="email", state="visible"),
            Step(action="pause_for_manual", message="msg"),
        ],
    )

    calls = {k: 0 for k in ["navigate", "sleep", "wait", "type", "click", "expect"]}

    monkeypatch.setattr(fe.act, "navigate", lambda d, url: calls.__setitem__("navigate", calls["navigate"] + 1))
    monkeypatch.setattr(fe.act, "sleep", lambda ms: calls.__setitem__("sleep", calls["sleep"] + 1))
    monkeypatch.setattr(fe.act, "wait", lambda *a, **k: calls.__setitem__("wait", calls["wait"] + 1))
    monkeypatch.setattr(fe.act, "type", lambda *a, **k: calls.__setitem__("type", calls["type"] + 1))
    monkeypatch.setattr(fe.act, "click", lambda *a, **k: calls.__setitem__("click", calls["click"] + 1))
    monkeypatch.setattr(fe.act, "expect", lambda *a, **k: calls.__setitem__("expect", calls["expect"] + 1))

    evt = DummyEvent()
    ctx = {"account": {"email": "a@b"}, "manual_continue_event": evt}

    fe.FlowRunner.execute(flow, DummyDriver(), account={"email": "a@b"}, context=ctx)

    assert all(v == 1 for v in calls.values())
    assert evt.wait_called == 1 and evt.clear_called == 1


def test_run_batch_aggregates_results(monkeypatch):
    flow = Flow(
        name="b",
        start_url="https://x",
        selectors={},
        steps=[Step(action="navigate")],
    )

    # one success, one failure
    sequence = [None, RuntimeError("x")]

    def fake_exec(flow, driver, account=None, context=None):  # noqa: ANN001
        val = sequence.pop(0)
        if val is not None:
            raise val

    monkeypatch.setattr(fe.FlowRunner, "execute", fake_exec)

    drivers = []

    def driver_factory():
        d = DummyDriver()
        drivers.append(d)
        return d

    result = fe.run_batch(
        flow,
        accounts=[{"email": "a"}, {"email": "b"}],
        interval_seconds=0,
        driver_factory=driver_factory,
    )

    assert result["total"] == 2
    assert result["success"] == 1
    assert result["failed"] == 1


def test_validate_flow_errors(monkeypatch):
    # expose _validate_flow
    _validate_flow = fe._validate_flow

    # 1) missing flow section
    data = {"steps": []}
    flow = Flow(name="x", steps=[Step(action="navigate")], selectors={})
    with pytest.raises(fe.ValidationError):
        _validate_flow(data, flow)

    # 2) missing steps array
    data = {"flow": {}}
    with pytest.raises(fe.ValidationError):
        _validate_flow(data, flow)

    # 3) undefined selector referenced
    data = {"flow": {}, "steps": [{"action": "click", "target": "email"}], "selectors": {}}
    flow = Flow(name="x", steps=[Step(action="click", target="email")], selectors={})
    with pytest.raises(fe.ValidationError):
        _validate_flow(data, flow)


def test_variable_resolve_obj():
    obj = {"a": "{x.y}", "b": ["{x.y}", {"z": "{x.y}"}]}
    ctx = {"x": {"y": 3}}
    out = fe.VariableResolver.resolve_obj(obj, ctx)
    assert out == {"a": "3", "b": ["3", {"z": "3"}]}
