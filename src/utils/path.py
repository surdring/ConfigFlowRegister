from pathlib import Path
import sys


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def resource_path(*parts: str) -> Path:
    return base_dir().joinpath(*parts).resolve()


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
