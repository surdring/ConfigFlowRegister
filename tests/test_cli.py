from __future__ import annotations

import sys
from pathlib import Path
import types
import pytest

# ensure src on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
import importlib


def _import_cli():
    return importlib.import_module("cli")


class DummyLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def test_cli_help_shows_and_exits(capsys):
    cli = _import_cli()
    with pytest.raises(SystemExit) as ei:
        cli._build_parser().parse_args(["--help"])  # argparse raises SystemExit(0)
    assert ei.value.code == 0
    # help text is printed by argparse; no assertion necessary here


def _patch_happy_path(cli, monkeypatch, tmp_path: Path):
    # setup_logger -> dummy
    monkeypatch.setattr(cli, "setup_logger", lambda: DummyLogger())

    # config
    cfg_dict = {
        "registration": {"default_count": 1, "interval_seconds": 0, "headless": True},
        "flow": {"file": str(tmp_path / "flow.toml")},
    }
    monkeypatch.setattr(cli.app_config, "load_config", lambda: cfg_dict)

    # Flow loader -> return minimal Flow (lazy import models)
    models = importlib.import_module("engine.models")
    Flow = getattr(models, "Flow")
    Step = getattr(models, "Step")
    flow_obj = Flow(name="x", steps=[Step(action="navigate")], selectors={})
    monkeypatch.setattr(cli.FlowLoader, "load", lambda p: flow_obj)

    # DM -> fake accounts
    class FakeDM:
        def __init__(self, config=None):  # noqa: ANN001
            self.config = config

        def generate_accounts(self, count: int):  # noqa: D401
            class A:
                id = 1
                email = "a@b"
                username = "a"
                password = "p"
                first_name = "F"
                last_name = "L"

            return [A()]

    monkeypatch.setattr(cli, "DataManager", FakeDM)

    # Browser lifecycle
    class D:  # fake driver
        pass

    monkeypatch.setattr(cli.BrowserProvider, "start_browser", lambda **k: D())
    monkeypatch.setattr(cli.BrowserProvider, "cleanup", lambda d: None)

    # run_batch -> success summary
    monkeypatch.setattr(
        cli, "run_batch", lambda *a, **k: {"results": [], "success": 1, "failed": 0, "total": 1, "elapsed_s": 0.1}
    )


def test_cli_main_success(monkeypatch, tmp_path: Path):
    cli = _import_cli()
    _patch_happy_path(cli, monkeypatch, tmp_path)
    code = cli.main(["--flow", str(tmp_path / "flow.toml"), "--count", "1", "--interval", "0"])
    assert code == 0


@pytest.mark.parametrize(
    "kind,code",
    [
        ("validation", 1),
        ("filenotfound", 1),
        ("keyboard", 130),
        ("runtime", 2),
    ],
)
def test_cli_exit_codes(monkeypatch, tmp_path: Path, kind: str, code: int):
    cli = _import_cli()
    _patch_happy_path(cli, monkeypatch, tmp_path)

    # Build exception per kind
    if kind == "validation":
        exc: Exception = cli.ValidationError("x")
        monkeypatch.setattr(cli.FlowLoader, "load", lambda p: (_ for _ in ()).throw(exc))
        ret = cli.main(["--flow", str(tmp_path / "flow.toml")])
        assert ret == code
        return
    if kind == "filenotfound":
        exc = FileNotFoundError("x")
        monkeypatch.setattr(cli.FlowLoader, "load", lambda p: (_ for _ in ()).throw(exc))
        ret = cli.main(["--flow", str(tmp_path / "flow.toml")])
        assert ret == code
        return
    if kind == "keyboard":
        exc = KeyboardInterrupt()
    else:
        exc = RuntimeError("x")

    # Otherwise let FlowLoader.load succeed and run_batch fail
    def raise_exc(*a, **k):
        raise exc

    monkeypatch.setattr(cli, "run_batch", raise_exc)
    ret = cli.main(["--flow", str(tmp_path / "flow.toml")])
    assert ret == code
