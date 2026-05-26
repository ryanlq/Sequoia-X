"""Sequoia-X V2 向后兼容入口。

旧参数映射：
  python main.py               → sequoia daily
  python main.py --backfill    → sequoia backfill
  python main.py --sync        → sequoia sync
  python main.py --analyze     → sequoia analyze
"""

import sys

from sequoia_x.cli import app

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv = [sys.argv[0], "daily"]
    elif "--backfill" in sys.argv:
        sys.argv = [sys.argv[0], "backfill"] + [a for a in sys.argv[1:] if a != "--backfill"]
    elif "--sync" in sys.argv:
        sys.argv = [sys.argv[0], "sync"] + [a for a in sys.argv[1:] if a != "--sync"]
    elif "--analyze" in sys.argv:
        sys.argv = [sys.argv[0], "analyze"] + [a for a in sys.argv[1:] if a != "--analyze"]
    app()
