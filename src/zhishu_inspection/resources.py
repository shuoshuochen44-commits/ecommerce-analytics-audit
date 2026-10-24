"""Separate read-only bundled assets from persistent user workspace files."""

import sys
from pathlib import Path


def project_directory():
    if getattr(sys,'frozen',False):
        return Path(sys.executable).resolve().parent
    checkout = Path(__file__).resolve().parents[2]
    # An installed package must never put a default workspace in site-packages.
    return checkout if (checkout / 'pyproject.toml').is_file() else Path.cwd()


def resource_path(relative):
    if getattr(sys,'frozen',False):
        root = Path(sys._MEIPASS)
    else:
        package = Path(__file__).resolve().parent
        root = package if (package / 'sql').is_dir() else package.parents[1]
    return root/relative
