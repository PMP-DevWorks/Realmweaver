#!/usr/bin/env python3
"""
SceneCaster — Multi-screen storytelling display controller
============================================================

A single-window control panel (lives on your main display) that pushes
static images, animated GIFs, and video to any monitor connected to the
machine. Built for tabletop / D&D storytelling.

KEY CONCEPTS:
  - Each physical monitor gets one borderless fullscreen "Output" window.
  - One screen is the "control" screen — it is NOT blacked out.
  - Scenes hold per-screen background + overlay layer assignments.
  - A separate Music Layer auto-triggers per scene.
  - Each screen card shows a live mini-preview thumbnail.

INSTALL (one time):
    pip install PyQt6

RUN:
    python scene_caster.py
"""

import sys
import os
import json
import math
import time as _time
from dataclasses import dataclass, field, asdict
from typing import Optional

from PyQt6.QtCore import (
    Qt, QUrl, QTimer, QSize, QSizeF, QPointF, QPoint, QEvent, QMimeData,
    pyqtSignal, QPropertyAnimation, QEasingCurve
)
from PyQt6.QtGui import (
    QPixmap, QMovie, QGuiApplication, QFont,
    QImageReader, QDragEnterEvent, QDropEvent, QTransform, QPainter,
    QColor, QPen, QPolygonF, QDrag, QIcon
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QComboBox, QGridLayout,
    QFrame, QSizePolicy, QStackedLayout, QInputDialog, QMessageBox,
    QScrollArea, QSplitter, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QDialog, QDialogButtonBox, QSlider, QCheckBox, QGroupBox, QLineEdit,
    QColorDialog, QDoubleSpinBox, QGraphicsOpacityEffect, QSpinBox, QScroller
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem, QVideoWidget

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
GIF_EXT   = {".gif"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
ALL_EXT   = IMAGE_EXT | GIF_EXT | VIDEO_EXT

THUMB_W: int = 240
THUMB_H: int = 135

APP_DIR   = os.path.dirname(os.path.abspath(__file__))
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


def media_kind(path: str) -> Optional[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT: return "image"
    if ext in GIF_EXT:   return "gif"
    if ext in VIDEO_EXT: return "video"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# GridOverlayWidget — transparent child drawn on top of OutputWindow content
# ─────────────────────────────────────────────────────────────────────────────
class GridOverlayWidget(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self.grid_type   = "square"
        self.cell_size   = 1.0    # inches
        self.color       = "#000000"
        self.screen_w_in = 0.0   # physical screen width in inches
        self.screen_h_in = 0.0   # physical screen height in inches
        self.setVisible(False)

    def paintEvent(self, event):
        if self.screen_w_in <= 0 or self.screen_h_in <= 0 or self.cell_size <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(self.color), 1.0))
        w, h = self.width(), self.height()
        px_per_in_x = w / self.screen_w_in

        if self.grid_type == "square":
            cell_px_x = self.cell_size * px_per_in_x
            cell_px_y = self.cell_size * (h / self.screen_h_in)
            x = 0.0
            while x <= w + 1:
                p.drawLine(QPointF(x, 0), QPointF(x, h))
                x += cell_px_x
            y = 0.0
            while y <= h + 1:
                p.drawLine(QPointF(0, y), QPointF(w, y))
                y += cell_px_y
        else:  # flat-top hex
            r      = self.cell_size * px_per_in_x / math.sqrt(3)
            hex_h  = math.sqrt(3) * r
            col_step = 1.5 * r
            col = -1
            while True:
                cx = col * col_step
                if cx - r > w:
                    break
                row = -1
                while True:
                    offset = hex_h / 2 if col % 2 != 0 else 0.0
                    cy = row * hex_h + offset
                    if cy - r > h:
                        break
                    pts = QPolygonF([
                        QPointF(cx + r * math.cos(math.radians(60 * i)),
                                cy + r * math.sin(math.radians(60 * i)))
                        for i in range(6)
                    ])
                    p.drawPolygon(pts)
                    row += 1
                col += 1
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# PlacedAssetsOverlay — transparent widget that paints placed assets on top of
# everything in the OutputWindow, for image and GIF backgrounds.
# ─────────────────────────────────────────────────────────────────────────────
class PlacedAssetsOverlay(QWidget):
    def __init__(self, output_win):
        super().__init__(output_win)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setVisible(False)

    def paintEvent(self, event):
        output = self.parent()
        assets = output._placed_assets
        cache  = output._asset_pix_cache
        if not assets:
            return

        ww, wh = output.width(), output.height()
        if ww <= 0 or wh <= 0 or output._src_w == 0 or output._src_h == 0:
            return

        # Mirror _set_scaled_pixmap: scale source to (ww*zoom, wh*zoom), then place at offset
        sw_src, sh_src = output._src_w, output._src_h
        tw = int(ww * output._zoom)
        th = int(wh * output._zoom)
        if output.fill_mode:
            ratio = max(tw / sw_src, th / sh_src)
        else:
            ratio = min(tw / sw_src, th / sh_src)
        iw = int(sw_src * ratio)
        ih = int(sh_src * ratio)
        ox = int((ww - iw) / 2 + output._pan_x)
        oy = int((wh - ih) / 2 + output._pan_y)

        p = QPainter(self)
        for pa in assets:
            if isinstance(pa, dict):
                pa = PlacedAsset(**{k: v for k, v in pa.items()
                                    if k in ("asset_path", "x", "y", "w", "h",
                                             "locked", "visible", "sound_path")})
            pix = cache.get(pa.asset_path)
            if pix is None or pix.isNull():
                continue
            pw = max(1, int(pa.w * iw))
            ph = max(1, int(pa.h * ih))
            scaled = pix.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            dx = ox + int(pa.x * iw) - scaled.width()  // 2
            dy = oy + int(pa.y * ih) - scaled.height() // 2
            if not pa.visible:
                p.setOpacity(0.35)
                p.drawPixmap(dx, dy, scaled)
                p.setOpacity(1.0)
                pen_w = max(3, iw // 300)
                p.setPen(QPen(QColor("#ff3333"), pen_w))
                p.drawLine(dx, dy, dx + scaled.width(), dy + scaled.height())
                p.drawLine(dx + scaled.width(), dy, dx, dy + scaled.height())
            else:
                p.drawPixmap(dx, dy, scaled)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# OutputWindow — one per physical screen
# ─────────────────────────────────────────────────────────────────────────────
class OutputWindow(QWidget):
    def __init__(self, screen_index: int, screen):
        super().__init__()
        self.screen_index = screen_index
        self._screen = screen
        self.current_path: Optional[str] = None
        self.current_kind: Optional[str] = None
        self.rotation: int  = 0
        self.fill_mode: bool = False
        self._raw_pixmap: Optional[QPixmap]     = None
        self._overlay_pixmap: Optional[QPixmap] = None
        self._overlay_path: Optional[str]        = None

        self.setWindowTitle(f"SceneCaster Output {screen_index + 1}")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet("background-color: black;")

        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

        # image / gif surface
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.stack.addWidget(self.image_label)

        # video surface
        self.gfx_scene = QGraphicsScene(self)
        self.gfx_view  = QGraphicsView(self.gfx_scene)
        self.gfx_view.setStyleSheet("background:black; border:none;")
        self.gfx_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gfx_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gfx_view.setFrameShape(QFrame.Shape.NoFrame)
        self.gfx_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.video_item = QGraphicsVideoItem()
        self.video_item.setZValue(0)
        self.gfx_scene.addItem(self.video_item)
        self.video_item.nativeSizeChanged.connect(self._fit_video_item)

        self.overlay_gfx_item = QGraphicsPixmapItem()
        self.overlay_gfx_item.setZValue(5)
        self.gfx_scene.addItem(self.overlay_gfx_item)

        self.player = QMediaPlayer()
        self.audio  = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_item)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.stack.addWidget(self.gfx_view)

        self._movie: Optional[QMovie] = None
        self._placed_assets: list = []
        self._asset_pix_cache: dict[str, QPixmap] = {}
        self._pa_gfx_items: list[QGraphicsPixmapItem] = []
        self._src_w: int = 0   # rotated source dimensions for overlay positioning
        self._src_h: int = 0

        # pinch-to-zoom state
        self._zoom: float = 1.0
        self._pan_x: float = 0.0   # pixel offset from center
        self._pan_y: float = 0.0
        self._pinch_start_dist: float = 0.0
        self._pinch_start_zoom: float = 1.0
        self._pinch_start_pan: tuple = (0.0, 0.0)
        self._pinch_start_center: tuple = (0.0, 0.0)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        # Forward touch events from child widgets so pinch-to-zoom is received
        self.image_label.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.gfx_view.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.image_label.installEventFilter(self)
        self.gfx_view.installEventFilter(self)

        self._placed_overlay = PlacedAssetsOverlay(self)

        # grid overlay (floats above content, below fade widget)
        self._grid_overlay = GridOverlayWidget(self)

        # black fade widget for scene transitions
        self._fade_widget = QWidget(self)
        self._fade_widget.setStyleSheet("background: black;")
        self._fade_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._fade_effect = QGraphicsOpacityEffect()
        self._fade_effect.setOpacity(0.0)
        self._fade_widget.setGraphicsEffect(self._fade_effect)
        self._fade_anim = QPropertyAnimation(self._fade_effect, b"opacity")
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.show_blank()

    # ── placement ─────────────────────────────────────────────────────────────

    def place_on_screen(self):
        geo = self._screen.geometry()
        self.setGeometry(geo)
        self.showFullScreen()
        self.windowHandle().setScreen(self._screen)
        self.setGeometry(geo)

    # ── blank ─────────────────────────────────────────────────────────────────

    def show_blank(self):
        self._stop_all()
        self.current_path    = None
        self.current_kind    = None
        self._overlay_pixmap = None
        self._overlay_path   = None
        self.image_label.clear()
        self.overlay_gfx_item.setPixmap(QPixmap())
        self.stack.setCurrentWidget(self.image_label)
        self._placed_overlay.setVisible(False)

    def _stop_all(self):
        if self._movie is not None:
            try:
                self._movie.frameChanged.disconnect(self._on_gif_frame)
            except Exception:
                pass
            self._movie.stop()
            self._movie = None
        self.player.stop()
        self.image_label.clear()
        self.image_label.setMovie(None)
        self._raw_pixmap = None
        for item in self._pa_gfx_items:
            self.gfx_scene.removeItem(item)
        self._pa_gfx_items.clear()
        self._asset_pix_cache.clear()

    # ── overlay ───────────────────────────────────────────────────────────────

    def display_overlay(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if not os.path.exists(path) or ext not in (IMAGE_EXT | GIF_EXT):
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        self._overlay_pixmap = QPixmap.fromImage(reader.read())
        self._overlay_path   = path
        self._redraw_composite()

    def clear_overlay(self):
        self._overlay_pixmap = None
        self._overlay_path   = None
        self.overlay_gfx_item.setPixmap(QPixmap())
        self._redraw_composite()

    def _redraw_composite(self):
        if self.current_kind == "image" and self._raw_pixmap:
            self._set_scaled_pixmap(self._apply_rotation(self._raw_pixmap))
        elif self.current_kind == "gif" and self._movie:
            self._on_gif_frame(self._movie.currentFrameNumber())
        elif self.current_kind == "video":
            self._update_video_overlay()

    def _composite(self, base: QPixmap, include_placed: bool = True) -> QPixmap:
        has_ov = self._overlay_pixmap is not None and not self._overlay_pixmap.isNull()
        has_pa = include_placed and bool(self._placed_assets)
        if not has_ov and not has_pa:
            return base
        result = QPixmap(base.size())
        result.fill(Qt.GlobalColor.transparent)
        p = QPainter(result)
        p.drawPixmap(0, 0, base)
        if has_ov:
            ov = self._overlay_pixmap.scaled(
                base.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((base.width() - ov.width()) // 2,
                         (base.height() - ov.height()) // 2, ov)
        if has_pa:
            self._paint_placed_assets(p, base.width(), base.height())
        p.end()
        return result

    def _paint_placed_assets(self, painter: QPainter, bw: int, bh: int):
        for pa in self._placed_assets:
            if isinstance(pa, dict):
                pa = PlacedAsset(**{k: v for k, v in pa.items()
                                    if k in ("asset_path", "x", "y", "w", "h",
                                             "locked", "visible", "sound_path")})
            if not os.path.exists(pa.asset_path):
                continue
            ext = os.path.splitext(pa.asset_path)[1].lower()
            if ext not in (IMAGE_EXT | GIF_EXT):
                continue
            reader = QImageReader(pa.asset_path)
            reader.setAutoTransform(True)
            pix = QPixmap.fromImage(reader.read())
            if pix.isNull():
                continue
            pw = max(1, int(pa.w * bw))
            ph = max(1, int(pa.h * bh))
            scaled = pix.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            dx = int(pa.x * bw) - scaled.width()  // 2
            dy = int(pa.y * bh) - scaled.height() // 2
            if not pa.visible:
                painter.setOpacity(0.35)
                painter.drawPixmap(dx, dy, scaled)
                painter.setOpacity(1.0)
                pen_w = max(3, bw // 300)
                painter.setPen(QPen(QColor("#ff3333"), pen_w))
                painter.drawLine(dx, dy, dx + scaled.width(), dy + scaled.height())
                painter.drawLine(dx + scaled.width(), dy, dx, dy + scaled.height())
            else:
                painter.drawPixmap(dx, dy, scaled)

    def set_placed_assets(self, assets: list):
        def _path(pa):
            return pa.asset_path if hasattr(pa, "asset_path") else pa.get("asset_path", "")

        new_paths = {_path(pa) for pa in assets}
        old_paths = {_path(pa) for pa in self._placed_assets}
        paths_changed = new_paths != old_paths

        self._placed_assets = list(assets)

        if paths_changed:
            # Asset list changed — rebuild pixmap cache and redraw background
            self._asset_pix_cache.clear()
            for pa in self._placed_assets:
                path = _path(pa)
                if path and os.path.exists(path):
                    reader = QImageReader(path)
                    reader.setAutoTransform(True)
                    pix = QPixmap.fromImage(reader.read())
                    if not pix.isNull():
                        self._asset_pix_cache[path] = pix
            self._redraw_composite()

        # Video props are drawn as QGraphicsPixmapItems positioned from pa.x/y/w/h/visible,
        # so this must run on every update (move/resize/visibility), not just when the
        # set of asset paths changes, or edits to an already-placed prop never show.
        self._update_video_placed_assets()

        if self.current_kind in ("image", "gif"):
            self._placed_overlay.resize(self.size())
            self._placed_overlay.setVisible(bool(self._placed_assets))
            self._placed_overlay.raise_()
            self._grid_overlay.raise_()
            self._fade_widget.raise_()
            self._placed_overlay.update()
        elif paths_changed:
            self._placed_overlay.setVisible(False)

    def _update_video_overlay(self):
        if self._overlay_pixmap is None or self._overlay_pixmap.isNull():
            self.overlay_gfx_item.setPixmap(QPixmap())
            return
        native = self.video_item.nativeSize()
        if not native.isValid() or native.width() == 0:
            return
        w, h = int(native.width()), int(native.height())
        ov = self._overlay_pixmap.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.overlay_gfx_item.setPixmap(ov)
        self.overlay_gfx_item.setPos((w - ov.width()) / 2, (h - ov.height()) / 2)

    def _update_video_placed_assets(self):
        for item in self._pa_gfx_items:
            self.gfx_scene.removeItem(item)
        self._pa_gfx_items.clear()
        if self.current_kind != "video":
            return
        native = self.video_item.nativeSize()
        if not native.isValid() or native.width() == 0:
            return
        nw, nh = native.width(), native.height()
        for pa in self._placed_assets:
            if isinstance(pa, dict):
                pa = PlacedAsset(**{k: v for k, v in pa.items()
                                    if k in ("asset_path", "x", "y", "w", "h",
                                             "locked", "visible", "sound_path")})
            pix = self._asset_pix_cache.get(pa.asset_path)
            if pix is None or pix.isNull():
                continue
            pw = max(1, int(pa.w * nw))
            ph = max(1, int(pa.h * nh))
            scaled = pix.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            gfx_item = QGraphicsPixmapItem(scaled)
            gfx_item.setZValue(10)
            gfx_item.setPos(pa.x * nw - scaled.width() / 2,
                            pa.y * nh - scaled.height() / 2)
            if not pa.visible:
                gfx_item.setOpacity(0.35)
            self.gfx_scene.addItem(gfx_item)
            self._pa_gfx_items.append(gfx_item)

    # ── grid ──────────────────────────────────────────────────────────────────

    def apply_grid(self, settings: dict):
        if not settings or not settings.get("enabled", False):
            self.clear_grid()
            return
        g = self._grid_overlay
        g.grid_type    = settings.get("grid_type", "square")
        g.cell_size    = settings.get("cell_size", 1.0)
        g.color        = settings.get("color", "#000000")
        g.screen_w_in  = settings.get("screen_w_in", 0.0)
        g.screen_h_in  = settings.get("screen_h_in", 0.0)
        g.resize(self.size())
        g.setVisible(True)
        g.raise_()
        self._fade_widget.raise_()  # keep fade widget on top of grid
        g.update()

    def clear_grid(self):
        self._grid_overlay.setVisible(False)

    # ── transitions ───────────────────────────────────────────────────────────

    def fade_to_black(self, duration_ms: int, callback):
        self._fade_widget.resize(self.size())
        self._fade_widget.raise_()
        self._fade_anim.stop()
        try:
            self._fade_anim.finished.disconnect()
        except Exception:
            pass
        self._fade_anim.setDuration(duration_ms)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    def fade_from_black(self, duration_ms: int):
        self._fade_anim.stop()
        try:
            self._fade_anim.finished.disconnect()
        except Exception:
            pass
        self._fade_anim.setDuration(duration_ms)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    # ── rotation / fill ───────────────────────────────────────────────────────

    def _apply_rotation(self, pix: QPixmap) -> QPixmap:
        if self.rotation == 0:
            return pix
        return pix.transformed(
            QTransform().rotate(self.rotation),
            Qt.TransformationMode.SmoothTransformation)

    def _aspect_mode(self):
        return (Qt.AspectRatioMode.KeepAspectRatioByExpanding if self.fill_mode
                else Qt.AspectRatioMode.KeepAspectRatio)

    def set_rotation(self, degrees: int):
        self.rotation = degrees
        if self.current_kind == "image" and self._raw_pixmap:
            self._set_scaled_pixmap(self._apply_rotation(self._raw_pixmap))
        elif self.current_kind == "gif" and self.current_path:
            self.display(self.current_path)
        elif self.current_kind == "video":
            self._fit_video_item()

    def set_fill_mode(self, fill: bool):
        self.fill_mode = fill
        if self.current_kind == "image" and self._raw_pixmap:
            self._set_scaled_pixmap(self._apply_rotation(self._raw_pixmap))
        elif self.current_kind == "gif" and self._movie:
            self._on_gif_frame(self._movie.currentFrameNumber())
        elif self.current_kind == "video":
            self._fit_video_item()

    # ── display ───────────────────────────────────────────────────────────────

    def display(self, path: str, mute: bool = False):
        kind = media_kind(path)
        if kind is None or not os.path.exists(path):
            self.show_blank()
            return
        saved_ov_pix  = self._overlay_pixmap
        saved_ov_path = self._overlay_path
        self._stop_all()
        self.current_path    = path
        self.current_kind    = kind
        self._overlay_pixmap = saved_ov_pix
        self._overlay_path   = saved_ov_path

        if kind == "image":
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            self._raw_pixmap = QPixmap.fromImage(reader.read())
            self._set_scaled_pixmap(self._apply_rotation(self._raw_pixmap))
            self.stack.setCurrentWidget(self.image_label)

        elif kind == "gif":
            self._movie = QMovie(path)
            self._movie.setCacheMode(QMovie.CacheMode.CacheAll)
            self._movie.frameChanged.connect(self._on_gif_frame)
            self._movie.start()
            self.stack.setCurrentWidget(self.image_label)

        elif kind == "video":
            self.audio.setMuted(mute)
            self.player.setSource(QUrl.fromLocalFile(path))
            self.stack.setCurrentWidget(self.gfx_view)
            self.player.play()
            if self._overlay_pixmap:
                QTimer.singleShot(400, self._update_video_overlay)

    def _set_scaled_pixmap(self, pix: QPixmap):
        if pix.isNull():
            return
        ww, wh = self.width(), self.height()
        if ww <= 0 or wh <= 0:
            return
        self._src_w, self._src_h = pix.width(), pix.height()
        # Scale to window at zoom level, then crop/offset to window size
        zoom_size = QSize(int(ww * self._zoom), int(wh * self._zoom))
        scaled = pix.scaled(zoom_size, self._aspect_mode(),
                             Qt.TransformationMode.SmoothTransformation)
        frame = QPixmap(ww, wh)
        frame.fill(Qt.GlobalColor.black)
        p = QPainter(frame)
        ox = int((ww - scaled.width())  / 2 + self._pan_x)
        oy = int((wh - scaled.height()) / 2 + self._pan_y)
        p.drawPixmap(ox, oy, scaled)
        p.end()
        self.image_label.setPixmap(self._composite(frame, include_placed=False))

    def _on_gif_frame(self, _: int):
        if self._movie is None:
            return
        pix = self._movie.currentPixmap()
        if self.rotation != 0:
            pix = self._apply_rotation(pix)
        self._set_scaled_pixmap(pix)
        if self._placed_overlay.isVisible():
            self._placed_overlay.update()

    def _fit_video_item(self, _size: QSizeF = None):
        native = self.video_item.nativeSize()
        if not native.isValid() or native.width() == 0:
            return
        self.video_item.setSize(native)
        self.video_item.setTransformOriginPoint(native.width() / 2, native.height() / 2)
        self.video_item.setRotation(self.rotation)
        self.gfx_view.resetTransform()
        self.gfx_view.fitInView(
            self.gfx_scene.itemsBoundingRect(), self._aspect_mode())
        if self._zoom != 1.0:
            self.gfx_view.scale(self._zoom, self._zoom)
            self.gfx_view.centerOn(
                native.width()  / 2 - self._pan_x / self._zoom,
                native.height() / 2 - self._pan_y / self._zoom)
        if self._overlay_pixmap:
            self._update_video_overlay()
        self._update_video_placed_assets()

    # ── pinch-to-zoom ────────────────────────────────────────────────────────

    def _apply_zoom(self):
        if self.current_kind == "image" and self._raw_pixmap:
            self._set_scaled_pixmap(self._apply_rotation(self._raw_pixmap))
        elif self.current_kind == "gif" and self._movie:
            self._set_scaled_pixmap(self._movie.currentPixmap()
                                    if self.rotation == 0
                                    else self._apply_rotation(self._movie.currentPixmap()))
        elif self.current_kind == "video":
            self._fit_video_item()
        if self._placed_overlay.isVisible():
            self._placed_overlay.update()

    def reset_zoom(self):
        self._zoom  = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._apply_zoom()

    def eventFilter(self, obj, e):
        """Forward touch events from child widgets so pinch-to-zoom reaches our handler."""
        if e.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            return self.event(e)
        return super().eventFilter(obj, e)

    def event(self, e):
        t = e.type()
        if t in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            pts = e.points()
            if len(pts) == 2:
                p1 = pts[0].position()
                p2 = pts[1].position()
                dist = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
                cx   = (p1.x() + p2.x()) / 2
                cy   = (p1.y() + p2.y()) / 2
                if t == QEvent.Type.TouchBegin or self._pinch_start_dist == 0:
                    self._pinch_start_dist   = dist
                    self._pinch_start_zoom   = self._zoom
                    self._pinch_start_pan    = (self._pan_x, self._pan_y)
                    self._pinch_start_center = (cx, cy)
                elif t == QEvent.Type.TouchUpdate and self._pinch_start_dist > 0:
                    ratio    = dist / self._pinch_start_dist
                    new_zoom = max(1.0, min(8.0, self._pinch_start_zoom * ratio))
                    # Pan so the pinch center stays fixed on screen
                    dcx = cx - self._pinch_start_center[0]
                    dcy = cy - self._pinch_start_center[1]
                    self._zoom  = new_zoom
                    self._pan_x = self._pinch_start_pan[0] * ratio + dcx
                    self._pan_y = self._pinch_start_pan[1] * ratio + dcy
                    self._clamp_pan()
                    self._apply_zoom()
            elif t == QEvent.Type.TouchEnd:
                self._pinch_start_dist = 0
                if self._zoom < 1.05:
                    self.reset_zoom()
            return True
        return super().event(e)

    def _clamp_pan(self):
        """Keep pan within the zoomed image bounds so you can't pan to empty black."""
        if self._zoom <= 1.0:
            self._pan_x = 0.0
            self._pan_y = 0.0
            return
        max_pan_x = self.width()  * (self._zoom - 1) / 2
        max_pan_y = self.height() * (self._zoom - 1) / 2
        self._pan_x = max(-max_pan_x, min(max_pan_x, self._pan_x))
        self._pan_y = max(-max_pan_y, min(max_pan_y, self._pan_y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grid_overlay.resize(self.size())
        self._fade_widget.resize(self.size())
        self._placed_overlay.resize(self.size())
        if self.current_kind == "image" and self._raw_pixmap:
            self._set_scaled_pixmap(self._apply_rotation(self._raw_pixmap))
        elif self.current_kind == "gif" and self._movie:
            self._on_gif_frame(self._movie.currentFrameNumber())
        elif self.current_kind == "video":
            self._fit_video_item()
        if self.current_kind in ("image", "gif"):
            self._placed_overlay.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            pass

    # ── exact rendered frame / thumbnail for minimap and control panel ───────

    def get_scene_frame(self, include_placed: bool = True, target_size=None) -> Optional[QPixmap]:
        """Return a frame that matches the actual output viewport.

        This is intentionally based on the OutputWindow's current size, rotation,
        fill mode, overlay, and prop compositing instead of the source-media size.
        The minimap uses include_placed=False so props can stay interactive widgets
        on top of an accurate cloned scene background.
        """
        size = target_size or self.size()
        if size.width() <= 0 or size.height() <= 0:
            return None

        if self.current_kind == "image" and self._raw_pixmap:
            pix = self._apply_rotation(self._raw_pixmap)
            scaled = pix.scaled(size, self._aspect_mode(),
                                Qt.TransformationMode.SmoothTransformation)
            frame = QPixmap(size)
            frame.fill(Qt.GlobalColor.black)
            p = QPainter(frame)
            x = (size.width() - scaled.width()) // 2
            y = (size.height() - scaled.height()) // 2
            p.drawPixmap(x, y, self._composite(scaled, include_placed))
            p.end()
            return frame

        if self.current_kind == "gif" and self._movie:
            pix = self._movie.currentPixmap()
            if pix.isNull():
                return None
            if self.rotation != 0:
                pix = self._apply_rotation(pix)
            scaled = pix.scaled(size, self._aspect_mode(),
                                Qt.TransformationMode.SmoothTransformation)
            frame = QPixmap(size)
            frame.fill(Qt.GlobalColor.black)
            p = QPainter(frame)
            x = (size.width() - scaled.width()) // 2
            y = (size.height() - scaled.height()) // 2
            p.drawPixmap(x, y, self._composite(scaled, include_placed))
            p.end()
            return frame

        if self.current_kind == "video":
            # Video frames are owned by the graphics view, so render the view.
            # Hide placed-asset GFX items when include_placed=False to avoid
            # double-rendering them alongside the PlacedAssetItem minimap widgets.
            if not include_placed:
                for item in self._pa_gfx_items:
                    item.setVisible(False)
            frame = QPixmap(size)
            frame.fill(Qt.GlobalColor.black)
            p = QPainter(frame)
            self.gfx_view.render(p)
            p.end()
            if not include_placed:
                for item in self._pa_gfx_items:
                    item.setVisible(True)
            return frame

        return None

    def get_thumbnail(self) -> Optional[QPixmap]:
        frame = self.get_scene_frame(include_placed=True, target_size=self.size())
        if frame and not frame.isNull():
            return frame.scaled(
                THUMB_W, THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Scene data model
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Scene:
    name: str
    assignments: dict   = field(default_factory=dict)
    music_path: Optional[str] = None
    rotations: dict     = field(default_factory=dict)
    fill_modes: dict    = field(default_factory=dict)
    grid_settings: dict = field(default_factory=dict)
    placed_assets: dict = field(default_factory=dict)  # str(idx) -> list of PlacedAsset dicts


# ─────────────────────────────────────────────────────────────────────────────
# Asset prop data models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class AssetItem:
    path: str
    size_w: float = 0.15       # fraction of screen width (0.0–1.0)
    size_h: float = 0.15       # fraction of screen height (0.0–1.0)
    sound_path: Optional[str] = None
    effect: Optional[str] = None


@dataclass
class PlacedAsset:
    asset_path: str
    x: float = 0.5            # center x, 0.0–1.0 relative to screen
    y: float = 0.5            # center y, 0.0–1.0 relative to screen
    w: float = 0.15           # width, 0.0–1.0 relative to screen
    h: float = 0.15           # height, 0.0–1.0 relative to screen
    locked: bool = False
    visible: bool = True      # False = greyed + red-X overlay
    sound_path: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# MediaTile — list item in the media library
# ─────────────────────────────────────────────────────────────────────────────
class MediaTile(QListWidgetItem):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.kind = media_kind(path)
        tag = {"image": "IMG", "gif": "GIF", "video": "VID"}.get(self.kind, "?")
        self.setText(f"[{tag}] {os.path.basename(path)}")
        self.setToolTip(path)
        self.setIcon(self._build_thumb(tag))

    def _build_thumb(self, tag: str) -> QIcon:
        ts = px(40)
        if self.kind in ("image", "gif") and os.path.exists(self.path):
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            pix = QPixmap.fromImage(reader.read())
            if not pix.isNull():
                return QIcon(pix.scaled(ts, ts, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        # No cheap static frame for video/audio (or a bad read) — draw a
        # placeholder swatch so every row still shows something to the side.
        pix = QPixmap(ts, ts)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(C_CARD))
        p.setPen(QPen(QColor(C_BORDER_GOLD), 1))
        p.drawRoundedRect(0, 0, ts - 1, ts - 1, 6, 6)
        p.setPen(QColor(C_TEXT_RUNE))
        f = QFont(FONT_BODY)
        f.setPointSize(pt(8))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, tag)
        p.end()
        return QIcon(pix)


# ─────────────────────────────────────────────────────────────────────────────
# AssetConfigDialog — configure size, sound, and effect for a library asset
# ─────────────────────────────────────────────────────────────────────────────
class AssetConfigDialog(QDialog):
    def __init__(self, asset: AssetItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Asset")
        self.setMinimumWidth(px(460))
        self.setMinimumHeight(px(340))
        self.asset = asset

        lay = QVBoxLayout(self)
        lay.setSpacing(px(16))
        lay.setContentsMargins(px(24), px(24), px(24), px(24))

        name_lbl = QLabel(os.path.basename(asset.path))
        name_lbl.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(13)}pt; font-weight:700; color:{C_ACCENT_GOLD};')
        lay.addWidget(name_lbl)

        def _add_slider(label: str, value: float, setter) -> QSlider:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setMinimumWidth(px(140))
            lbl.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(11)}pt;")
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(5, 100)
            sl.setValue(int(value * 100))
            sl.setMinimumHeight(px(56))
            val_lbl = QLabel(f"{int(value * 100)}%")
            val_lbl.setMinimumWidth(px(44))
            val_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(11)}pt;")
            sl.valueChanged.connect(lambda v, vl=val_lbl: vl.setText(f"{v}%"))
            sl.valueChanged.connect(setter)
            row.addWidget(lbl)
            row.addWidget(sl, 1)
            row.addWidget(val_lbl)
            lay.addLayout(row)
            return sl

        _add_slider("Width (% of screen):", asset.size_w,
                    lambda v: setattr(self.asset, "size_w", v / 100))
        _add_slider("Height (% of screen):", asset.size_h,
                    lambda v: setattr(self.asset, "size_h", v / 100))

        # Sound file row
        snd_row = QHBoxLayout()
        snd_lbl = QLabel("Sound:")
        snd_lbl.setMinimumWidth(px(140))
        snd_lbl.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(11)}pt;")
        self._snd_edit = QLineEdit(os.path.basename(asset.sound_path or ""))
        self._snd_edit.setReadOnly(True)
        self._snd_edit.setMinimumHeight(px(56))
        self._snd_edit.setToolTip(asset.sound_path or "")
        snd_browse = QPushButton("Browse…")
        snd_browse.setMinimumHeight(px(56))
        snd_browse.setMinimumWidth(px(80))
        snd_browse.clicked.connect(self._browse_sound)
        snd_clear = QPushButton("✕")
        snd_clear.setMinimumSize(px(44), px(40))
        snd_clear.clicked.connect(self._clear_sound)
        snd_row.addWidget(snd_lbl)
        snd_row.addWidget(self._snd_edit, 1)
        snd_row.addSpacing(px(6))
        snd_row.addWidget(snd_browse)
        snd_row.addWidget(snd_clear)
        lay.addLayout(snd_row)

        # Effect row (stubbed for future visual effects)
        eff_row = QHBoxLayout()
        eff_lbl = QLabel("Effect:")
        eff_lbl.setMinimumWidth(px(140))
        eff_lbl.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(11)}pt;")
        self._eff_combo = QComboBox()
        self._eff_combo.addItems(["None", "Pulse", "Shake"])
        self._eff_combo.setMinimumHeight(px(56))
        effects = ["none", "pulse", "shake"]
        cur = (asset.effect or "none").lower()
        if cur in effects:
            self._eff_combo.setCurrentIndex(effects.index(cur))
        self._eff_combo.currentIndexChanged.connect(
            lambda i: setattr(self.asset, "effect", ["none", "pulse", "shake"][i]))
        eff_row.addWidget(eff_lbl)
        eff_row.addWidget(self._eff_combo, 1)
        lay.addLayout(eff_row)

        lay.addStretch(1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _slider_style(self):
        return ""

    def _btn_style(self):
        return ""

    def _browse_sound(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Sound file", MUSIC_DIR, f"Audio ({exts})", options=_DIALOG_OPTS)
        if path:
            self.asset.sound_path = path
            self._snd_edit.setText(os.path.basename(path))
            self._snd_edit.setToolTip(path)

    def _clear_sound(self):
        self.asset.sound_path = None
        self._snd_edit.setText("")
        self._snd_edit.setToolTip("")


# ─────────────────────────────────────────────────────────────────────────────
# AssetTile — one entry in the asset library panel (drag source)
# ─────────────────────────────────────────────────────────────────────────────
class AssetTile(QWidget):
    DRAG_THRESHOLD = 28     # touch fingers jitter far more than a mouse cursor while held still
    LONG_PRESS_MS  = 600

    def __init__(self, asset: AssetItem, library_panel, parent=None):
        super().__init__(parent)
        self.asset    = asset
        self._library = library_panel
        self._press_pos: Optional[QPoint] = None
        self._dragging = False
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press)
        self.setFixedHeight(px(190))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._build_ui()
        self._set_normal_style()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(px(10), px(8), px(10), px(8))
        outer.setSpacing(px(8))

        top = QHBoxLayout()
        top.setSpacing(px(12))

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(px(80), px(80))
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setStyleSheet(f"background:{C_VOID}; border-radius:{px(6)}px;")
        self._load_thumb()
        top.addWidget(self.thumb_lbl)

        info = QVBoxLayout()
        info.setSpacing(px(3))
        name_lbl = QLabel(os.path.basename(self.asset.path))
        name_lbl.setStyleSheet(f"color:{C_TEXT_PARCH}; font-size:{pt(11)}pt; font-weight:600;")
        name_lbl.setWordWrap(True)
        info.addWidget(name_lbl)
        if self.asset.sound_path:
            self.snd_lbl = QLabel(f"♪ {os.path.basename(self.asset.sound_path)}")
            self.snd_lbl.setStyleSheet(f"color:{C_GLOW_PURPLE}; font-size:{pt(9)}pt;")
            info.addWidget(self.snd_lbl)
        hint_lbl = QLabel("Hold to set sound • Drag to place")
        hint_lbl.setStyleSheet(f"color:{C_BORDER}; font-size:{pt(9)}pt;")
        info.addWidget(hint_lbl)
        info.addStretch(1)
        top.addLayout(info, 1)

        # Big, obviously-tappable clone/delete buttons — sized for a finger, not a cursor.
        clone_btn = QPushButton("⧉ Clone")
        clone_btn.setFixedSize(px(96), px(56))
        clone_btn.setStyleSheet(
            f"QPushButton {{ background:{C_HOVER}; color:{C_TEXT_PARCH}; "
            f"border:1px solid {C_ACCENT_PURPLE}; border-radius:{px(8)}px; font-size:{pt(11)}pt; }}"
            f"QPushButton:pressed {{ background:{C_ACCENT_PURPLE}; }}")
        clone_btn.clicked.connect(self._on_clone)
        top.addWidget(clone_btn)

        del_btn = QPushButton("✕ Delete")
        del_btn.setFixedSize(px(96), px(56))
        del_btn.setStyleSheet(
            f"QPushButton {{ background:{C_HOVER}; color:{C_DANGER}; "
            f"border:1px solid {C_DANGER}; border-radius:{px(8)}px; font-size:{pt(11)}pt; }}"
            f"QPushButton:pressed {{ background:{C_DANGER}; color:white; }}")
        del_btn.clicked.connect(self._on_delete)
        top.addWidget(del_btn)

        outer.addLayout(top)

        # Horizontal size slider spanning the tile width — drag it to scale the asset.
        # Saves the moment you lift your finger, not on every intermediate value.
        size_row = QHBoxLayout()
        size_row.setSpacing(px(10))
        size_lbl = QLabel("Size:")
        size_lbl.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(11)}pt;")
        size_row.addWidget(size_lbl)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(3, 100)
        self.size_slider.setValue(int(round(self.asset.size_w * 100)))
        self.size_slider.setMinimumHeight(px(48))
        self.size_slider.setPageStep(2)
        self.size_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: {px(10)}px; border-radius: {px(5)}px; background: {C_INPUT};
            }}
            QSlider::handle:horizontal {{
                width: {px(44)}px; height: {px(44)}px; margin: -{px(17)}px 0;
                border-radius: {px(22)}px; background: {C_ACCENT_GOLD};
                border: {px(2)}px solid {C_VOID};
            }}
            QSlider::sub-page:horizontal {{
                background: {C_ACCENT_PURPLE}; border-radius: {px(5)}px;
            }}
        """)
        self.size_slider.valueChanged.connect(self._on_size_slider_changed)
        self.size_slider.sliderReleased.connect(self._on_size_slider_released)
        size_row.addWidget(self.size_slider, 1)
        self.size_pct_lbl = QLabel(self._size_label_text())
        self.size_pct_lbl.setMinimumWidth(px(120))
        self.size_pct_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(11)}pt;")
        size_row.addWidget(self.size_pct_lbl)
        outer.addLayout(size_row)

    def _size_label_text(self) -> str:
        ref = self._library.reference_screen_size()
        px_w = round(self.asset.size_w * ref.width())
        px_h = round(self.asset.size_h * ref.height())
        pct  = int(round(self.asset.size_w * 100))
        return f"{pct}% ≈ {px_w}×{px_h}px"

    def _on_size_slider_changed(self, value: int):
        ratio = value / 100
        self.asset.size_w = ratio
        self.asset.size_h = ratio
        self.size_pct_lbl.setText(self._size_label_text())

    def _on_size_slider_released(self):
        self._library.on_asset_changed()

    def _on_clone(self):
        self._library.clone_asset(self.asset)

    def _on_delete(self):
        self._library.delete_asset(self.asset)

    def refresh_labels(self):
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(int(round(self.asset.size_w * 100)))
        self.size_slider.blockSignals(False)
        self.size_pct_lbl.setText(self._size_label_text())

    def _load_thumb(self):
        path = self.asset.path
        ext  = os.path.splitext(path)[1].lower()
        if os.path.exists(path) and ext in (IMAGE_EXT | GIF_EXT):
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            pix = QPixmap.fromImage(reader.read())
            if not pix.isNull():
                ts = px(80)
                self.thumb_lbl.setPixmap(
                    pix.scaled(ts, ts, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))

    def _set_normal_style(self):
        self.setStyleSheet(
            f"AssetTile {{ background:{C_CARD}; border-radius:{px(8)}px; "
            f"border-top:1px solid {C_BORDER_GOLD}; }}")

    def _set_pressed_style(self):
        self.setStyleSheet(
            f"AssetTile {{ background:{C_HOVER}; border-radius:{px(8)}px; "
            f"border:1px solid {C_ACCENT_PURPLE}; }}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
            self._dragging  = False
            self._set_pressed_style()
            self._long_press_timer.start(self.LONG_PRESS_MS)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and not self._dragging:
            if (event.pos() - self._press_pos).manhattanLength() > self.DRAG_THRESHOLD:
                self._dragging = True
                self._long_press_timer.stop()
                self._set_normal_style()
                self._start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._long_press_timer.stop()
        self._set_normal_style()
        self._press_pos = None
        self._dragging  = False
        super().mouseReleaseEvent(event)

    def _on_long_press(self):
        self._set_normal_style()
        dlg = AssetConfigDialog(self.asset, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_labels()
            self._library.on_asset_changed()

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-asset-path",  self.asset.path.encode())
        mime.setData("application/x-asset-w",     str(self.asset.size_w).encode())
        mime.setData("application/x-asset-h",     str(self.asset.size_h).encode())
        if self.asset.sound_path:
            mime.setData("application/x-asset-sound",
                         (self.asset.sound_path or "").encode())
        drag.setMimeData(mime)
        pm = self.thumb_lbl.pixmap()
        if pm and not pm.isNull():
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)


# ─────────────────────────────────────────────────────────────────────────────
# AssetLibraryPanel — scrollable list of asset tiles with Add button
# ─────────────────────────────────────────────────────────────────────────────
class AssetLibraryPanel(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._tiles: list[AssetTile] = []
        self.setMinimumWidth(px(300))
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(8), px(10), px(8), px(10))
        lay.setSpacing(px(8))

        hdr = QLabel("Asset Library")
        hdr.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(13)}pt; font-weight:700; color:{C_ACCENT_GOLD};')
        lay.addWidget(hdr)

        sub = QLabel("Slide to resize • Hold to set sound • Drag to place")
        sub.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        lay.addWidget(sub)

        add_btn = QPushButton("+ Add Assets")
        add_btn.setMinimumHeight(px(72))
        ControlWindow._make_accent(add_btn)
        add_btn.clicked.connect(self._add_assets)
        lay.addWidget(add_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        _touch_scroll(scroll)

        self._tile_container = QWidget()
        self._tile_container.setStyleSheet(f"background:{C_VOID};")
        self._tile_layout = QVBoxLayout(self._tile_container)
        self._tile_layout.setContentsMargins(0, 0, 0, 0)
        self._tile_layout.setSpacing(px(6))
        self._tile_layout.addStretch(1)

        scroll.setWidget(self._tile_container)
        lay.addWidget(scroll, 1)
        self._refresh_tiles()

    def _add_assets(self):
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXT | GIF_EXT))
        files = _pick_media_files(
            self, "Add assets", ASSETS_DIR, f"Images & GIFs ({exts})", multi=True)
        for path in files:
            if not any(a.path == path for a in self.controller.asset_library):
                self.controller.asset_library.append(AssetItem(path=path))
        if files:
            self.controller._save_scenes()
            self._refresh_tiles()

    def clone_asset(self, asset: "AssetItem"):
        clone = AssetItem(path=asset.path, size_w=asset.size_w, size_h=asset.size_h,
                           sound_path=asset.sound_path, effect=asset.effect)
        lib = self.controller.asset_library
        idx = next((i for i, a in enumerate(lib) if a is asset), len(lib) - 1)
        lib.insert(idx + 1, clone)
        self.controller._save_scenes()
        self._refresh_tiles()

    def delete_asset(self, asset: "AssetItem"):
        reply = QMessageBox.question(
            self, "Delete Asset",
            f"Remove \"{os.path.basename(asset.path)}\" from the library?\n"
            "Props already placed on scenes are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        lib = self.controller.asset_library
        self.controller.asset_library = [a for a in lib if a is not asset]
        self.controller._save_scenes()
        self._refresh_tiles()

    def _refresh_tiles(self):
        for tile in self._tiles:
            tile.deleteLater()
        self._tiles.clear()
        while self._tile_layout.count():
            item = self._tile_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for asset in self.controller.asset_library:
            tile = AssetTile(asset, self)
            self._tiles.append(tile)
            self._tile_layout.addWidget(tile)
        self._tile_layout.addStretch(1)

    def on_asset_changed(self):
        self.controller._save_scenes()

    def reference_screen_size(self) -> QSize:
        """Best-guess screen to convert an asset's size ratio into pixels for display.
        Picks the first non-main output (i.e. an actual cast screen, not the control
        panel's own monitor); falls back to the primary screen if none are set up yet."""
        outputs = self.controller.outputs
        for idx, out in enumerate(outputs):
            if idx != self.controller._main_screen_idx:
                size = out.size()
                if size.width() > 0 and size.height() > 0:
                    return size
                return out._screen.geometry().size()
        screen = QGuiApplication.primaryScreen()
        return screen.geometry().size() if screen else QSize(1920, 1080)


# ─────────────────────────────────────────────────────────────────────────────
# PlacedAssetItem — interactive widget for a prop placed on the MiniMapCanvas
# ─────────────────────────────────────────────────────────────────────────────
class PlacedAssetItem(QWidget):
    TAP_WINDOW_MS  = 400    # max gap between two taps for a double-tap
    HOLD_DELETE_MS = 800    # hold duration on 2nd tap to trigger delete
    LOCK_HOLD_MS   = 5000   # two-finger hold duration to toggle lock
    DRAG_THRESHOLD = 28     # touch fingers jitter far more than a mouse cursor while held still

    deleted = pyqtSignal(object)
    moved   = pyqtSignal(object)

    def __init__(self, placed: PlacedAsset, canvas, parent=None):
        super().__init__(parent)
        self.placed  = placed
        self._canvas = canvas
        self._press_pos: Optional[QPoint]  = None
        self._is_dragging     = False
        self._tap_count       = 0
        self._last_tap_ms     = 0.0
        self._tap_timer       = QTimer(self)
        self._tap_timer.setSingleShot(True)
        self._tap_timer.timeout.connect(self._on_single_tap)
        self._hold_timer      = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_delete)
        self._lock_timer      = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._on_toggle_lock)
        self._touch_count     = 0
        self._delete_mode     = False
        self._sound_player: Optional[QMediaPlayer] = None
        self._pixmap: Optional[QPixmap] = None
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self._load_pixmap()

    def _load_pixmap(self):
        path = self.placed.asset_path
        ext  = os.path.splitext(path)[1].lower()
        if os.path.exists(path) and ext in (IMAGE_EXT | GIF_EXT):
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                self._pixmap = QPixmap.fromImage(img)

    def paintEvent(self, event):
        if not self._pixmap or self._pixmap.isNull():
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(C_INPUT))
            p.end()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scaled = self._pixmap.scaled(self.size(),
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
        ox = (self.width()  - scaled.width())  // 2
        oy = (self.height() - scaled.height()) // 2

        if not self.placed.visible:
            p.setOpacity(0.35)
            p.drawPixmap(ox, oy, scaled)
            p.setOpacity(1.0)
            pen_w = max(3, self.width() // 20)
            p.setPen(QPen(QColor("#ff3333"), pen_w))
            m = pen_w
            p.drawLine(m, m, self.width() - m, self.height() - m)
            p.drawLine(self.width() - m, m, m, self.height() - m)
        else:
            p.drawPixmap(ox, oy, scaled)

        if self.placed.locked:
            p.setPen(QPen(QColor(C_ACCENT_GOLD), 2))
            p.setFont(QFont("Segoe UI", max(10, self.width() // 5)))
            p.drawText(self.rect().adjusted(2, 2, -2, -2),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, "🔒")

        # Red delete-zone highlight when dragging outside the canvas
        if getattr(self, '_delete_mode', False):
            p.setOpacity(0.6)
            p.fillRect(self.rect(), QColor(200, 30, 30))
            p.setOpacity(1.0)
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", max(10, self.width() // 4)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "🗑")
        else:
            # Subtle border
            p.setPen(QPen(QColor(C_ACCENT_PURPLE), 1))
            p.setOpacity(0.5)
            p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.end()

    # ── gesture handling ─────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos  = event.pos()
            self._is_dragging = False
            now = _time.monotonic() * 1000
            if (now - self._last_tap_ms) < self.TAP_WINDOW_MS:
                self._tap_count += 1
                self._tap_timer.stop()
                self._hold_timer.start(self.HOLD_DELETE_MS)
            else:
                self._tap_count = 1
            self._last_tap_ms = now
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and not self._is_dragging:
            if (event.pos() - self._press_pos).manhattanLength() > self.DRAG_THRESHOLD:
                if not self.placed.locked:
                    self._is_dragging = True
                    self._delete_mode = False
                    self._hold_timer.stop()
                    self._tap_timer.stop()
                    self._tap_count = 0
        if self._is_dragging and not self.placed.locked:
            centre = self.mapToParent(event.pos())
            new_x  = centre.x() - self.width()  // 2
            new_y  = centre.y() - self.height() // 2
            sx, sy, sw, sh = self._canvas._scene_rect()
            in_scene = (sx <= centre.x() <= sx + sw and sy <= centre.y() <= sy + sh)
            if in_scene:
                new_x = max(int(sx), min(int(sx + sw - self.width()),  new_x))
                new_y = max(int(sy), min(int(sy + sh - self.height()), new_y))
                self._delete_mode = False
            else:
                self._delete_mode = True
            self.move(new_x, new_y)
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                if getattr(self, '_delete_mode', False):
                    self._delete_mode = False
                    self._is_dragging = False
                    self.deleted.emit(self)
                    return
                self._update_placed_position()
                self.moved.emit(self)
                self._is_dragging = False
            elif self._tap_count == 1:
                self._tap_timer.start(self.TAP_WINDOW_MS)
            elif self._tap_count >= 2:
                self._hold_timer.stop()
                self.placed.visible = not self.placed.visible
                self.update()
                self.moved.emit(self)
                self._tap_count = 0
            self._press_pos = None
        event.accept()

    def _on_single_tap(self):
        self._tap_count = 0
        if self.placed.sound_path and os.path.exists(self.placed.sound_path):
            self._play_sound(self.placed.sound_path)

    def _on_hold_delete(self):
        self._tap_count = 0
        self.deleted.emit(self)

    def _on_toggle_lock(self):
        self.placed.locked = not self.placed.locked
        self.update()
        self.moved.emit(self)

    def _play_sound(self, path: str):
        if self._sound_player is None:
            self._sound_player = QMediaPlayer()
            self._sound_player._ao = QAudioOutput()
            self._sound_player.setAudioOutput(self._sound_player._ao)
        self._sound_player.setSource(QUrl.fromLocalFile(path))
        self._sound_player.play()

    def event(self, event):
        t = event.type()
        if t in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            pts = event.points()
            if len(pts) == 2:
                if t == QEvent.Type.TouchBegin:
                    self._touch_count = 2
                    self._two_finger_start = (pts[0].position(), pts[1].position())
                    self._lock_timer.start(self.LOCK_HOLD_MS)
                elif t == QEvent.Type.TouchUpdate and self._lock_timer.isActive():
                    # Cancel the lock hold once fingers move — it's a pinch, not a hold
                    s1, s2 = getattr(self, '_two_finger_start', (pts[0].position(), pts[1].position()))
                    moved = max((pts[0].position() - s1).manhattanLength(),
                                (pts[1].position() - s2).manhattanLength())
                    if moved > self.DRAG_THRESHOLD:
                        self._lock_timer.stop()
                elif t == QEvent.Type.TouchEnd:
                    self._lock_timer.stop()
                    self._touch_count = 0
                # Forward to the canvas so pinch-to-zoom works over props too
                self._canvas.event(event)
            elif self._touch_count == 2:
                self._lock_timer.stop()
                self._touch_count = len(pts)
                if t == QEvent.Type.TouchEnd:
                    self._canvas.event(event)
                    self._touch_count = 0
            return True
        return super().event(event)

    def _update_placed_position(self):
        sx, sy, sw, sh = self._canvas._scene_rect()
        if sw <= 0 or sh <= 0:
            return
        self.placed.x = max(0.0, min(1.0, (self.x() + self.width()  / 2 - sx) / sw))
        self.placed.y = max(0.0, min(1.0, (self.y() + self.height() / 2 - sy) / sh))


# ─────────────────────────────────────────────────────────────────────────────
# MiniMapCanvas — drop target that shows screen background + placed props
# ─────────────────────────────────────────────────────────────────────────────
class MiniMapCanvas(QWidget):
    def __init__(self, screen_idx: int, controller, parent=None):
        super().__init__(parent)
        self.screen_idx  = screen_idx
        self.controller  = controller
        self._items: list[PlacedAssetItem] = []
        self._bg_pixmap: Optional[QPixmap] = None
        self._scene_size = QSizeF(16, 9)
        # pinch-to-zoom / pan state (mirrors OutputWindow)
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._pinch_start_dist: float = 0.0
        self._pinch_start_zoom: float = 1.0
        self._pinch_start_pan: tuple = (0.0, 0.0)
        self._pinch_start_center: tuple = (0.0, 0.0)
        self._pan_drag_start: Optional[QPoint] = None
        self._pan_start: tuple = (0.0, 0.0)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.setAcceptDrops(True)
        self.setStyleSheet(f"background:{C_VOID};")
        self._refresh_background_from_output()

        for pa in controller.live_placed_assets.get(screen_idx, []):
            self._add_item(pa)

    def _output(self) -> Optional[OutputWindow]:
        return (self.controller.outputs[self.screen_idx]
                if self.screen_idx < len(self.controller.outputs) else None)

    def _refresh_background_from_output(self):
        output = self._output()
        if not output:
            return
        out_size = output.size()
        if out_size.width() <= 0 or out_size.height() <= 0:
            geo = output._screen.geometry()
            out_size = geo.size()
        self._scene_size = QSizeF(out_size.width(), out_size.height())
        frame = output.get_scene_frame(include_placed=False, target_size=out_size)
        if frame and not frame.isNull():
            self._bg_pixmap = frame

    def _scene_rect(self):
        sw = max(1.0, self._scene_size.width())
        sh = max(1.0, self._scene_size.height())
        scale = min(self.width() / sw, self.height() / sh) if self.width() and self.height() else 1.0
        scale *= self._zoom
        w = sw * scale
        h = sh * scale
        x = (self.width() - w) / 2 + self._pan_x
        y = (self.height() - h) / 2 + self._pan_y
        return x, y, w, h

    # ── pinch-to-zoom / pan ──────────────────────────────────────────────────

    def _apply_view(self):
        for item in self._items:
            self._position_item(item)
        self.update()

    def reset_zoom(self):
        self._zoom  = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._apply_view()

    def _clamp_pan(self):
        """Keep pan within the zoomed scene bounds so you can't pan to empty void."""
        if self._zoom <= 1.0:
            self._pan_x = 0.0
            self._pan_y = 0.0
            return
        max_pan_x = self.width()  * (self._zoom - 1) / 2
        max_pan_y = self.height() * (self._zoom - 1) / 2
        self._pan_x = max(-max_pan_x, min(max_pan_x, self._pan_x))
        self._pan_y = max(-max_pan_y, min(max_pan_y, self._pan_y))

    def _set_zoom_at(self, new_zoom: float, cx: float, cy: float):
        """Zoom so the scene point under (cx, cy) stays fixed on screen."""
        new_zoom = max(1.0, min(8.0, new_zoom))
        if new_zoom == self._zoom:
            return
        ratio = new_zoom / self._zoom
        # Vector from widget center to the anchor point scales with zoom;
        # pan must absorb the difference so the anchor stays put.
        wcx = self.width()  / 2
        wcy = self.height() / 2
        self._pan_x = (self._pan_x - (cx - wcx)) * ratio + (cx - wcx)
        self._pan_y = (self._pan_y - (cy - wcy)) * ratio + (cy - wcy)
        self._zoom  = new_zoom
        self._clamp_pan()
        self._apply_view()

    def event(self, e):
        t = e.type()
        if t in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            pts = e.points()
            if len(pts) == 2:
                p1 = pts[0].position()
                p2 = pts[1].position()
                dist = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
                cx   = (p1.x() + p2.x()) / 2
                cy   = (p1.y() + p2.y()) / 2
                if t == QEvent.Type.TouchBegin or self._pinch_start_dist == 0:
                    self._pinch_start_dist   = dist
                    self._pinch_start_zoom   = self._zoom
                    self._pinch_start_pan    = (self._pan_x, self._pan_y)
                    self._pinch_start_center = (cx, cy)
                elif t == QEvent.Type.TouchUpdate and self._pinch_start_dist > 0:
                    ratio    = dist / self._pinch_start_dist
                    new_zoom = max(1.0, min(8.0, self._pinch_start_zoom * ratio))
                    # Pan so the pinch center stays fixed on screen
                    dcx = cx - self._pinch_start_center[0]
                    dcy = cy - self._pinch_start_center[1]
                    self._zoom  = new_zoom
                    self._pan_x = self._pinch_start_pan[0] * ratio + dcx
                    self._pan_y = self._pinch_start_pan[1] * ratio + dcy
                    self._clamp_pan()
                    self._apply_view()
            elif t == QEvent.Type.TouchEnd:
                self._pinch_start_dist = 0
                if self._zoom < 1.05:
                    self.reset_zoom()
            return True
        return super().event(e)

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if steps:
            pos = event.position()
            self._set_zoom_at(self._zoom * (1.15 ** steps), pos.x(), pos.y())
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._zoom > 1.0:
            self._pan_drag_start = event.pos()
            self._pan_start      = (self._pan_x, self._pan_y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_drag_start is not None:
            d = event.pos() - self._pan_drag_start
            self._pan_x = self._pan_start[0] + d.x()
            self._pan_y = self._pan_start[1] + d.y()
            self._clamp_pan()
            self._apply_view()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pan_drag_start = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.reset_zoom()
        super().mouseDoubleClickEvent(event)

    def _sync_live_to_output(self):
        assets = self.get_placed_assets()
        self.controller.set_placed_assets(self.screen_idx, assets)
        row = self.controller.scene_list.currentRow()
        if 0 <= row < len(self.controller.scenes):
            self.controller.scenes[row].placed_assets[str(self.screen_idx)] = [asdict(pa) for pa in assets]
            self.controller._save_scenes()

    def get_placed_assets(self) -> list:
        return [item.placed for item in self._items]

    def _add_item(self, placed: PlacedAsset):
        item = PlacedAssetItem(placed, self, parent=self)
        self._position_item(item)
        item.deleted.connect(self._on_item_deleted)
        item.moved.connect(lambda _item: self._sync_live_to_output())
        item.show()
        item.raise_()
        self._items.append(item)

    def _position_item(self, item: PlacedAssetItem):
        sx, sy, sw, sh = self._scene_rect()
        w_px = max(30, int(item.placed.w * sw))
        h_px = max(30, int(item.placed.h * sh))
        x_px = int(sx + item.placed.x * sw - w_px / 2)
        y_px = int(sy + item.placed.y * sh - h_px / 2)
        x_px = max(int(sx), min(int(sx + sw - w_px), x_px))
        y_px = max(int(sy), min(int(sy + sh - h_px), y_px))
        item.resize(w_px, h_px)
        item.move(x_px, y_px)
        item.raise_()

    def _on_item_deleted(self, item: PlacedAssetItem):
        if item in self._items:
            self._items.remove(item)
        item.deleteLater()
        self._sync_live_to_output()

    def paintEvent(self, event):
        self._refresh_background_from_output()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C_VOID))
        sx, sy, sw, sh = self._scene_rect()
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            p.drawPixmap(int(sx), int(sy), int(sw), int(sh), self._bg_pixmap)
        p.setPen(QPen(QColor(C_ACCENT_PURPLE), 1))
        p.drawRect(int(sx), int(sy), int(sw) - 1, int(sh) - 1)
        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._clamp_pan()
        for item in self._items:
            self._position_item(item)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-asset-path") or mime.hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime = event.mimeData()
        path = ""
        size_w = 0.15
        size_h = 0.15
        snd_path = None

        if mime.hasFormat("application/x-asset-path"):
            path = bytes(mime.data("application/x-asset-path")).decode("utf-8")
            try:
                size_w = float(bytes(mime.data("application/x-asset-w")).decode("utf-8"))
                size_h = float(bytes(mime.data("application/x-asset-h")).decode("utf-8"))
            except Exception:
                pass
            if mime.hasFormat("application/x-asset-sound"):
                snd_path = bytes(mime.data("application/x-asset-sound")).decode("utf-8") or None
        elif mime.hasText():
            path = mime.text()

        if not path or not os.path.exists(path):
            event.ignore()
            return

        sx, sy, sw, sh = self._scene_rect()
        pos = event.position().toPoint()
        if not (sx <= pos.x() <= sx + sw and sy <= pos.y() <= sy + sh):
            event.ignore()
            return
        rx = (pos.x() - sx) / max(1.0, sw)
        ry = (pos.y() - sy) / max(1.0, sh)

        placed = PlacedAsset(
            asset_path=path,
            x=max(0.0, min(1.0, rx)),
            y=max(0.0, min(1.0, ry)),
            w=size_w,
            h=size_h,
            sound_path=snd_path,
        )

        self._add_item(placed)
        self._sync_live_to_output()
        event.acceptProposedAction()


# ─────────────────────────────────────────────────────────────────────────────
# MiniMapDialog — full-screen editor for placing props on a screen
# ─────────────────────────────────────────────────────────────────────────────
class MiniMapDialog(QDialog):
    def __init__(self, screen_idx: int, controller, parent=None):
        super().__init__(parent)
        self.screen_idx  = screen_idx
        self.controller  = controller
        self.setWindowTitle(f"Props — Screen {screen_idx + 1}")
        self._build_ui()
        self.showMaximized()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        top = QWidget()
        top.setFixedHeight(px(90))
        top.setStyleSheet(
            f"background:{C_CARD}; border-bottom:1px solid {C_BORDER_GOLD};")
        tl  = QHBoxLayout(top)
        tl.setContentsMargins(px(16), 0, px(16), 0)
        tl.setSpacing(px(12))

        title = QLabel(f"Props  ·  Screen {self.screen_idx + 1}")
        title.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(14)}pt; font-weight:700; color:{C_ACCENT_GOLD};')
        tl.addWidget(title)
        tl.addStretch(1)

        hint = QLabel(
            "Drag asset → map to place   •   Tap = play sound   •   "
            "Double-tap = hide/show   •   Double-tap + hold = delete   •   "
            "Two-finger 5 s = lock   •   Pinch = zoom   •   "
            "Drag map = pan   •   Double-tap map = reset zoom")
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        tl.addWidget(hint)
        tl.addStretch(1)

        back_btn = QPushButton("← Back")
        back_btn.setMinimumHeight(px(72))
        back_btn.setMinimumWidth(px(100))
        back_btn.clicked.connect(self.reject)

        save_btn = QPushButton("✔  Save to Scene")
        save_btn.setMinimumHeight(px(72))
        save_btn.setMinimumWidth(px(160))
        ControlWindow._make_accent(save_btn)
        save_btn.clicked.connect(self._save_to_scene)

        tl.addWidget(back_btn)
        tl.addSpacing(px(8))
        tl.addWidget(save_btn)
        root.addWidget(top)

        # ── Body: library | canvas ────────────────────────────────────────────
        body = QSplitter(Qt.Orientation.Horizontal)

        self._library = AssetLibraryPanel(self.controller, parent=self)
        body.addWidget(self._library)

        self._canvas = MiniMapCanvas(self.screen_idx, self.controller, parent=self)
        body.addWidget(self._canvas)
        body.setSizes([px(300), 1000])
        root.addWidget(body, 1)

    def _btn_style(self, accent: bool) -> str:
        return ""

    def _save_to_scene(self):
        assets = self._canvas.get_placed_assets()
        self.controller.set_placed_assets(self.screen_idx, assets)
        row = self.controller.scene_list.currentRow()
        if 0 <= row < len(self.controller.scenes):
            scene = self.controller.scenes[row]
            scene.placed_assets[str(self.screen_idx)] = [asdict(pa) for pa in assets]
            self.controller._save_scenes()
            QMessageBox.information(
                self, "Saved",
                f"Props saved to scene \"{scene.name}\".")
        else:
            QMessageBox.information(
                self, "Applied",
                "Props applied to screen. Save or update a scene to persist them.")
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# SceneEditorDialog — edit per-screen bg/overlay and music for a scene
# ─────────────────────────────────────────────────────────────────────────────
class SceneEditorDialog(QDialog):
    def __init__(self, scene: Scene, screen_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Scene: {scene.name}")
        self.setMinimumWidth(px(600))
        self.scene        = scene
        self.screen_count = screen_count
        self._bg: dict[str, str]        = {}
        self._overlay: dict[str, str]   = {}
        self._rotations: dict[str, int]  = dict(scene.rotations)
        self._fill_modes: dict[str, bool] = dict(scene.fill_modes)
        self._music: str = scene.music_path or ""

        for k, v in scene.assignments.items():
            layers = v if isinstance(v, list) else [v]
            if len(layers) > 0 and layers[0]:
                self._bg[k] = layers[0]
            if len(layers) > 1 and layers[1]:
                self._overlay[k] = layers[1]

        lay = QVBoxLayout(self)
        lay.setSpacing(px(8))

        lbl_style = f"color:{C_TEXT_RUNE}; font-size:{pt(10)}pt;"

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        _touch_scroll(scroll)

        screens_container = QWidget()
        screens_lay = QVBoxLayout(screens_container)
        screens_lay.setContentsMargins(0, 0, 0, 0)
        screens_lay.setSpacing(px(8))

        for i in range(screen_count):
            k = str(i)
            grp = QGroupBox(f"Screen {i + 1}")
            glay = QVBoxLayout(grp)
            glay.setSpacing(px(4))

            for role, label_text in (("bg", "Background:"), ("ov", "Overlay:")):
                row = QHBoxLayout()
                lbl = QLabel(label_text)
                lbl.setMinimumWidth(px(88))
                lbl.setStyleSheet(lbl_style)
                current = self._bg.get(k, "") if role == "bg" else self._overlay.get(k, "")
                edit = QLineEdit(os.path.basename(current) if current else "")
                edit.setObjectName(f"{role}_{k}")
                edit.setReadOnly(True)
                edit.setToolTip(current)
                browse = QPushButton("Browse…")
                browse.setMinimumWidth(px(80))
                clear  = QPushButton("✕")
                clear.setMinimumWidth(px(48))
                if role == "bg":
                    browse.clicked.connect(lambda _, ki=k: self._browse_bg(ki))
                    clear.clicked.connect(lambda _, ki=k: self._clear_field("bg", ki))
                else:
                    browse.clicked.connect(lambda _, ki=k: self._browse_ov(ki))
                    clear.clicked.connect(lambda _, ki=k: self._clear_field("ov", ki))
                row.addWidget(lbl)
                row.addWidget(edit, 1)
                row.addWidget(browse)
                row.addWidget(clear)
                glay.addLayout(row)

            # Rotation
            rot_row = QHBoxLayout()
            rot_lbl = QLabel("Rotate:")
            rot_lbl.setMinimumWidth(px(88))
            rot_lbl.setStyleSheet(lbl_style)
            rot_combo = QComboBox()
            rot_combo.addItems(["0°", "90°", "180°", "270°"])
            rot_combo.setObjectName(f"rot_{k}")
            cur_rot = self._rotations.get(k, 0)
            rot_combo.setCurrentIndex([0, 90, 180, 270].index(cur_rot) if cur_rot in [0, 90, 180, 270] else 0)
            rot_combo.currentIndexChanged.connect(
                lambda idx, ki=k: self._rotations.__setitem__(ki, [0, 90, 180, 270][idx]))
            rot_row.addWidget(rot_lbl)
            rot_row.addWidget(rot_combo, 1)
            glay.addLayout(rot_row)

            # Fill mode
            fill_row = QHBoxLayout()
            fill_lbl = QLabel("Display:")
            fill_lbl.setMinimumWidth(px(88))
            fill_lbl.setStyleSheet(lbl_style)
            fill_combo = QComboBox()
            fill_combo.addItems(["Fit", "Fill screen"])
            fill_combo.setObjectName(f"fill_{k}")
            fill_combo.setCurrentIndex(1 if self._fill_modes.get(k, False) else 0)
            fill_combo.currentIndexChanged.connect(
                lambda idx, ki=k: self._fill_modes.__setitem__(ki, idx == 1))
            fill_row.addWidget(fill_lbl)
            fill_row.addWidget(fill_combo, 1)
            glay.addLayout(fill_row)

            screens_lay.addWidget(grp)

        scroll.setWidget(screens_container)
        lay.addWidget(scroll, 1)

        # Music row
        mgrp = QGroupBox("Music")
        mrow = QHBoxLayout(mgrp)
        ml = QLabel("Track:")
        ml.setMinimumWidth(px(88))
        ml.setStyleSheet(lbl_style)
        self._music_edit = QLineEdit(os.path.basename(self._music) if self._music else "")
        self._music_edit.setObjectName("music_track")
        self._music_edit.setReadOnly(True)
        self._music_edit.setToolTip(self._music)
        mb = QPushButton("Browse…")
        mb.setMinimumWidth(px(80))
        mb.clicked.connect(self._browse_music)
        mc = QPushButton("✕")
        mc.setMinimumWidth(px(48))
        mc.clicked.connect(self._clear_music)
        mrow.addWidget(ml)
        mrow.addWidget(self._music_edit, 1)
        mrow.addWidget(mb)
        mrow.addWidget(mc)
        lay.addWidget(mgrp)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._fit_to_screen(parent)

    def _fit_to_screen(self, parent):
        """Cap dialog size to the available area of the screen it opens on, and
        center it there. Prevents the dialog from growing off-screen when many
        monitors are configured (each adds a Screen N group box)."""
        screen = None
        if parent is not None and parent.window() is not None:
            screen = parent.window().screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        margin_w = max(px(40), int(avail.width() * 0.05))
        margin_h = max(px(40), int(avail.height() * 0.05))
        self.setMaximumSize(avail.width() - margin_w, avail.height() - margin_h)
        self.resize(min(self.sizeHint().width(), self.maximumWidth()),
                    min(self.sizeHint().height(), self.maximumHeight()))
        x = avail.x() + (avail.width() - self.width()) // 2
        y = avail.y() + (avail.height() - self.height()) // 2
        self.move(x, y)

    def _btn(self):
        return ""

    def _combo_style(self):
        return ""

    def _set_field(self, name: str, path: str):
        w = self.findChild(QLineEdit, name)
        if w:
            w.setText(os.path.basename(path) if path else "")
            w.setToolTip(path)

    def _browse_bg(self, k: str):
        exts = " ".join(f"*{e}" for e in sorted(ALL_EXT))
        files = _pick_media_files(self, "Background media", MEDIA_DIR, f"Media ({exts})")
        if files:
            self._bg[k] = files[0]
            self._set_field(f"bg_{k}", files[0])

    def _browse_ov(self, k: str):
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXT | GIF_EXT))
        files = _pick_media_files(self, "Overlay image/GIF", MEDIA_DIR, f"Image/GIF ({exts})")
        if files:
            self._overlay[k] = files[0]
            self._set_field(f"ov_{k}", files[0])

    def _clear_field(self, role: str, k: str):
        if role == "bg":
            self._bg.pop(k, None)
        else:
            self._overlay.pop(k, None)
        self._set_field(f"{role}_{k}", "")

    def _browse_music(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Music track", MUSIC_DIR, f"Audio ({exts})", options=_DIALOG_OPTS)
        if path:
            self._music = path
            self._music_edit.setText(os.path.basename(path))
            self._music_edit.setToolTip(path)

    def _clear_music(self):
        self._music = ""
        self._music_edit.setText("")
        self._music_edit.setToolTip("")

    def apply_to_scene(self):
        assignments = {}
        for i in range(self.screen_count):
            k  = str(i)
            bg = self._bg.get(k, "")
            ov = self._overlay.get(k, "")
            if bg or ov:
                assignments[k] = [bg, ov] if ov else [bg]
        self.scene.assignments = assignments
        self.scene.music_path  = self._music or None
        self.scene.rotations   = dict(self._rotations)
        self.scene.fill_modes  = dict(self._fill_modes)


# ─────────────────────────────────────────────────────────────────────────────
# ClickableLabel — QLabel that emits clicked() on left-press
# ─────────────────────────────────────────────────────────────────────────────
class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# ScreenCard — one control card per output screen
# ─────────────────────────────────────────────────────────────────────────────
class ScreenCard(QFrame):
    def __init__(self, screen_index: int, controller):
        super().__init__()
        self.screen_index = screen_index
        self.controller   = controller
        self.setObjectName("screenCard")
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(px(280))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(10), px(10), px(10), px(10))
        lay.setSpacing(px(5))

        # live preview thumbnail (clickable → opens MiniMapDialog)
        self.preview_label = ClickableLabel()
        self.preview_label.setFixedSize(THUMB_W, THUMB_H)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            f"background:{C_VOID}; border-radius:{px(4)}px; border:1px solid {C_BORDER};")
        self.preview_label.setToolTip("Tap to open prop placement map")
        self.preview_label.clicked.connect(self._open_mini_map)
        lay.addWidget(self.preview_label, 0, Qt.AlignmentFlag.AlignHCenter)

        map_hint = QLabel("↑ Tap to place props")
        map_hint.setStyleSheet(
            f"color:{C_GLOW_PURPLE}; font-size:{pt(9)}pt; font-style:italic;")
        map_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(map_hint)

        title = QLabel(f"Screen {screen_index + 1}")
        title.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(13)}pt; font-weight:600; color:{C_TEXT_PARCH};')
        lay.addWidget(title)

        self.main_badge = QLabel("(control screen — not blacked out)")
        self.main_badge.setStyleSheet(f"color:{C_ACCENT_GOLD}; font-size:{pt(9)}pt;")
        self.main_badge.setVisible(False)
        lay.addWidget(self.main_badge)

        self.res_label = QLabel("")
        self.res_label.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        lay.addWidget(self.res_label)

        self.current_label = QLabel("— empty —")
        self.current_label.setWordWrap(True)
        self.current_label.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(10)}pt;")
        lay.addWidget(self.current_label)

        self.overlay_status = QLabel("Overlay: —")
        self.overlay_status.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        lay.addWidget(self.overlay_status)

        # BG controls
        bg_row = QHBoxLayout()
        bg_row.setSpacing(px(5))
        self._assign_btn = QPushButton("Set BG →")
        self._assign_btn.clicked.connect(self._assign_selected)
        self._clear_btn  = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._clear)
        bg_row.addWidget(self._assign_btn)
        bg_row.addWidget(self._clear_btn)
        lay.addLayout(bg_row)

        # Overlay controls
        ov_row = QHBoxLayout()
        ov_row.setSpacing(px(5))
        self._ov_btn = QPushButton("Set overlay →")
        self._ov_btn.clicked.connect(self._assign_overlay)
        self._ov_clear = QPushButton("Clear OV")
        self._ov_clear.clicked.connect(self._clear_overlay)
        ov_row.addWidget(self._ov_btn)
        ov_row.addWidget(self._ov_clear)
        lay.addLayout(ov_row)

        # Rotation
        rot_row = QHBoxLayout()
        rot_lbl = QLabel("Rotate:")
        rot_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self.rot_combo = QComboBox()
        self.rot_combo.addItems(["0°", "90°", "180°", "270°"])
        self.rot_combo.currentIndexChanged.connect(self._on_rotation_changed)
        rot_row.addWidget(rot_lbl)
        rot_row.addWidget(self.rot_combo, 1)
        lay.addLayout(rot_row)

        # Fill mode
        fill_row = QHBoxLayout()
        fill_lbl = QLabel("Display:")
        fill_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self.fill_combo = QComboBox()
        self.fill_combo.addItems(["Fit", "Fill screen"])
        self.fill_combo.currentIndexChanged.connect(self._on_fill_changed)
        fill_row.addWidget(fill_lbl)
        fill_row.addWidget(self.fill_combo, 1)
        lay.addLayout(fill_row)

        # ── Grid Overlay section ──────────────────────────────────────────────
        grid_grp = QGroupBox("Grid Overlay")
        grid_lay = QVBoxLayout(grid_grp)
        grid_lay.setSpacing(px(4))
        grid_lay.setContentsMargins(px(6), px(10), px(6), px(6))

        # Screen physical size
        sz_row = QHBoxLayout()
        sz_lbl = QLabel("Screen:")
        sz_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self._grid_w_spin = QDoubleSpinBox()
        self._grid_w_spin.setRange(1.0, 300.0)
        self._grid_w_spin.setValue(27.0)
        self._grid_w_spin.setSuffix("\" W")
        self._grid_w_spin.setDecimals(1)
        self._grid_h_spin = QDoubleSpinBox()
        self._grid_h_spin.setRange(1.0, 300.0)
        self._grid_h_spin.setValue(15.0)
        self._grid_h_spin.setSuffix("\" H")
        self._grid_h_spin.setDecimals(1)
        sz_row.addWidget(sz_lbl)
        sz_row.addWidget(self._grid_w_spin)
        sz_row.addWidget(self._grid_h_spin)
        grid_lay.addLayout(sz_row)

        # Toggle + type
        tog_row = QHBoxLayout()
        tog_row.setSpacing(px(5))
        self._grid_toggle = QPushButton("Grid: OFF")
        self._grid_toggle.setCheckable(True)
        self._grid_toggle.setChecked(False)
        self._grid_toggle.clicked.connect(self._on_grid_toggled)
        self._grid_type_combo = QComboBox()
        self._grid_type_combo.addItems(["Square", "Hex"])
        self._grid_type_combo.currentIndexChanged.connect(self._on_grid_changed)
        tog_row.addWidget(self._grid_toggle)
        tog_row.addWidget(self._grid_type_combo)
        grid_lay.addLayout(tog_row)

        # Cell size
        cell_row = QHBoxLayout()
        cell_lbl = QLabel("Cell:")
        cell_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self._grid_cell_spin = QDoubleSpinBox()
        self._grid_cell_spin.setRange(0.25, 12.0)
        self._grid_cell_spin.setValue(1.0)
        self._grid_cell_spin.setSingleStep(0.25)
        self._grid_cell_spin.setSuffix(" in")
        self._grid_cell_spin.setDecimals(2)
        self._grid_cell_spin.valueChanged.connect(self._on_grid_changed)
        cell_row.addWidget(cell_lbl)
        cell_row.addWidget(self._grid_cell_spin)
        grid_lay.addLayout(cell_row)

        # Color
        color_row = QHBoxLayout()
        color_lbl = QLabel("Color:")
        color_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self._grid_color = "#000000"
        self._grid_color_btn = QPushButton()
        self._grid_color_btn.setFixedHeight(px(28))
        self._grid_color_btn.setStyleSheet(
            f"background:{self._grid_color}; border:1px solid {C_BORDER}; border-radius:{px(4)}px;")
        self._grid_color_btn.clicked.connect(self._pick_grid_color)
        color_row.addWidget(color_lbl)
        color_row.addWidget(self._grid_color_btn)
        grid_lay.addLayout(color_row)

        lay.addWidget(grid_grp)

        # Connect screen size spinboxes after grid_grp is built
        self._grid_w_spin.valueChanged.connect(self._on_screen_size_changed)
        self._grid_h_spin.valueChanged.connect(self._on_screen_size_changed)

        drop_lbl = QLabel("Drop a file here", alignment=Qt.AlignmentFlag.AlignCenter)
        drop_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt; font-style:italic;")
        lay.addWidget(drop_lbl)

    def _combo_style(self):
        return ""

    def _spin_style(self):
        return ""

    # ── public update methods ─────────────────────────────────────────────────

    def set_resolution_text(self, text: str):
        self.res_label.setText(text)

    def update_current(self, path: Optional[str]):
        self.current_label.setText(
            os.path.basename(path) if path else "— empty —")

    def update_overlay_label(self, path: Optional[str]):
        self.overlay_status.setText(
            f"Overlay: {os.path.basename(path)}" if path else "Overlay: —")

    def set_preview(self, pix: Optional[QPixmap]):
        if pix and not pix.isNull():
            self.preview_label.setPixmap(
                pix.scaled(THUMB_W, THUMB_H,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview_label.clear()

    def set_is_main(self, is_main: bool):
        self.main_badge.setVisible(is_main)
        for w in (self._assign_btn, self._clear_btn, self._ov_btn,
                  self._ov_clear, self.rot_combo, self.fill_combo,
                  self._grid_toggle, self._grid_type_combo, self._grid_cell_spin,
                  self._grid_color_btn, self._grid_w_spin, self._grid_h_spin):
            w.setEnabled(not is_main)

    def update_grid_ui(self, settings: dict, screen_size: dict = None):
        for w in (self._grid_toggle, self._grid_type_combo, self._grid_cell_spin,
                  self._grid_w_spin, self._grid_h_spin):
            w.blockSignals(True)
        enabled = settings.get("enabled", False)
        self._grid_toggle.setChecked(enabled)
        self._grid_toggle.setText("Grid: ON" if enabled else "Grid: OFF")
        self._grid_type_combo.setCurrentIndex(
            1 if settings.get("grid_type") == "hex" else 0)
        self._grid_cell_spin.setValue(settings.get("cell_size", 1.0))
        color = settings.get("color", "#000000")
        self._grid_color = color
        self._grid_color_btn.setStyleSheet(
            f"background:{color}; border:1px solid {C_BORDER}; border-radius:{px(4)}px;")
        sz = screen_size or {}
        w_in = sz.get("w") or settings.get("screen_w_in", 27.0)
        h_in = sz.get("h") or settings.get("screen_h_in", 15.0)
        self._grid_w_spin.setValue(w_in)
        self._grid_h_spin.setValue(h_in)
        for w in (self._grid_toggle, self._grid_type_combo, self._grid_cell_spin,
                  self._grid_w_spin, self._grid_h_spin):
            w.blockSignals(False)

    # ── button handlers ───────────────────────────────────────────────────────

    def _assign_selected(self):
        sel = self.controller.selected_media_path()
        if sel:
            self.controller.push_to_screen(self.screen_index, sel)

    def _clear(self):
        self.controller.clear_screen(self.screen_index)

    def _assign_overlay(self):
        sel = self.controller.selected_media_path()
        if sel:
            self.controller.push_overlay_to_screen(self.screen_index, sel)

    def _clear_overlay(self):
        self.controller.clear_overlay_screen(self.screen_index)

    def _on_rotation_changed(self, idx: int):
        self.controller.set_rotation(self.screen_index, [0, 90, 180, 270][idx])

    def _on_fill_changed(self, idx: int):
        self.controller.set_fill_mode(self.screen_index, idx == 1)

    def _on_grid_toggled(self):
        enabled = self._grid_toggle.isChecked()
        self._grid_toggle.setText("Grid: ON" if enabled else "Grid: OFF")
        self._on_grid_changed()

    def _on_grid_changed(self):
        settings = self._get_grid_settings()
        self.controller.update_live_grid(self.screen_index, settings)

    def _on_screen_size_changed(self):
        k = str(self.screen_index)
        self.controller.screen_sizes[k] = {
            "w": self._grid_w_spin.value(),
            "h": self._grid_h_spin.value(),
        }
        self.controller._save_scenes()
        if self._grid_toggle.isChecked():
            self.controller.update_live_grid(self.screen_index, self._get_grid_settings())

    def _get_grid_settings(self) -> dict:
        return {
            "enabled":      self._grid_toggle.isChecked(),
            "grid_type":    "hex" if self._grid_type_combo.currentIndex() == 1 else "square",
            "cell_size":    self._grid_cell_spin.value(),
            "color":        self._grid_color,
            "screen_w_in":  self._grid_w_spin.value(),
            "screen_h_in":  self._grid_h_spin.value(),
        }

    def _pick_grid_color(self):
        color = QColorDialog.getColor(QColor(self._grid_color), self, "Grid Color")
        if color.isValid():
            self._grid_color = color.name()
            self._grid_color_btn.setStyleSheet(
                f"background:{self._grid_color}; border:1px solid {C_BORDER}; border-radius:{px(4)}px;")
            self._on_grid_changed()

    def _open_mini_map(self):
        if self.screen_index == self.controller._main_screen_idx:
            return
        dlg = MiniMapDialog(self.screen_index, self.controller, parent=self)
        dlg.exec()
        QTimer.singleShot(200, lambda: self.controller._refresh_thumb(self.screen_index))

    def dragEnterEvent(self, e: QDragEnterEvent):
        mime = e.mimeData()
        if mime.hasUrls() or mime.hasFormat("application/x-asset-path") or mime.hasText():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        mime = e.mimeData()
        p = ""
        if mime.hasUrls():
            for url in mime.urls():
                candidate = url.toLocalFile()
                if media_kind(candidate):
                    p = candidate
                    break
        elif mime.hasFormat("application/x-asset-path"):
            p = bytes(mime.data("application/x-asset-path")).decode("utf-8")
        elif mime.hasText():
            p = mime.text()

        if p and media_kind(p):
            self.controller.add_media(p)
            self.controller.push_to_screen(self.screen_index, p)


# ─────────────────────────────────────────────────────────────────────────────
# MediaPreviewFileDialog — open/add-file dialog with a live preview pane
# (image → static, gif → animated, video → muted playback)
# ─────────────────────────────────────────────────────────────────────────────
class MediaPreviewFileDialog(QFileDialog):
    PREVIEW_SIZE = 240

    def __init__(self, parent, title: str, directory: str, name_filter: str):
        super().__init__(parent, title, directory, name_filter)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self._movie: Optional[QMovie] = None
        self._build_preview()
        self.currentChanged.connect(self._update_preview)

    def _build_preview(self):
        ts = px(self.PREVIEW_SIZE)

        self._img_label = QLabel("No preview")
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setWordWrap(True)

        self._video_widget = QVideoWidget()
        self._video_player = QMediaPlayer(self)
        self._video_audio = QAudioOutput(self)
        self._video_audio.setMuted(True)
        self._video_player.setAudioOutput(self._video_audio)
        self._video_player.setVideoOutput(self._video_widget)
        self._video_player.setLoops(QMediaPlayer.Loops.Infinite)

        holder = QWidget()
        holder.setFixedSize(ts, ts)
        holder.setStyleSheet(
            f"background:{C_VOID}; color:{C_TEXT_RUNE}; border-radius:{px(6)}px;")
        self._preview_stack = QStackedLayout(holder)
        self._preview_stack.addWidget(self._img_label)
        self._preview_stack.addWidget(self._video_widget)

        layout = self.layout()
        if isinstance(layout, QGridLayout):
            layout.addWidget(holder, 0, layout.columnCount(), layout.rowCount(), 1)

    def _update_preview(self, path: str):
        self._video_player.stop()
        if self._movie is not None:
            self._movie.stop()
            self._movie = None

        kind = media_kind(path) if path else None
        if kind in ("image", "gif") and os.path.isfile(path):
            self._preview_stack.setCurrentWidget(self._img_label)
            ts = px(self.PREVIEW_SIZE)
            if kind == "gif":
                self._movie = QMovie(path)
                self._movie.setScaledSize(QSize(ts, ts))
                self._img_label.setMovie(self._movie)
                self._movie.start()
            else:
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                pix = QPixmap.fromImage(reader.read())
                self._img_label.setMovie(None)
                if not pix.isNull():
                    self._img_label.setPixmap(
                        pix.scaled(ts, ts, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
                else:
                    self._img_label.setText("No preview")
        elif kind == "video" and os.path.isfile(path):
            self._preview_stack.setCurrentWidget(self._video_widget)
            self._video_player.setSource(QUrl.fromLocalFile(path))
            self._video_player.play()
        else:
            self._preview_stack.setCurrentWidget(self._img_label)
            self._img_label.setMovie(None)
            self._img_label.setPixmap(QPixmap())
            self._img_label.setText("No preview")

    def done(self, result):
        self._video_player.stop()
        if self._movie is not None:
            self._movie.stop()
        super().done(result)


def _pick_media_files(parent, title: str, directory: str, name_filter: str,
                       multi: bool = False) -> list[str]:
    dlg = MediaPreviewFileDialog(parent, title, directory, name_filter)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFiles if multi
                     else QFileDialog.FileMode.ExistingFile)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.selectedFiles()
    return []


# ─────────────────────────────────────────────────────────────────────────────
# MediaListWidget — Media Library list that supports dragging items onto a
# ScreenCard (drop target already understands application/x-asset-path)
# ─────────────────────────────────────────────────────────────────────────────
class MediaListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        path = item.path
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-asset-path", path.encode())
        mime.setText(path)
        drag.setMimeData(mime)
        icon = item.icon()
        if not icon.isNull():
            pm = icon.pixmap(px(40), px(40))
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)


# ─────────────────────────────────────────────────────────────────────────────
# ControlWindow — main control panel
# ─────────────────────────────────────────────────────────────────────────────
class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SceneCaster — Control")
        self.resize(1200, 820)
        self._apply_dark_theme()

        self.outputs: list[OutputWindow]    = []
        self.screen_cards: list[ScreenCard] = []
        self.scenes: list[Scene]            = []
        self.live_assignments: dict[int, str] = {}
        self.live_overlays: dict[int, str]    = {}
        self.live_grid_settings: dict[int, dict] = {}
        self.live_placed_assets: dict[int, list] = {}
        self.screen_sizes: dict[str, dict]    = {}
        self.asset_library: list[AssetItem]   = []
        self._main_screen_idx: int = 0

        # timers kept alive for music fade operations
        self._music_fade_out_timer: Optional[QTimer] = None
        self._music_fade_in_timer:  Optional[QTimer] = None

        self._build_outputs()
        self._build_music_backend()
        self._build_ui()
        self._load_scenes()

    # ── theming ───────────────────────────────────────────────────────────────

    def _apply_dark_theme(self):
        f = QFont(FONT_BODY)
        f.setPointSize(pt(10))
        QApplication.instance().setFont(f)

        qss = f"""
        QWidget {{
            background: {C_PANEL};
            color: {C_TEXT_PARCH};
            font-family: "{FONT_BODY}";
            font-size: {pt(10)}pt;
        }}
        ControlWindow {{
            background: {C_VOID};
        }}
        QLabel {{
            border: none;
            background: transparent;
        }}
        QPushButton {{
            background: {C_CARD};
            color: {C_TEXT_PARCH};
            border: none;
            border-top: 2px solid {C_GOLD_DIM};
            padding: {px(10)}px {px(24)}px;
            border-radius: {px(10)}px;
            font-size: {pt(11)}pt;
            min-height: {px(72)}px;
        }}
        QPushButton:hover {{
            background: {C_HOVER};
            border-top: 1px solid {C_ACCENT_GOLD};
        }}
        QPushButton:pressed {{
            background: {C_ACCENT_PURPLE};
            color: white;
        }}
        QPushButton:disabled {{
            background: {C_VOID};
            color: {C_TEXT_RUNE};
            border-top: 1px solid {C_BORDER};
        }}
        QPushButton:checked {{
            background: {C_ACCENT_PURPLE};
            color: white;
            border-top: 1px solid {C_GLOW_PURPLE};
        }}
        QPushButton[accent="true"] {{
            background: {C_ACCENT_GOLD};
            color: {C_VOID};
            font-weight: 700;
            border: none;
        }}
        QPushButton[accent="true"]:hover {{
            background: #d4aa30;
        }}
        QPushButton[accent="true"]:pressed {{
            background: #b08a1a;
        }}
        QPushButton[danger="true"] {{
            background: #1a0505;
            color: #ff7070;
            border-top: 1px solid {C_DANGER};
        }}
        QPushButton[danger="true"]:hover {{
            background: #2a0a0a;
        }}
        QListWidget {{
            background: {C_VOID};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_BORDER};
            border-radius: {px(8)}px;
            padding: {px(3)}px;
        }}
        QListWidget::item {{
            padding: {px(14)}px {px(10)}px;
            border-radius: {px(6)}px;
            min-height: {px(64)}px;
        }}
        QListWidget::item:selected {{
            background: {C_CARD};
            color: {C_ACCENT_GOLD};
            border-left: 3px solid {C_ACCENT_GOLD};
        }}
        QListWidget::item:hover:!selected {{
            background: {C_HOVER};
        }}
        QComboBox {{
            background: {C_INPUT};
            color: {C_TEXT_PARCH};
            padding: {px(12)}px {px(16)}px;
            border-radius: {px(8)}px;
            border: 1px solid {C_BORDER};
            font-size: {pt(11)}pt;
            min-height: {px(60)}px;
        }}
        QComboBox:hover {{
            border: 1px solid {C_GOLD_DIM};
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background: {C_CARD};
            color: {C_TEXT_PARCH};
            selection-background-color: {C_HOVER};
            selection-color: {C_ACCENT_GOLD};
            border: 1px solid {C_BORDER};
        }}
        QLineEdit {{
            background: {C_INPUT};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_BORDER};
            border-radius: {px(8)}px;
            padding: {px(10)}px {px(14)}px;
            min-height: {px(56)}px;
        }}
        QLineEdit:focus {{
            border: 1px solid {C_ACCENT_GOLD};
        }}
        QGroupBox {{
            color: {C_ACCENT_GOLD};
            font-weight: 600;
            font-size: {pt(10)}pt;
            border: 1px solid {C_ACCENT_PURPLE};
            border-radius: {px(8)}px;
            margin-top: {px(10)}px;
            padding-top: {px(12)}px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {px(12)}px;
            color: {C_ACCENT_GOLD};
        }}
        QSlider::groove:horizontal {{
            background: {C_BORDER};
            height: {px(6)}px;
            border-radius: {px(3)}px;
        }}
        QSlider::handle:horizontal {{
            background: {C_ACCENT_GOLD};
            width: {px(32)}px;
            height: {px(32)}px;
            border-radius: {px(16)}px;
            margin: {px(-14)}px 0;
        }}
        QSlider::sub-page:horizontal {{
            background: {C_ACCENT_PURPLE};
            border-radius: {px(2)}px;
        }}
        QScrollBar:vertical {{
            width: {px(8)}px;
            background: {C_VOID};
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {C_GOLD_DIM};
            border-radius: {px(4)}px;
            min-height: {px(24)}px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {C_ACCENT_GOLD};
        }}
        QScrollBar:horizontal {{
            height: {px(8)}px;
            background: {C_VOID};
        }}
        QScrollBar::handle:horizontal {{
            background: {C_GOLD_DIM};
            border-radius: {px(4)}px;
            min-width: {px(24)}px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {C_ACCENT_GOLD};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; }}
        QFrame#screenCard {{
            background: {C_CARD};
            border: 1px solid {C_BORDER};
            border-top: 2px solid {C_BORDER_GOLD};
            border-radius: {px(10)}px;
        }}
        QFrame#screenCard:hover {{
            border: 1px solid {C_ACCENT_PURPLE};
            border-top: 2px solid {C_ACCENT_GOLD};
        }}
        QFrame#musicPanel {{
            background: {C_CARD};
            border: 1px solid {C_BORDER};
            border-top: 2px solid {C_BORDER_GOLD};
            border-radius: {px(8)}px;
        }}
        QCheckBox {{
            color: {C_TEXT_AGED};
            spacing: {px(8)}px;
        }}
        QCheckBox::indicator {{
            width: {px(28)}px;
            height: {px(28)}px;
            border: 1px solid {C_BORDER};
            border-radius: {px(6)}px;
            background: {C_INPUT};
        }}
        QCheckBox::indicator:checked {{
            background: {C_ACCENT_GOLD};
            border-color: {C_ACCENT_GOLD};
        }}
        QSpinBox, QDoubleSpinBox {{
            background: {C_INPUT};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_BORDER};
            border-radius: {px(8)}px;
            padding: {px(8)}px {px(10)}px;
            min-height: {px(52)}px;
        }}
        QSplitter::handle {{
            background: {C_BORDER};
        }}
        QSplitter::handle:horizontal {{
            width: {px(2)}px;
        }}
        QToolTip {{
            background: {C_CARD};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_ACCENT_GOLD};
            padding: {px(5)}px;
            border-radius: {px(4)}px;
        }}
        QScrollArea {{
            background: {C_VOID};
            border: none;
        }}
        QDialog {{
            background: {C_PANEL};
        }}
        """
        self.setStyleSheet(qss)

    def btn_style(self):
        return ""

    def accent_btn_style(self):
        return ""

    def _combo_style(self):
        return ""

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _runic_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(9)}pt; '
            f'color:{C_ACCENT_GOLD}; letter-spacing:3px; font-weight:600;'
        )
        return lbl

    @staticmethod
    def _make_accent(btn: QPushButton) -> QPushButton:
        btn.setProperty("accent", "true")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    @staticmethod
    def _make_danger(btn: QPushButton) -> QPushButton:
        btn.setProperty("danger", "true")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    # ── music backend ─────────────────────────────────────────────────────────

    def _build_music_backend(self):
        self._music_player = QMediaPlayer()
        self._music_audio  = QAudioOutput()
        self._music_player.setAudioOutput(self._music_audio)
        self._music_audio.setVolume(0.7)
        self._music_loop   = True
        self._music_player.mediaStatusChanged.connect(self._on_music_status)

    def _on_music_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._music_loop:
            self._music_player.setPosition(0)
            self._music_player.play()

    def _on_speaker_changed(self, idx: int):
        if 0 <= idx < len(self._audio_devices):
            self._music_audio.setDevice(self._audio_devices[idx])

    def _play_music(self, path: str):
        if not path or not os.path.exists(path):
            return
        self._music_player.setSource(QUrl.fromLocalFile(path))
        self._music_player.play()
        self._music_track_label.setText(os.path.basename(path))

    def _play_music_with_fade(self, path: str):
        target_vol = self._vol_slider.value() / 100.0
        is_playing = (self._music_player.playbackState() ==
                      QMediaPlayer.PlaybackState.PlayingState)
        if is_playing:
            self._music_fade_out(
                MUSIC_FADE_MS,
                lambda: self._start_and_fade_in(path, target_vol))
        else:
            self._start_and_fade_in(path, target_vol)

    def _start_and_fade_in(self, path: str, target_vol: float):
        self._music_audio.setVolume(0.0)
        self._play_music(path)
        self._music_fade_in(MUSIC_FADE_MS, target_vol)

    def _music_fade_out(self, duration_ms: int, callback):
        if self._music_fade_out_timer:
            self._music_fade_out_timer.stop()
        start_vol = self._music_audio.volume()
        if start_vol <= 0.001:
            self._music_player.stop()
            callback()
            return
        steps    = max(1, duration_ms // 30)
        step_vol = start_vol / steps
        current  = [start_vol]
        timer    = QTimer(self)
        def tick():
            current[0] = max(0.0, current[0] - step_vol)
            self._music_audio.setVolume(current[0])
            if current[0] <= 0.0:
                timer.stop()
                self._music_player.stop()
                callback()
        timer.timeout.connect(tick)
        timer.start(30)
        self._music_fade_out_timer = timer

    def _music_fade_in(self, duration_ms: int, target_vol: float):
        if self._music_fade_in_timer:
            self._music_fade_in_timer.stop()
        if target_vol <= 0:
            return
        steps    = max(1, duration_ms // 30)
        step_vol = target_vol / steps
        current  = [0.0]
        timer    = QTimer(self)
        def tick():
            current[0] = min(target_vol, current[0] + step_vol)
            self._music_audio.setVolume(current[0])
            if current[0] >= target_vol:
                timer.stop()
        timer.timeout.connect(tick)
        timer.start(30)
        self._music_fade_in_timer = timer

    # ── output windows ────────────────────────────────────────────────────────

    def _build_outputs(self):
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        self._primary = primary
        self._main_screen_idx = screens.index(primary) if primary in screens else 0
        for idx, scr in enumerate(screens):
            win = OutputWindow(idx, scr)
            self.outputs.append(win)
            if idx != self._main_screen_idx:
                win.place_on_screen()
        QTimer.singleShot(300, self._reclaim_focus)

    def _reclaim_focus(self):
        self.raise_()
        self.activateWindow()

    # ── grid live update ──────────────────────────────────────────────────────

    def update_live_grid(self, idx: int, settings: dict):
        self.live_grid_settings[idx] = settings
        if idx < len(self.outputs):
            self.outputs[idx].apply_grid(settings)

    # ── placed asset management ───────────────────────────────────────────────

    def set_placed_assets(self, idx: int, assets: list):
        self.live_placed_assets[idx] = list(assets)
        if idx < len(self.outputs):
            self.outputs[idx].set_placed_assets(assets)
        if idx < len(self.screen_cards):
            self._refresh_thumb(idx)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(px(16), px(16), px(16), px(16))
        root.setSpacing(px(10))

        header = QLabel("SceneCaster")
        header.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(22)}pt; font-weight:700; color:{C_ACCENT_GOLD};'
        )
        sub = QLabel("Arcane Screen Weaver  •  D&D Storytelling Display Controller")
        sub.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(10)}pt; color:{C_TEXT_RUNE}; letter-spacing:1px;'
        )
        exit_btn = QPushButton("⏻  Exit")
        exit_btn.setProperty("danger", True)
        exit_btn.setMinimumHeight(px(72))
        exit_btn.setMinimumWidth(px(140))
        exit_btn.clicked.connect(self._confirm_exit)

        head_row = QHBoxLayout()
        head_row.setSpacing(px(12))
        head_col = QVBoxLayout()
        head_col.setSpacing(0)
        head_col.addWidget(header)
        head_col.addWidget(sub)
        head_row.addLayout(head_col)
        head_row.addStretch(1)
        head_row.addWidget(exit_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(head_row)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(f"background:{C_GOLD_DIM}; max-height:1px; border:none;")
        rule.setFixedHeight(1)
        root.addWidget(rule)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # ── LEFT: media library + scenes ──────────────────────────────────────
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(px(6))

        lib_lbl = self._runic_label("Media Library")
        ll.addWidget(lib_lbl)

        self.media_list = MediaListWidget()
        self.media_list.setIconSize(QSize(px(40), px(40)))
        self.media_list.setAcceptDrops(True)
        self.media_list.itemDoubleClicked.connect(self._preview_or_hint)
        _touch_scroll(self.media_list)
        ll.addWidget(self.media_list, 1)

        mb_row = QHBoxLayout()
        mb_row.setSpacing(px(6))
        for lbl, cb in (("Add files…", self._add_files_dialog),
                        ("Add folder…", self._add_folder_dialog)):
            b = QPushButton(lbl)
            b.clicked.connect(cb)
            mb_row.addWidget(b)
        ll.addLayout(mb_row)

        scn_lbl = self._runic_label("Scenes")
        ll.addWidget(scn_lbl)

        self.scene_list = QListWidget()
        self.scene_list.itemDoubleClicked.connect(self._activate_scene_item)
        _touch_scroll(self.scene_list)
        ll.addWidget(self.scene_list, 1)

        sb_row = QHBoxLayout()
        sb_row.setSpacing(px(6))
        for lbl, cb in (("Save current", self._save_scene),
                        ("Edit scene…",  self._edit_scene),
                        ("Delete",       self._delete_scene)):
            b = QPushButton(lbl)
            b.clicked.connect(cb)
            if lbl == "Delete":
                self._make_danger(b)
            sb_row.addWidget(b)
        ll.addLayout(sb_row)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(px(6))
        prev_btn = QPushButton("◀ Prev")
        prev_btn.clicked.connect(lambda: self._step_scene(-1))
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(lambda: self._step_scene(1))
        self._make_accent(next_btn)
        nav_row.addWidget(prev_btn)
        nav_row.addWidget(next_btn)
        ll.addLayout(nav_row)

        splitter.addWidget(left)

        # ── RIGHT: screen cards + music + global ──────────────────────────────
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(px(8))

        scr_lbl = self._runic_label("Connected Screens")
        rl.addWidget(scr_lbl)

        ctrl_row = QHBoxLayout()
        ctrl_lbl = QLabel("Control panel on:")
        ctrl_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(10)}pt;")
        self.main_screen_combo = QComboBox()
        for i in range(len(self.outputs)):
            self.main_screen_combo.addItem(f"Screen {i + 1}")
        self.main_screen_combo.setCurrentIndex(self._main_screen_idx)
        self.main_screen_combo.currentIndexChanged.connect(self._set_main_screen)
        ctrl_row.addWidget(ctrl_lbl)
        ctrl_row.addWidget(self.main_screen_combo, 1)
        rl.addLayout(ctrl_row)

        cards_scroll  = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        _touch_scroll(cards_scroll)
        cards_holder  = QWidget()
        self.cards_grid = QGridLayout(cards_holder)
        self.cards_grid.setSpacing(px(12))

        for idx, scr in enumerate(QGuiApplication.screens()):
            card = ScreenCard(idx, self)
            geo  = scr.geometry()
            dpr  = scr.devicePixelRatio()
            rw   = int(geo.width() * dpr)
            rh   = int(geo.height() * dpr)
            tag  = " (primary)" if scr == self._primary else ""
            res  = f"{rw}×{rh}{tag}" + ("  • 4K" if rw >= 3840 else "")
            card.set_resolution_text(res)
            card.set_is_main(idx == self._main_screen_idx)
            self.screen_cards.append(card)
            self.cards_grid.addWidget(card, idx // 2, idx % 2)

        cards_scroll.setWidget(cards_holder)
        rl.addWidget(cards_scroll, 1)

        # ── Music panel ───────────────────────────────────────────────────────
        mf = QFrame()
        mf.setObjectName("musicPanel")
        mfl = QVBoxLayout(mf)
        mfl.setContentsMargins(px(12), px(10), px(12), px(10))
        mfl.setSpacing(px(6))

        mf_hdr = QLabel("♪  Music Layer")
        mf_hdr.setStyleSheet(
            f'font-family:"{FONT_SERIF}"; font-size:{pt(11)}pt; font-weight:600; color:{C_ACCENT_GOLD};'
        )
        mfl.addWidget(mf_hdr)

        spk_row = QHBoxLayout()
        spk_lbl = QLabel("Output:")
        spk_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self._speaker_combo = QComboBox()
        self._audio_devices = QMediaDevices.audioOutputs()
        default_dev = QMediaDevices.defaultAudioOutput()
        for dev in self._audio_devices:
            self._speaker_combo.addItem(dev.description())
        default_idx = next(
            (i for i, d in enumerate(self._audio_devices) if d.id() == default_dev.id()), 0)
        self._speaker_combo.setCurrentIndex(default_idx)
        self._speaker_combo.currentIndexChanged.connect(self._on_speaker_changed)
        spk_row.addWidget(spk_lbl)
        spk_row.addWidget(self._speaker_combo, 1)
        mfl.addLayout(spk_row)

        self._music_track_label = QLabel("No track loaded")
        self._music_track_label.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        mfl.addWidget(self._music_track_label)

        mc_row = QHBoxLayout()
        mc_row.setSpacing(px(6))
        play_b  = QPushButton("▶ Play")
        pause_b = QPushButton("⏸ Pause")
        stop_b  = QPushButton("⏹ Stop")
        add_m_b = QPushButton("Add music…")
        play_b.clicked.connect(self._music_player.play)
        pause_b.clicked.connect(self._music_player.pause)
        stop_b.clicked.connect(self._music_player.stop)
        add_m_b.clicked.connect(self._add_music_dialog)
        self._make_accent(play_b)
        for b in (play_b, pause_b, stop_b, add_m_b):
            mc_row.addWidget(b)
        mfl.addLayout(mc_row)

        vol_row = QHBoxLayout()
        vol_lbl = QLabel("Vol:")
        vol_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.valueChanged.connect(
            lambda v: self._music_audio.setVolume(v / 100.0))
        self._loop_chk = QCheckBox("Loop")
        self._loop_chk.setChecked(True)
        self._loop_chk.toggled.connect(self._set_music_loop)
        vol_row.addWidget(vol_lbl)
        vol_row.addWidget(self._vol_slider, 1)
        vol_row.addWidget(self._loop_chk)
        mfl.addLayout(vol_row)

        rl.addWidget(mf)

        # Global controls
        glob_row = QHBoxLayout()
        glob_row.setSpacing(px(8))
        blank_all_b = QPushButton("⬛  Blank all screens")
        blank_all_b.clicked.connect(self.blank_all)
        self._make_danger(blank_all_b)
        self.mute_combo = QComboBox()
        self.mute_combo.addItems(["Video audio: ON", "Video audio: MUTED"])
        glob_row.addWidget(blank_all_b)
        glob_row.addStretch(1)
        glob_row.addWidget(self.mute_combo)
        rl.addLayout(glob_row)

        splitter.addWidget(right)
        splitter.setSizes([px(400), px(900)])

        hint = QLabel(
            "Select media → 'Set BG →' for background, 'Set overlay →' for composited overlay. "
            "Double-click a scene to activate it. ◀ / ▶ or ← / → to step scenes. B = blank all. "
            "Use 'Edit scene…' to configure bg/overlay/music per screen without going live first."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        root.addWidget(hint)

    def _set_music_loop(self, checked: bool):
        self._music_loop = checked

    # ── main screen ───────────────────────────────────────────────────────────

    def _move_control_to_screen(self, screen_idx: int):
        screens = QGuiApplication.screens()
        if screen_idx < len(screens):
            geo = screens[screen_idx].geometry()
            self.move(geo.topLeft())
            self.showMaximized()

    def _set_main_screen(self, new_idx: int):
        old_idx = self._main_screen_idx
        if old_idx == new_idx:
            return
        self._main_screen_idx = new_idx
        if old_idx < len(self.outputs):
            self.outputs[old_idx].place_on_screen()
        if new_idx < len(self.outputs):
            self.outputs[new_idx].hide()
        for i, card in enumerate(self.screen_cards):
            card.set_is_main(i == new_idx)
        self._move_control_to_screen(new_idx)
        self._save_scenes()
        QTimer.singleShot(300, self._reclaim_focus)

    # ── rotation / fill ───────────────────────────────────────────────────────

    def set_rotation(self, screen_idx: int, degrees: int):
        if screen_idx < len(self.outputs):
            self.outputs[screen_idx].set_rotation(degrees)

    def set_fill_mode(self, screen_idx: int, fill: bool):
        if screen_idx < len(self.outputs):
            self.outputs[screen_idx].set_fill_mode(fill)

    # ── media library ─────────────────────────────────────────────────────────

    def add_media(self, path: str):
        for i in range(self.media_list.count()):
            if self.media_list.item(i).path == path:
                return
        self.media_list.addItem(MediaTile(path))

    def _add_files_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(ALL_EXT))
        files = _pick_media_files(self, "Add media", MEDIA_DIR, f"Media ({exts})", multi=True)
        for f in files:
            self.add_media(f)

    def _add_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(
            self, "Add folder", MEDIA_DIR,
            options=QFileDialog.Option.ShowDirsOnly | _DIALOG_OPTS)
        if not d:
            return
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isfile(p) and media_kind(p):
                self.add_media(p)

    def _add_music_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Add music", MUSIC_DIR, f"Audio ({exts})", options=_DIALOG_OPTS)
        if path:
            self._play_music(path)

    def selected_media_path(self) -> Optional[str]:
        it = self.media_list.currentItem()
        return it.path if isinstance(it, MediaTile) else None

    def _preview_or_hint(self, item):
        if isinstance(item, MediaTile):
            target = next(
                (i for i in range(len(self.outputs)) if i != self._main_screen_idx), None)
            if target is not None:
                self.push_to_screen(target, item.path)

    # ── pushing media ─────────────────────────────────────────────────────────

    def _is_muted(self) -> bool:
        return self.mute_combo.currentIndex() == 1

    def push_to_screen(self, idx: int, path: str):
        if idx >= len(self.outputs) or idx == self._main_screen_idx:
            return
        self.outputs[idx].display(path, mute=self._is_muted())
        self.live_assignments[idx] = path
        self.screen_cards[idx].update_current(path)
        thumb = self.outputs[idx].get_thumbnail()
        if thumb:
            self.screen_cards[idx].set_preview(thumb)
        else:
            QTimer.singleShot(700, lambda i=idx: self._refresh_thumb(i))

    def _refresh_thumb(self, idx: int):
        if idx < len(self.outputs) and idx < len(self.screen_cards):
            thumb = self.outputs[idx].get_thumbnail()
            if thumb:
                self.screen_cards[idx].set_preview(thumb)

    def _refresh_all_thumbs(self):
        for i in range(len(self.outputs)):
            if i != self._main_screen_idx:
                self._refresh_thumb(i)

    def push_overlay_to_screen(self, idx: int, path: str):
        if idx >= len(self.outputs) or idx == self._main_screen_idx:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (IMAGE_EXT | GIF_EXT):
            QMessageBox.warning(self, "Overlay",
                                "Overlays must be image (.png/.jpg/…) or GIF files.")
            return
        self.outputs[idx].display_overlay(path)
        self.live_overlays[idx] = path
        self.screen_cards[idx].update_overlay_label(path)
        self._refresh_thumb(idx)

    def clear_overlay_screen(self, idx: int):
        if idx < len(self.outputs) and idx != self._main_screen_idx:
            self.outputs[idx].clear_overlay()
            self.live_overlays.pop(idx, None)
            self.screen_cards[idx].update_overlay_label(None)
            self._refresh_thumb(idx)

    def clear_screen(self, idx: int):
        if idx < len(self.outputs) and idx != self._main_screen_idx:
            self.outputs[idx].show_blank()
            self.live_assignments.pop(idx, None)
            self.live_overlays.pop(idx, None)
            self.screen_cards[idx].update_current(None)
            self.screen_cards[idx].update_overlay_label(None)
            self.screen_cards[idx].set_preview(None)

    def blank_all(self):
        for i in range(len(self.outputs)):
            self.clear_screen(i)

    # ── scenes ────────────────────────────────────────────────────────────────

    def _save_scene(self):
        if not self.live_assignments:
            QMessageBox.information(self, "Nothing to save",
                                    "Put something on a screen first.")
            return
        name, ok = QInputDialog.getText(self, "Save scene", "Scene name:")
        if not ok or not name.strip():
            return
        assignments   = {}
        rotations     = {}
        fill_modes    = {}
        grid_settings = {}
        placed_assets = {}
        for k, bg in self.live_assignments.items():
            ov = self.live_overlays.get(k, "")
            assignments[str(k)] = [bg, ov] if ov else [bg]
            if k < len(self.outputs):
                rotations[str(k)]  = self.outputs[k].rotation
                fill_modes[str(k)] = self.outputs[k].fill_mode
            gs = self.live_grid_settings.get(k)
            if gs:
                grid_settings[str(k)] = gs
            pa_list = self.live_placed_assets.get(k, [])
            if pa_list:
                placed_assets[str(k)] = [asdict(pa) for pa in pa_list
                                          if isinstance(pa, PlacedAsset)]
        self.scenes.append(Scene(
            name=name.strip(), assignments=assignments,
            rotations=rotations, fill_modes=fill_modes,
            grid_settings=grid_settings, placed_assets=placed_assets))
        self._refresh_scene_list()
        self._save_scenes()

    def _edit_scene(self):
        row = self.scene_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Edit scene", "Select a scene first.")
            return
        dlg = SceneEditorDialog(self.scenes[row], len(self.outputs), parent=self)
        dlg.setStyleSheet("")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to_scene()
            self._refresh_scene_list()
            self._save_scenes()
            scene = self.scenes[row]
            for layers in scene.assignments.values():
                for p in (layers if isinstance(layers, list) else [layers]):
                    if p and os.path.exists(p):
                        self.add_media(p)

    def _delete_scene(self):
        row = self.scene_list.currentRow()
        if row < 0:
            return
        del self.scenes[row]
        self._refresh_scene_list()
        self._save_scenes()

    def _refresh_scene_list(self):
        self.scene_list.clear()
        for s in self.scenes:
            music_tag = " ♪" if s.music_path else ""
            self.scene_list.addItem(
                f"{s.name}  ({len(s.assignments)} screens){music_tag}")

    def _activate_scene_item(self, item):
        self._activate_scene(self.scene_list.row(item))

    def _activate_scene(self, row: int):
        if row < 0 or row >= len(self.scenes):
            return
        screens_to_fade = [i for i in range(len(self.outputs))
                           if i != self._main_screen_idx]
        if screens_to_fade:
            pending = [len(screens_to_fade)]
            def on_all_faded():
                self._do_activate_scene(row)
                for i in screens_to_fade:
                    self.outputs[i].fade_from_black(TRANSITION_MS)
            def make_cb():
                def cb():
                    pending[0] -= 1
                    if pending[0] == 0:
                        on_all_faded()
                return cb
            for i in screens_to_fade:
                self.outputs[i].fade_to_black(TRANSITION_MS, make_cb())
        else:
            self._do_activate_scene(row)

    def _do_activate_scene(self, row: int):
        scene = self.scenes[row]
        used  = set()
        for k, layers in scene.assignments.items():
            idx  = int(k)
            used.add(idx)
            ls   = layers if isinstance(layers, list) else [layers]
            bg   = ls[0] if len(ls) > 0 else ""
            ov   = ls[1] if len(ls) > 1 else ""

            rot  = scene.rotations.get(k, 0)
            fill = scene.fill_modes.get(k, False)
            if idx < len(self.outputs):
                self.outputs[idx].set_rotation(rot)
                self.outputs[idx].set_fill_mode(fill)
            if idx < len(self.screen_cards):
                card = self.screen_cards[idx]
                card.rot_combo.blockSignals(True)
                card.rot_combo.setCurrentIndex(
                    [0, 90, 180, 270].index(rot) if rot in [0, 90, 180, 270] else 0)
                card.rot_combo.blockSignals(False)
                card.fill_combo.blockSignals(True)
                card.fill_combo.setCurrentIndex(1 if fill else 0)
                card.fill_combo.blockSignals(False)

            if bg:
                self.push_to_screen(idx, bg)
            if ov:
                self.push_overlay_to_screen(idx, ov)
            elif idx in self.live_overlays:
                self.clear_overlay_screen(idx)

            # Apply grid settings for this screen
            gs = dict(scene.grid_settings.get(k, {}))
            sz = self.screen_sizes.get(k, {})
            if sz:
                if not gs.get("screen_w_in"):
                    gs["screen_w_in"] = sz.get("w", 0.0)
                if not gs.get("screen_h_in"):
                    gs["screen_h_in"] = sz.get("h", 0.0)
            self.live_grid_settings[idx] = gs
            if idx < len(self.outputs):
                self.outputs[idx].apply_grid(gs)
            if idx < len(self.screen_cards):
                self.screen_cards[idx].update_grid_ui(gs, sz)

            # Restore placed assets for this screen
            pa_dicts = scene.placed_assets.get(k, [])
            pa_list  = []
            for pa_d in pa_dicts:
                try:
                    pa_list.append(PlacedAsset(**{
                        kk: vv for kk, vv in pa_d.items()
                        if kk in ("asset_path", "x", "y", "w", "h",
                                  "locked", "visible", "sound_path")}))
                except Exception:
                    pass
            self.live_placed_assets[idx] = pa_list
            if idx < len(self.outputs):
                self.outputs[idx].set_placed_assets(pa_list)

        for i in range(len(self.outputs)):
            if i not in used:
                self.clear_screen(i)
                if i < len(self.outputs):
                    self.outputs[i].clear_grid()
                    self.outputs[i].set_placed_assets([])
                self.live_grid_settings.pop(i, None)
                self.live_placed_assets[i] = []
                if i < len(self.screen_cards):
                    self.screen_cards[i].update_grid_ui({})

        self.scene_list.setCurrentRow(row)
        if scene.music_path and os.path.exists(scene.music_path):
            self._play_music_with_fade(scene.music_path)
        QTimer.singleShot(500, self._refresh_all_thumbs)
        QTimer.singleShot(1200, self._refresh_all_thumbs)

    def _step_scene(self, direction: int):
        if not self.scenes:
            return
        cur = self.scene_list.currentRow()
        nxt = max(0, min(len(self.scenes) - 1, cur + direction)) if cur >= 0 else 0
        self._activate_scene(nxt)

    # ── persistence ───────────────────────────────────────────────────────────

    def _save_scenes(self):
        try:
            data = {
                "screen_sizes":   self.screen_sizes,
                "main_screen_idx": self._main_screen_idx,
                "asset_library":  [asdict(a) for a in self.asset_library],
                "scenes":         [asdict(s) for s in self.scenes],
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Could not save scenes:", e)

    def _load_scenes(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE) as f:
                raw = json.load(f)

            # Support both old list format and new dict format
            if isinstance(raw, list):
                data_list = raw
                self.screen_sizes = {}
            else:
                data_list = raw.get("scenes", [])
                self.screen_sizes = raw.get("screen_sizes", {})
                saved_main = raw.get("main_screen_idx", self._main_screen_idx)
                if isinstance(saved_main, int) and saved_main < len(self.outputs):
                    if saved_main != self._main_screen_idx:
                        old_main = self._main_screen_idx
                        self._main_screen_idx = saved_main
                        self.main_screen_combo.blockSignals(True)
                        self.main_screen_combo.setCurrentIndex(saved_main)
                        self.main_screen_combo.blockSignals(False)
                        for i, card in enumerate(self.screen_cards):
                            card.set_is_main(i == saved_main)
                        # Place the previously-skipped old main screen as an output
                        if old_main < len(self.outputs):
                            self.outputs[old_main].place_on_screen()
                        # Hide the new main screen's output window
                        self.outputs[saved_main].hide()
                        self._move_control_to_screen(saved_main)

            # Restore asset library
            self.asset_library = []
            for a in raw.get("asset_library", []):
                try:
                    ai = AssetItem(**{k: v for k, v in a.items()
                                      if k in ("path", "size_w", "size_h",
                                               "sound_path", "effect")})
                    if os.path.exists(ai.path):
                        self.asset_library.append(ai)
                except Exception:
                    pass

            # Populate screen size spinboxes from saved global sizes
            for k, sz in self.screen_sizes.items():
                idx = int(k)
                if idx < len(self.screen_cards):
                    card = self.screen_cards[idx]
                    card._grid_w_spin.blockSignals(True)
                    card._grid_w_spin.setValue(sz.get("w", 27.0))
                    card._grid_w_spin.blockSignals(False)
                    card._grid_h_spin.blockSignals(True)
                    card._grid_h_spin.setValue(sz.get("h", 15.0))
                    card._grid_h_spin.blockSignals(False)

            self.scenes = []
            for d in data_list:
                assignments = d.get("assignments", {})
                for k, v in assignments.items():
                    if isinstance(v, str):
                        assignments[k] = [v]
                d["assignments"] = assignments
                if "music_path"    not in d: d["music_path"]    = None
                if "rotations"     not in d: d["rotations"]     = {}
                if "fill_modes"    not in d: d["fill_modes"]    = {}
                if "grid_settings" not in d: d["grid_settings"] = {}
                if "placed_assets" not in d: d["placed_assets"] = {}
                self.scenes.append(Scene(**d))
            for s in self.scenes:
                for layers in s.assignments.values():
                    for p in (layers if isinstance(layers, list) else [layers]):
                        if p and os.path.exists(p):
                            self.add_media(p)
            self._refresh_scene_list()
        except Exception as e:
            print("Could not load scenes:", e)

    # ── keyboard shortcuts ────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right:
            self._step_scene(1)
        elif event.key() == Qt.Key.Key_Left:
            self._step_scene(-1)
        elif event.key() == Qt.Key.Key_B:
            self.blank_all()
        else:
            super().keyPressEvent(event)

    def _confirm_exit(self):
        box = QMessageBox(self)
        box.setWindowTitle("Exit SceneCaster")
        box.setText("Close SceneCaster and all output screens?")
        box.setIcon(QMessageBox.Icon.Question)
        exit_b   = box.addButton("⏻  Exit", QMessageBox.ButtonRole.AcceptRole)
        cancel_b = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        # Big tap targets for the touch panel
        for b in (exit_b, cancel_b):
            if b:
                b.setMinimumSize(px(160), px(80))
        box.setDefaultButton(cancel_b)
        box.exec()
        if box.clickedButton() is exit_b:
            self.close()

    def closeEvent(self, event):
        for w in self.outputs:
            w.close()
        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SceneCaster")
    global UI_SCALE, THUMB_W, THUMB_H, FONT_SERIF, FONT_BODY
    UI_SCALE = _compute_ui_scale()
    THUMB_W = px(240)
    THUMB_H = px(135)
    FONT_SERIF = _resolve_serif_family()
    FONT_BODY  = _resolve_body_family()
    win = ControlWindow()
    win.showMaximized()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
