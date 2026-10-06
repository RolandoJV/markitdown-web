# SPDX-FileCopyrightText: markitdown-web is an unofficial companion package.
# The underlying MarkItDown library is (c) Microsoft Corporation, MIT License.
# See README.md for attribution.

from .__about__ import __version__
from .config import Settings
from .app import create_app

__all__ = ["__version__", "Settings", "create_app"]
