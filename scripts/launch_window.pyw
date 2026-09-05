"""Windowed launcher with a visible failure message and project-local diagnostics."""
import ctypes
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
root = Path(os.environ.get("HIA_PROJECT_ROOT") or Path(__file__).resolve().parents[1]).resolve()
os.environ["HIA_PROJECT_ROOT"] = str(root)
sys.path.insert(0, str(root / "src"))


def start():
    from studio.common import AppPaths
    from studio.__main__ import main
    paths = AppPaths(root)
    folder = paths.local("logs")
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "launcher.log").open("a", encoding="utf-8") as log:
        sys.stdout = sys.stderr = log
        try:
            result = main(["launcher"])
        except Exception as exc:
            print("Launcher failed:", type(exc).__name__)
            result = 1
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
    if result:
        ctypes.windll.user32.MessageBoxW(None,
            "Studio could not open. Run Setup Studio.cmd first.\n"
            "Details: " + str(folder / "launcher.log"), "Big-Chicken Houdini Studio", 0x10)
    return result


if __name__ == "__main__":
    try:
        exit_code = start()
    except Exception:
        # Missing checkout/permissions can fail before the local log opens.
        ctypes.windll.user32.MessageBoxW(None,
            "Studio could not load this installation. Check HIA_PROJECT_ROOT and run Setup Studio.cmd.",
            "Big-Chicken Houdini Studio", 0x10)
        exit_code = 1
    raise SystemExit(exit_code)
