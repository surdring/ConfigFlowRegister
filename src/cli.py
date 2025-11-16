#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Robust imports for both dev and packaged contexts
try:
    from .utils.logger import setup_logger
    from .utils import config as app_config
    from .utils.exceptions import ValidationError
    from .engine.flow_engine import FlowLoader, run_batch
    from .browser.provider import BrowserProvider
    from .data.data_manager import DataManager, Configuration
except Exception:
    try:
        from src.utils.logger import setup_logger  # type: ignore
        from src.utils import config as app_config  # type: ignore
        from src.utils.exceptions import ValidationError  # type: ignore
        from src.engine.flow_engine import FlowLoader, run_batch  # type: ignore
        from src.browser.provider import BrowserProvider  # type: ignore
        from src.data.data_manager import DataManager, Configuration  # type: ignore
    except Exception:
        # Last resort: add src to sys.path
        import os

        SRC = Path(__file__).resolve().parent
        if str(SRC) not in sys.path:
            sys.path.insert(0, str(SRC))
        from src.utils.logger import setup_logger  # type: ignore
        from src.utils import config as app_config  # type: ignore
        from src.utils.exceptions import ValidationError  # type: ignore
        from src.engine.flow_engine import FlowLoader, run_batch  # type: ignore
        from src.browser.provider import BrowserProvider  # type: ignore
        from src.data.data_manager import DataManager, Configuration  # type: ignore


def _build_parser() -> argparse.ArgumentParser:
    epilog = (
        "示例:\n"
        "  python -m src.cli --flow flows/windsurf_register.toml --count 3 --interval 2\n"
        "  # 使用环境变量占位符（已由引擎支持 {env.*}）\n"
        "  set REG_EMAIL=test@example.com  # Windows\n"
        "  export REG_EMAIL=test@example.com  # Linux/macOS\n"
        "  python -m src.cli --flow flows/windsurf_register.toml\n"
    )
    p = argparse.ArgumentParser(
        prog="ConfigFlowRegister CLI",
        description=(
            "配置驱动批量注册 - 命令行接口。\n"
            "- Flow 由 TOML 定义 (selectors/steps)。\n"
            "- 变量系统支持 {config.*}/{account.*}/{env.*}/{flow.*}。\n"
            "- 无头模式下人机验证通过率极低，建议 headless=false。"
        ),
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--flow", type=str, help="Flow TOML 路径（覆盖 config.flow.file）")
    p.add_argument("--count", type=int, help="注册账号数量，默认取自 config.registration.default_count")
    p.add_argument("--interval", type=float, help="账号间隔秒数，默认取自 config.registration.interval_seconds")
    return p


def _to_account_dicts(accounts: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in accounts:
        try:
            # dataclass Account
            out.append(
                {
                    "id": getattr(a, "id", None),
                    "email": getattr(a, "email", None),
                    "username": getattr(a, "username", None),
                    "password": getattr(a, "password", None),
                    "first_name": getattr(a, "first_name", None),
                    "last_name": getattr(a, "last_name", None),
                }
            )
        except Exception:
            # already dict-like
            try:
                out.append(
                    {
                        "id": a.get("id"),
                        "email": a.get("email"),
                        "username": a.get("username"),
                        "password": a.get("password"),
                        "first_name": a.get("first_name"),
                        "last_name": a.get("last_name"),
                    }
                )
            except Exception:
                raise ValidationError("无效的账号对象，无法转换为字典")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    logger = setup_logger()
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        # 配置
        cfg_dict = app_config.load_config()
        cfg = Configuration.from_json(cfg_dict)

        # 参数合并
        count = args.count if args.count is not None else cfg.registration.default_count
        interval = args.interval if args.interval is not None else cfg.registration.interval_seconds

        # Flow 路径解析（支持 CLI 覆盖 & 相对路径资源解析）
        flow_path = app_config.get_flow_file(cfg_dict, cli_flow=args.flow)
        logger.info(f"使用 Flow: {flow_path}")

        # 加载 Flow（包含严格校验）
        flow = FlowLoader.load(flow_path)

        # 生成账号（使用 DataManager 内置生成器）
        dm = DataManager(config=cfg)
        accounts_objs = dm.generate_accounts(count)
        accounts = _to_account_dicts(accounts_objs)

        # 批量执行（跨平台浏览器管理）
        def _factory():
            return BrowserProvider.start_browser(headless=cfg.registration.headless)

        def _cleanup(drv):
            BrowserProvider.cleanup(drv)

        summary = run_batch(
            flow,
            accounts,
            interval_seconds=interval,
            driver_factory=_factory,
            driver_cleanup=_cleanup,
            base_context={"config": cfg_dict},
        )

        # 结果输出
        logger.info(
            "执行统计: total=%d, success=%d, failed=%d, elapsed=%.2fs",
            summary["total"],
            summary["success"],
            summary["failed"],
            summary["elapsed_s"],
        )
        # 约定退出码：0 成功；若存在失败但流程未抛异常，仍视为成功运行
        return 0

    except (ValidationError, FileNotFoundError) as e:
        logger.error(f"配置/文件错误: {e}")
        return 1
    except KeyboardInterrupt:
        logger.warning("用户中断（KeyboardInterrupt）")
        return 130
    except Exception as e:
        logger.error(f"执行失败: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
