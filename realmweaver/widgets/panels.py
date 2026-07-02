"""Asset library, placed-asset props, screen cards."""
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

from realmweaver.media import media_kind, _pick_media_files
from realmweaver.models import AssetItem, PlacedAsset

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
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(13)}pt; font-weight:700; color:{C_ACCENT_GOLD};')
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
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(13)}pt; font-weight:700; color:{C_ACCENT_GOLD};')
        lay.addWidget(hdr)

        sub = QLabel("Slide to resize • Hold to set sound • Drag to place")
        sub.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        lay.addWidget(sub)

        add_btn = QPushButton("+ Add Assets")
        add_btn.setMinimumHeight(px(72))
        make_accent(add_btn)
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
        self.preview_label.setFixedSize(theme.THUMB_W, theme.THUMB_H)
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
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(13)}pt; font-weight:600; color:{C_TEXT_PARCH};')
        lay.addWidget(title)

        self.main_badge = QLabel("(control screen — not blacked out)")
        self.main_badge.setStyleSheet(f"color:{C_ACCENT_GOLD}; font-size:{pt(9)}pt;")
        self.main_badge.setVisible(False)
        lay.addWidget(self.main_badge)

        # Per-screen switches — fully independent, nothing changes on its own.
        flags_row = QHBoxLayout()
        self.scenes_chk = QCheckBox("Show scenes")
        self.scenes_chk.setChecked(True)
        self.scenes_chk.setToolTip(
            "Off: scene changes leave this screen exactly as it is")
        self.scenes_chk.toggled.connect(self._on_scenes_toggled)
        self.hud_chk = QCheckBox("HUD")
        self.hud_chk.setChecked(False)
        self.hud_chk.setToolTip(
            "Player plates, notes/initiative, card dock on this screen")
        self.hud_chk.toggled.connect(self._on_hud_toggled)
        flags_row.addWidget(self.scenes_chk)
        flags_row.addWidget(self.hud_chk)
        flags_row.addStretch(1)
        lay.addLayout(flags_row)

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
                pix.scaled(theme.THUMB_W, theme.THUMB_H,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview_label.clear()

    def set_is_main(self, is_main: bool):
        self.main_badge.setVisible(is_main)
        for w in (self._assign_btn, self._clear_btn, self._ov_btn,
                  self._ov_clear, self.rot_combo, self.fill_combo,
                  self._grid_toggle, self._grid_type_combo, self._grid_cell_spin,
                  self._grid_color_btn, self._grid_w_spin, self._grid_h_spin,
                  self.scenes_chk, self.hud_chk):
            w.setEnabled(not is_main)

    def _on_scenes_toggled(self, checked: bool):
        self.controller.set_screen_flag(self.screen_index, "scenes", checked)

    def _on_hud_toggled(self, checked: bool):
        self.controller.set_screen_flag(self.screen_index, "hud", checked)

    def set_flags(self, scenes: bool, hud: bool):
        """Sync checkboxes from saved state without firing the handlers."""
        for chk, val in ((self.scenes_chk, scenes), (self.hud_chk, hud)):
            chk.blockSignals(True)
            chk.setChecked(val)
            chk.blockSignals(False)

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
        from realmweaver.widgets.minimap import MiniMapDialog
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
