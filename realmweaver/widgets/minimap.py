"""Mini-map prop placement canvas and dialog."""
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

from realmweaver.models import PlacedAsset
from realmweaver.output.output_window import OutputWindow
from realmweaver.widgets.panels import AssetLibraryPanel, PlacedAssetItem

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
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(14)}pt; font-weight:700; color:{C_ACCENT_GOLD};')
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
        make_accent(save_btn)
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

