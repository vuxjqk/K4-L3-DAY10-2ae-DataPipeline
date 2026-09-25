from __future__ import annotations

import sys

from pipelines.phase1 import main


if __name__ == "__main__":
    # Console Windows mac dinh cp1252 -> loi khi in tieng Viet/emoji.
    sys.stdout.reconfigure(encoding="utf-8")
    main()
