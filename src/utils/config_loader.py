"""
配置文件加载模块

负责加载、验证和保存应用程序配置。
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from .exceptions import ValidationError
from .logger import default_logger as logger


def get_default_config() -> Dict[str, Any]:
    """
    获取默认配置
    
    Returns:
        默认配置字典
    """
    return {
        "email": {
            "address": "enc:O1eVQws7gNmcx4wG21yK",
            "password": "enc:YwDZG1xq1YKqzJZS21GG3g==",
            "imap_server": "imap.qq.com",
            "imap_port": 993,
            "subject_keywords": ["windsurf", "verify"],
            "time_window_seconds": 300
        },
        "registration": {
            "default_count": 5,
            "interval_seconds": 5,
            "browser_type": "chrome",
            "headless": False,
            "timeout_seconds": 30,
            "max_retries": 3,
            "domain": "yaoshangxian.top",
            "url": "https://windsurf.com/account/register",
            "password": "xqxatcdj1014"
        },
        "flow": {
            "file": "flows/windsurf_register.toml"
        },
        "export": {
            "format": "csv",
            "include_failed": False
        }
    }


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径，None则使用默认路径
        
    Returns:
        配置字典（如果文件不存在则返回默认配置）
        
    Raises:
        ValidationError: 配置文件格式错误
    """
    if config_path is None:
        # 在打包环境下，将配置文件固定到可执行文件同级目录
        import sys
        base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
        config_path = base_dir / "config.json"
    
    if not config_path.exists():
        logger.warning(f"配置文件不存在: {config_path}")
        logger.info("正在创建默认配置文件...")
        # 获取默认配置
        default_config = get_default_config()
        # 保存为配置文件
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info(f"✓ 已创建默认配置文件: {config_path}")
            logger.info("  默认配置已生成，email段将被忽略，可直接使用")
        except Exception as e:
            logger.warning(f"创建配置文件失败: {e}")
        return default_config
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # 验证必需字段
        _validate_config(config)
        
        logger.info(f"成功加载配置文件: {config_path}")
        return config
        
    except json.JSONDecodeError as e:
        raise ValidationError(f"配置文件格式错误: {e}")
    except Exception as e:
        raise ValidationError(f"加载配置文件失败: {e}")


def save_config(config: Dict[str, Any], config_path: Optional[Path] = None) -> None:
    """
    保存配置到文件
    
    Args:
        config: 配置字典
        config_path: 配置文件路径，None则使用默认路径
        
    Raises:
        ValidationError: 配置验证失败或保存失败
    """
    if config_path is None:
        config_path = Path("config.json")
    
    # 验证配置
    _validate_config(config)
    
    try:
        # 原子性写入（先写临时文件再重命名）
        temp_path = config_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        temp_path.replace(config_path)
        logger.info(f"配置已保存到: {config_path}")
        
    except Exception as e:
        raise ValidationError(f"保存配置失败: {e}")


def _validate_config(config: Dict[str, Any]) -> None:
    """
    验证配置完整性
    
    Args:
        config: 配置字典
        
    Raises:
        ValidationError: 配置验证失败
    """
    errors = []
    if not isinstance(config, dict):
        raise ValidationError("配置根对象必须为字典")
    
    # 验证email配置（允许空值，用户可以在GUI中填写；缺失email段也允许）
    if "email" in config:
        email_config = config["email"]
        # 只在有值时验证格式；若以 "enc:" 开头则视为加密值，不做 '@' 校验
        addr = str(email_config.get("address", "") or "")
        if addr and not addr.startswith("enc:") and "@" not in addr:
            errors.append("email.address格式无效")
    
    # 验证 registration 段（必需）
    reg_config = config.get("registration")
    if not isinstance(reg_config, dict):
        errors.append("缺少 registration 段或类型错误，应为对象")
    else:
        default_count = reg_config.get("default_count", 10)
        if not isinstance(default_count, int) or not 1 <= default_count <= 100:
            errors.append("registration.default_count必须为1-100之间的整数")

        interval = reg_config.get("interval_seconds", 5)
        if not isinstance(interval, int) or interval < 0:
            errors.append("registration.interval_seconds必须为非负整数")

        headless = reg_config.get("headless", False)
        if not isinstance(headless, bool):
            errors.append("registration.headless必须为布尔类型")

        timeout_seconds = reg_config.get("timeout_seconds", 30)
        if not isinstance(timeout_seconds, int) or timeout_seconds < 0:
            errors.append("registration.timeout_seconds必须为非负整数")

        max_retries = reg_config.get("max_retries", 3)
        if not isinstance(max_retries, int) or max_retries < 0:
            errors.append("registration.max_retries必须为非负整数")

    # 验证 flow 段（可选，但若存在需合法）
    if "flow" in config:
        flow_cfg = config.get("flow")
        if not isinstance(flow_cfg, dict):
            errors.append("flow 段类型错误，应为对象")
        else:
            f = flow_cfg.get("file")
            if f is not None and not isinstance(f, str):
                errors.append("flow.file 必须为字符串路径")

    # 验证 export 段（可选）
    if "export" in config:
        export_cfg = config.get("export")
        if not isinstance(export_cfg, dict):
            errors.append("export 段类型错误，应为对象")
        else:
            fmt = export_cfg.get("format", "csv")
            if fmt not in ("csv", "json"):
                errors.append("export.format 仅支持 csv 或 json")
            inc_failed = export_cfg.get("include_failed", False)
            if not isinstance(inc_failed, bool):
                errors.append("export.include_failed 必须为布尔类型")
    
    if errors:
        raise ValidationError("配置验证失败:\n" + "\n".join(f"- {e}" for e in errors))
