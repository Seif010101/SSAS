"""Start SSAS Studio."""

from __future__ import annotations

import os
import sys


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from . import logs
    from .resources import APP_NAME, ORG_NAME
    from .ui.context import AppContext
    from .ui.main_window import MainWindow
    from .ui.theme import app_icon
    from .ui.theme import apply as apply_theme

    logs.install()
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    apply_theme(app)
    app.setWindowIcon(app_icon())
    ctx = AppContext()
    win = MainWindow(ctx)
    win.show()
    if os.environ.get("SSAS_SMOKE_TEST"):
        # Used by the build to check that the packaged program starts.
        QTimer.singleShot(1500, app.quit)
    else:
        win.first_run_check()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
