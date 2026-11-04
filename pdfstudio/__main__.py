# -*- coding: utf-8 -*-
"""支持 python -m pdfstudio 方式启动。"""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
