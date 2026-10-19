"""Windowless desktop entry point. User data lives beside the executable."""

import os
import sys

from zhishu_inspection.desktop import main


if __name__ == '__main__':
    # HTTPServer writes access logs even when Windows provides no console.
    for stream in ('stdout', 'stderr'):
        if getattr(sys, stream) is None:
            setattr(sys, stream, open(os.devnull, 'w', encoding='utf-8'))
    main()
