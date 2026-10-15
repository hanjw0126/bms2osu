"""PyInstaller entry point (relative imports cannot be used in the entry script).

- No arguments, or only paths (e.g. folders dropped on the exe) -> GUI window
- Any option such as --remove-scratch / --help                -> command line mode
"""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]  # old macOS Finder arg
    if any(a.startswith("-") for a in args):
        from bms2osu.cli import main as cli_main
        sys.exit(cli_main(args))
    from bms2osu.gui import main as gui_main
    sys.exit(gui_main(args))
