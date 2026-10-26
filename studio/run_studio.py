"""Entry point used by PyInstaller (the installed program starts here)."""

import sys

from ssas_studio.app import main

if __name__ == "__main__":
    sys.exit(main())
