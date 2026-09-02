from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [root / ".pytest_cache", root / ".ruff_cache", root / ".mypy_cache"]
    for target in targets:
        if target.is_dir() and root in target.parents:
            shutil.rmtree(target)


if __name__ == "__main__":
    main()
