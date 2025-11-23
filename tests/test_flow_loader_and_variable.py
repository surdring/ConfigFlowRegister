from __future__ import annotations

import os
import sys
from pathlib import Path
import textwrap
import pytest

# ensure src on path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engine.flow_engine import FlowLoader, VariableResolver, _get_locator  # type: ignore
from engine.models import Flow, Step, Selector  # type: ignore
try:
    from utils.exceptions import ValidationError  # type: ignore
except Exception:
    from src.utils.exceptions import ValidationError  # type: ignore


# ---------------- 10.1 TOML 加载 ----------------

def test_load_flow_valid(tmp_path: Path):
    toml = textwrap.dedent(
        """
        [flow]
        name = "Test Flow"
        start_url = "https://example.com"
        timeout_ms = 1000

        [selectors.email]
        by = "id"
        value = "email"

        [[steps]]
        action = "navigate"

        [[steps]]
        action = "type"
        target = "email"
        value = "{account.email}"
        """
    ).strip()
    f = tmp_path / "flow.toml"
    f.write_text(toml, encoding="utf-8")
    flow = FlowLoader.load(f)
    assert flow.name == "Test Flow"
    assert "email" in flow.selectors
    assert len(flow.steps) == 2


def test_load_flow_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        FlowLoader.load(tmp_path / "no.toml")


def test_load_flow_invalid_toml(tmp_path: Path):
    # broken toml
    f = tmp_path / "broken.toml"
    f.write_text("[flow\nname='x'", encoding="utf-8")
    with pytest.raises(Exception):
        FlowLoader.load(f)


# ---------------- 10.2/10.3 变量替换与错误 ----------------

def test_variable_resolver_all_namespaces(monkeypatch):
    ctx = {
        "config": {"foo": "bar", "site": {"title": "T"}},
        "account": {"email": "e@x", "password": "p"},
        "flow": {"start_url": "https://a", "foo": "baz"},
    }
    monkeypatch.setenv("MY_ENV", "hello")

    assert VariableResolver.resolve("{config.foo}", ctx) == "bar"
    assert VariableResolver.resolve("{account.email}", ctx) == "e@x"
    assert VariableResolver.resolve("{env.MY_ENV}", ctx) == "hello"
    assert VariableResolver.resolve("{flow.start_url}", ctx) == "https://a"


def test_variable_resolver_missing_raises():
    ctx = {"config": {}, "account": {}, "flow": {}}
    with pytest.raises(ValidationError):
        VariableResolver.resolve("{account.missing}", ctx)


# ---------------- 10.4 Selector 解析 ----------------

def test_get_locator_mapping():
    flow = Flow(
        name="X",
        start_url="https://x",
        selectors={
            "sid": Selector(by="id", value="email"),
            "scss": Selector(by="css", value="#email"),
            "sx": Selector(by="xpath", value="//input[@id='email']"),
        },
        steps=[Step(action="navigate")],
    )
    by_id, val_id = _get_locator(flow, "sid")
    assert val_id == "email"
    by_css, val_css = _get_locator(flow, "scss")
    assert val_css == "#email"
    by_x, val_x = _get_locator(flow, "sx")
    assert val_x.startswith("//")
