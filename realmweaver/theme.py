"""Theme, DPI scaling, paths, and shared UI helpers.

This module must stay dependency-free within the package (only PyQt6/stdlib)
so every other module can import it without circular imports.

NOTE: UI_SCALE, THUMB_W, THUMB_H, FONT_SERIF and FONT_BODY are mutated at app
startup (see realmweaver.app.main). Always access them as `theme.NAME`, never
`from theme import NAME`, or you'll freeze the pre-startup default.
"""

import os

from PyQt6.QtWidgets import QApplication, QFileDialog, QPushButton, QScroller
from PyQt6.QtCore import Qt

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
GIF_EXT   = {".gif"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
ALL_EXT   = IMAGE_EXT | GIF_EXT | VIDEO_EXT

THUMB_W: int = 240
THUMB_H: int = 135

APP_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(APP_DIR, "data")
MEDIA_DIR = os.path.join(APP_DIR, "media")
VIDEOS_DIR = os.path.join(MEDIA_DIR, "videos")
GIFS_DIR   = os.path.join(MEDIA_DIR, "gifs")
IMAGES_DIR = os.path.join(MEDIA_DIR, "images")
ASSETS_DIR = os.path.join(MEDIA_DIR, "assets")
MUSIC_DIR  = os.path.join(MEDIA_DIR, "music")
os.makedirs(DATA_DIR, exist_ok=True)
for _d in (MEDIA_DIR, VIDEOS_DIR, GIFS_DIR, IMAGES_DIR, ASSETS_DIR, MUSIC_DIR):
    os.makedirs(_d, exist_ok=True)

CONFIG_FILE  = os.path.join(DATA_DIR, "scenecaster_scenes.json")
TRANSITION_MS = 300   # scene crossfade duration (ms)
MUSIC_FADE_MS = 500   # music fade duration (ms)

# Non-native dialogs inherit the app's scaled font/stylesheet, so they stay
# usable on high-DPI touch panels (the OS-native picker ignores our scaling).
_DIALOG_OPTS = QFileDialog.Option.DontUseNativeDialog

# ─── DPI Auto-Scale ───────────────────────────────────────────────────────────
def _compute_ui_scale() -> float:
    """
    Compute scale relative to a 96-DPI baseline using the screen's physical size
    in mm (which Qt reports accurately) divided by logical pixel count.
    This is reliable regardless of Windows DPI scaling percentage.
    Touch-first minimum of 2.0 ensures usable targets on high-DPI panels.
    """
    screen = QApplication.primaryScreen()
    if screen is None:
        return 2.0
    phys = screen.physicalSize()   # physical millimetres (reliable on Windows)
    geo  = screen.geometry()       # logical pixels (accounts for Windows scaling)
    if phys.width() > 10:
        # True logical DPI = logical pixels per inch
        logical_dpi = geo.width() / (phys.width() / 25.4)
        scale = logical_dpi / 96.0
    else:
        scale = screen.logicalDotsPerInch() / 96.0
    # Touch-first: always at least 2.0× so targets are ≥ 10 mm on any panel
    return max(2.0, min(4.0, scale))

UI_SCALE: float = 2.0

def px(base: int) -> int:
    return max(1, round(base * UI_SCALE))

def pt(base: int) -> int:
    return max(6, round(base * UI_SCALE))

# ─── Arcane Color Palette ─────────────────────────────────────────────────────
C_VOID          = "#070510"
C_PANEL         = "#0f0d1e"
C_CARD          = "#16122b"
C_INPUT         = "#1e1935"
C_HOVER         = "#2a2450"
C_ACCENT_GOLD   = "#c9a227"
C_ACCENT_PURPLE = "#7c3aed"
C_GLOW_PURPLE   = "#a855f7"
C_GOLD_DIM      = "#6b5210"
C_BORDER        = "#2d2455"
C_BORDER_GOLD   = "#4a3a0a"
C_TEXT_PARCH    = "#f0e6d3"
C_TEXT_AGED     = "#c4b39a"
C_TEXT_RUNE     = "#8a7a6a"
C_DANGER        = "#dc2626"

# ─── Font Resolution ──────────────────────────────────────────────────────────
def _resolve_serif_family() -> str:
    from PyQt6.QtGui import QFontDatabase
    available = set(QFontDatabase.families())
    for name in ["Cinzel Decorative", "Cinzel", "Palatino Linotype", "Georgia", "Times New Roman"]:
        if name in available:
            return name
    return "Georgia"

def _resolve_body_family() -> str:
    from PyQt6.QtGui import QFontDatabase
    available = set(QFontDatabase.families())
    for name in ["Segoe UI", "Helvetica Neue", "Helvetica", "Arial"]:
        if name in available:
            return name
    return "Arial"

FONT_SERIF: str = "Georgia"
FONT_BODY:  str = "Segoe UI"


def make_accent(btn: QPushButton) -> QPushButton:
    btn.setProperty("accent", "true")
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    return btn


def make_danger(btn: QPushButton) -> QPushButton:
    btn.setProperty("danger", "true")
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    return btn


def _touch_scroll(widget) -> None:
    """Enable kinetic (momentum) touch scrolling on a QScrollArea or QAbstractScrollArea,
    plus a large always-visible scrollbar as a reliable fallback — swipe-to-scroll gesture
    recognition isn't consistent on all touch panels, so a big draggable handle is kept
    on screen rather than hidden."""
    QScroller.grabGesture(
        widget.viewport() if hasattr(widget, "viewport") else widget,
        QScroller.ScrollerGestureType.LeftMouseButtonGesture,
    )
    widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    bar_w = px(34)
    widget.setStyleSheet(widget.styleSheet() + f"""
        QScrollBar:vertical {{
            width: {bar_w}px; background: {C_VOID}; margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {C_ACCENT_PURPLE}; border-radius: {bar_w // 2}px; min-height: {px(60)}px;
        }}
        QScrollBar::handle:vertical:pressed {{
            background: {C_ACCENT_GOLD};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """)
