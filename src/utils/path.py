from pathlib import Path
import sys


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _internal_dir() -> Path:
    """PyInstaller 6 one-dir layout puts data files under _internal/."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # fallback: _internal/ next to executable
        candidate = Path(sys.executable).parent / "_internal"
        if candidate.is_dir():
            return candidate
    return base_dir()


def resource_path(*parts: str) -> Path:
    # Try _internal/ first (PyInstaller 6 one-dir), then base_dir()
    p = _internal_dir().joinpath(*parts).resolve()
    if p.exists():
        return p
    return base_dir().joinpath(*parts).resolve()


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
