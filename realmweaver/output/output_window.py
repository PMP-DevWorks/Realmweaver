"""Per-monitor fullscreen output: background, grid, placed assets, zoom."""
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

from realmweaver import theme
from realmweaver.theme import (
    px, pt, _touch_scroll, make_accent, make_danger,
    IMAGE_EXT, GIF_EXT, VIDEO_EXT, AUDIO_EXT, ALL_EXT,
    APP_DIR, DATA_DIR, MEDIA_DIR, VIDEOS_DIR, GIFS_DIR, IMAGES_DIR,
    ASSETS_DIR, MUSIC_DIR, CONFIG_FILE, TRANSITION_MS, MUSIC_FADE_MS,
    _DIALOG_OPTS,
    C_VOID, C_PANEL, C_CARD, C_INPUT, C_HOVER, C_ACCENT_GOLD,
    C_ACCENT_PURPLE, C_GLOW_PURPLE, C_GOLD_DIM, C_BORDER, C_BORDER_GOLD,
    C_TEXT_PARCH, C_TEXT_AGED, C_TEXT_RUNE, C_DANGER,
)

from realmweaver.media import media_kind
from realmweaver.models import PlacedAsset
from realmweaver.widgets.cards import PlayerInfoView
from realmweaver.widgets.tabletop import TabletopLayout

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

        # card/handout page — shown only when the DM explicitly pushes cards
        # to this screen; clear_cards() returns to the media page untouched
        self.info_view = PlayerInfoView()
        self.stack.addWidget(self.info_view)

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

        # lighting tint overlay (below grid/fade, above content)
        self._light_overlay = QWidget(self)
        self._light_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._light_overlay.setVisible(False)

        # tabletop HUD (plates, notes, card dock, soundtrack pill)
        self.tabletop = TabletopLayout(self)

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

    # ── card page (explicit push / clear, never automatic) ───────────────────

    def show_cards(self, cards: list):
        """Cover this screen with the given cards. The underlying media keeps
        playing; clear_cards() uncovers it exactly as it was."""
        self.info_view.show_cards(cards)
        self.stack.setCurrentWidget(self.info_view)

    def clear_cards(self):
        """Remove pushed cards and return to whatever media page was active."""
        self.info_view.clear()
        if self.stack.currentWidget() is self.info_view:
            if self.current_kind == "video":
                self.stack.setCurrentWidget(self.gfx_view)
            else:
                self.stack.setCurrentWidget(self.image_label)

    def has_cards(self) -> bool:
        return bool(self.info_view._card_widgets)

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

    # ── lighting tint ─────────────────────────────────────────────────────────

    def set_lighting(self, lighting):
        """Apply a translucent colored tint over the scene (or None to clear)."""
        if not lighting or not lighting.get("tint"):
            self._light_overlay.setVisible(False)
            return
        color = QColor(lighting.get("tint", "#000000"))
        opacity = max(0.0, min(1.0, float(lighting.get("opacity", 0.3))))
        color.setAlphaF(opacity)
        self._light_overlay.setStyleSheet(
            f"background: rgba({color.red()},{color.green()},{color.blue()},{color.alpha()});")
        self._light_overlay.resize(self.size())
        self._light_overlay.setVisible(True)
        self._light_overlay.raise_()
        self._grid_overlay.raise_()
        self._fade_widget.raise_()

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
        self._light_overlay.resize(self.size())
        self.tabletop.relayout()
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
                theme.THUMB_W, theme.THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        return None
