"""Separate read-only bundled assets from persistent user workspace files."""

import sys
from pathlib import Path


def project_directory():
    if getattr(sys,'frozen',False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_path(relative):
    root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else project_directory()
    return root/relative
