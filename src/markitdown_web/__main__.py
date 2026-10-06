# SPDX-FileCopyrightText: markitdown-web is an unofficial companion package.
# The underlying MarkItDown library is (c) Microsoft Corporation, MIT License.

from __future__ import annotations

import argparse
import logging
import sys

from .__about__ import __version__
from .app import create_app
from .config import Settings

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")

_PUBLIC_BIND_WARNING = """
WARNING: The server is being bound to a non-localhost interface ({host}).
This exposes the server to other machines on the network or Internet.
The server has NO authentication and runs with your user's privileges.
Any process or user that can reach this interface can convert files and
trigger conversions with your privileges.
Only proceed if you understand the security implications.
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="markitdown-web",
        description="Run a local web UI for converting files to Markdown.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host/interface to bind (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to listen on (default: 8000)."
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="Uvicorn log level (default: info).",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper(), stream=sys.stderr)

    settings = Settings.from_env()
    is_loopback = args.host.strip().lower() in _LOOPBACK_HOSTS
    local_only = settings.local_only if is_loopback else False

    if not is_loopback:
        print(_PUBLIC_BIND_WARNING.format(host=args.host), file=sys.stderr)

    app = create_app(settings, local_only=local_only)

    try:
        import uvicorn
    except ImportError:  # pragma: no cover - dependency declared in pyproject
        print(
            "uvicorn is required to run the web UI. Install it with:\n"
            "  pip install 'markitdown-web'",
            file=sys.stderr,
        )
        raise SystemExit(1)

    display_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(f"markitdown-web {__version__} -> http://{display_host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
