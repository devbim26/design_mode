"""Locate the project's InvokeAI environment on Windows and Linux."""
from pathlib import Path
import sys
import sysconfig


def site_packages(venv: Path) -> Path:
    """Use the running venv's layout, or discover an existing project venv.

    The Windows fallback preserves setup scripts' existing missing-venv
    diagnostics and their tests with synthetic Windows environments.
    """
    if venv.resolve() == Path(sys.prefix).resolve():
        return Path(sysconfig.get_path("purelib"))
    windows = venv / "Lib" / "site-packages"
    if windows.is_dir():
        return windows
    candidates = sorted((venv / "lib").glob("python*/site-packages"))
    if len(candidates) > 1:
        raise RuntimeError(f"Multiple Python environments in {venv}; run its Python explicitly")
    return candidates[0] if candidates else windows
