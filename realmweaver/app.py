"""Application entry point."""

import sys

from PyQt6.QtWidgets import QApplication

from realmweaver import theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SceneCaster")
    theme.UI_SCALE   = theme._compute_ui_scale()
    theme.THUMB_W    = theme.px(240)
    theme.THUMB_H    = theme.px(135)
    theme.FONT_SERIF = theme._resolve_serif_family()
    theme.FONT_BODY  = theme._resolve_body_family()

    from realmweaver.control_window import ControlWindow
    win = ControlWindow()
    win.showMaximized()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
