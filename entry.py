"""PyInstaller entry point (relative imports cannot be used in the entry script)."""
import multiprocessing
import sys

from bms2osu.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
