from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest

# ensure src on path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from utils import config_loader as cl  # type: ignore
from utils.exceptions import ValidationError  # type: ignore


# ---------------- 10.7 配置加载：路径适配 ----------------

def test_load_config_dev_creates_default_in_cwd(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    cfg = cl.load_config()
    # default should be returned and file should be created in CWD
    f = tmp_path / "config.json"
    assert f.exists()
    assert isinstance(cfg, dict)
    assert "registration" in cfg


def test_load_config_frozen_uses_executable_dir(monkeypatch, tmp_path: Path):
    exe_dir = tmp_path / "appdir"
    exe_dir.mkdir()
    fake_exe = exe_dir / "app.exe"
    fake_exe.write_text("bin", encoding="utf-8")

    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    cfg = cl.load_config()
    f = exe_dir / "config.json"
    assert f.exists()
    assert "registration" in cfg


# ---------------- 10.8 原子写入 ----------------

def test_save_config_atomic(tmp_path: Path):
    cfg = cl.get_default_config()
    target = tmp_path / "config.json"
    cl.save_config(cfg, target)
    assert target.exists()
    # temp file should not remain (config.tmp)
    assert not (tmp_path / "config.tmp").exists()


def test_save_config_replace_failure(monkeypatch, tmp_path: Path):
    cfg = cl.get_default_config()
    target = tmp_path / "config.json"

    # Patch Path.replace to raise when called on the temp file
    original_replace = Path.replace

    def fail_replace(self, other):  # type: ignore[override]
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace, raising=True)

    with pytest.raises(ValidationError):
        cl.save_config(cfg, target)

    # restore (pytest will restore via monkeypatch automatically on teardown)
