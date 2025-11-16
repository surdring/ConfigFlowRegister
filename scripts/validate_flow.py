from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

# Import project modules with fallbacks
try:
    from src.engine.flow_engine import FlowLoader, VariableResolver
    from src.utils import config as app_config
except Exception:
    # Running from repo root
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from engine.flow_engine import FlowLoader, VariableResolver  # type: ignore
    import utils.config as app_config  # type: ignore


PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_]+)\.([^{}]+)\}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate Flow TOML and placeholders")
    p.add_argument("--flow", required=True, help="Path to Flow TOML file")
    p.add_argument("--config", default=None, help="Path to config.json (optional)")
    p.add_argument(
        "--account",
        default=None,
        help='Account JSON string, e.g. {"email":"a@b.com","password":"x"}',
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Load config
    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.exists():
            print(f"[ERROR] config not found: {cfg_path}")
            return 1
        config = app_config.load_config(cfg_path)
    else:
        config = app_config.load_config(None)

    # Account
    if args.account:
        try:
            account: Dict[str, Any] = json.loads(args.account)
        except Exception as e:
            print(f"[ERROR] invalid --account JSON: {e}")
            return 1
    else:
        account = {
            "email": "test@example.com",
            "password": "P@ssw0rd123",
            "first_name": "Test",
            "last_name": "User",
        }

    # Load flow
    flow_path = Path(args.flow)
    try:
        flow = FlowLoader.load(flow_path)
    except Exception as e:
        print(f"[ERROR] load flow failed: {e}")
        return 1

    # Build context (flow.start_url + variables)
    flow_ctx: Dict[str, Any] = {"start_url": flow.start_url}
    flow_ctx.update(flow.variables or {})
    ctx = {"config": config, "account": account, "flow": flow_ctx}

    # Validate placeholders resolution in step fields (value/message)
    unresolved = 0
    for i, s in enumerate(flow.steps):
        for field_name in ("value", "message"):
            raw = getattr(s, field_name)
            if isinstance(raw, str):
                try:
                    resolved = VariableResolver.resolve(raw, ctx)
                except Exception as e:
                    print(f"[ERROR] step#{i} field '{field_name}' resolve failed: {e}")
                    return 1
                if PLACEHOLDER_RE.search(resolved):
                    unresolved += 1
                    print(
                        f"[WARN] step#{i} field '{field_name}' has unresolved placeholders: {resolved}"
                    )

    # Summary
    print("[OK] Flow parsed successfully")
    print(f"- name: {flow.name}")
    print(f"- selectors: {len(flow.selectors)}")
    print(f"- steps: {len(flow.steps)}")
    if unresolved:
        print(f"[WARN] unresolved placeholders count: {unresolved}")
    else:
        print("[OK] all placeholders resolved in text fields")

    return 0


if __name__ == "__main__":
    sys.exit(main())
