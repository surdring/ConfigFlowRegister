from __future__ import annotations

import sys
from pathlib import Path
import os
import pytest
import importlib

# ensure src on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_get_flow_file_precedence_and_defaults(monkeypatch, tmp_path: Path):
    app_config = importlib.import_module("utils.config")
    # default
    cfg = {"flow": {"file": "flows/windsurf_register.toml"}}
    p = app_config.get_flow_file(cfg)
    assert p.name == "windsurf_register.toml"

    # cli overrides and relative path resolved
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flows").mkdir()
    (tmp_path / "flows" / "custom.toml").write_text("", encoding="utf-8")
    p2 = app_config.get_flow_file(cfg, cli_flow="flows/custom.toml")
    assert p2.exists()

    # missing config.flow.file -> use default
    cfg2 = {}
    p3 = app_config.get_flow_file(cfg2)
    assert p3.name == app_config.DEFAULT_FLOW_FILE.split("/")[-1]


def test_path_base_dir_and_resource_path_dev(monkeypatch, tmp_path: Path):
    upath = importlib.import_module("utils.path")
    monkeypatch.chdir(tmp_path)
    # dev mode
    assert upath.base_dir() == tmp_path
    p = upath.resource_path("a", "b.txt")
    assert str(p).endswith("a\\b.txt") or str(p).endswith("a/b.txt")


def test_path_base_dir_frozen(monkeypatch, tmp_path: Path):
    upath = importlib.import_module("utils.path")
    exe = tmp_path / "app" / "app.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("bin", encoding="utf-8")

    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert upath.base_dir() == exe.parent


def test_ensure_dir(tmp_path: Path):
    upath = importlib.import_module("utils.path")
    d = tmp_path / "x" / "y"
    out = upath.ensure_dir(d)
    assert out.exists() and out.is_dir()
