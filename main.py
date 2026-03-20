"""Backward-compatibility shim for PyInstaller and direct execution."""
from atlassian_local_cli.cli import main

if __name__ == "__main__":
    main()
