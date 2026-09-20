"""`python3 -m offload` — the same entry point as the `offload` console script."""
import sys

from offload.cli import main

if __name__ == "__main__":
    sys.exit(main())
