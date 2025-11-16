from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .config_loader import (
    load_config as _load_config,
    save_config as _save_config,
    get_default_config,  # re-export
)
from .exceptions import ValidationError  # re-export for callers
from .path import resource_path

DEFAULT_FLOW_FILE = "flows/windsurf_register.toml"


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    return _load_config(config_path)


essave_config = _save_config  # deprecated alias

def save_config(config: Dict[str, Any], config_path: Optional[Path] = None) -> None:
    _save_config(config, config_path)


def _resolve_flow_under_base(path_str: str) -> Path:
    """Resolve a flow path relative to application base directory with smart fallbacks.

    Rules:
    - If absolute, return as-is.
    - Try base_dir/<path_str> first.
    - Also try base_dir/flows/<name> to support packaged layout.
    - Also try base_dir/<name> to support keeping file next to EXE.
    The first existing path is returned; otherwise, return base_dir/<path_str>.
    """
    p = Path(path_str)
    if p.is_absolute():
        return p
    candidates = []
    # 1) as given under base
    candidates.append(resource_path(str(p)))
    # 2) flows/<name> under base
    candidates.append(resource_path("flows", p.name))
    # 3) root <name> under base
    candidates.append(resource_path(p.name))
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            # best-effort existence check
            pass
    # fallback to as-given under base
    return candidates[0]


def get_flow_file(config: Dict[str, Any], cli_flow: Optional[str] = None) -> Path:
    """Resolve Flow TOML path from CLI or config file.

    Priority: cli_flow > config['flow']['file'] > DEFAULT_FLOW_FILE.
    Returned path will be absolute and relative to base resource directory when needed.
    """
    if cli_flow:
        return _resolve_flow_under_base(cli_flow)

    flow_cfg = config.get("flow") if isinstance(config.get("flow"), dict) else None
    flow_file = None
    if isinstance(flow_cfg, dict):
        flow_file = flow_cfg.get("file")

    if flow_file:
        return _resolve_flow_under_base(str(flow_file))

    return _resolve_flow_under_base(DEFAULT_FLOW_FILE)
