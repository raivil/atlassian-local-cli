import sys


def resolve_body(inline, file_path):
    """Resolve text content from inline arg or file (use '-' for stdin)."""
    if inline and file_path:
        print("Error: --body and --body-file are mutually exclusive.", file=sys.stderr)
        sys.exit(1)
    if file_path:
        if file_path == "-":
            return sys.stdin.read()
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return inline
