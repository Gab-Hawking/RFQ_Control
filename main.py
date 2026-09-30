"""Ponto de entrada do RFQ Control (usado também pelo PyInstaller)."""

import sys

from rfq_control.app import main

if __name__ == "__main__":
    sys.exit(main())
