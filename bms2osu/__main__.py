import sys


def _run() -> int:
    # No arguments -> GUI window, otherwise the command line interface.
    if len(sys.argv) <= 1:
        from .gui import main
        return main([])
    from .cli import main
    return main()


if __name__ == "__main__":
    sys.exit(_run())
