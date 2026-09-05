"""Daily entry: import the current checkout, never install or repair dependencies."""
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
root = Path(os.environ.get("HIA_PROJECT_ROOT") or Path(__file__).resolve().parents[1]).resolve()
os.environ["HIA_PROJECT_ROOT"] = str(root)
sys.path.insert(0, str(root / "src"))

from studio.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["launcher"]))
