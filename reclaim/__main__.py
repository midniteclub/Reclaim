"""Entry point for ``python -m reclaim`` and the packaged ``Reclaim.exe``.

With command-line arguments it runs the CLI; with no arguments it launches the
GUI.
"""
import sys


def main() -> int:
    if len(sys.argv) > 1:
        from reclaim.cli.main import main as cli_main
        return cli_main(sys.argv[1:])

    try:
        from reclaim.gui.app import run as gui_run
    except Exception as exc:  # noqa: BLE001 - GUI optional / display may be missing
        print(f"Could not start the GUI ({exc}).")
        print("Use the command line instead, e.g.:  reclaim scan C:\\Users")
        return 1
    gui_run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
