"""Media helpers: kind detection, library tiles, preview file dialog."""
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

def media_kind(path: str) -> Optional[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT: return "image"
    if ext in GIF_EXT:   return "gif"
    if ext in VIDEO_EXT: return "video"
    return None
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
        f = QFont(theme.FONT_BODY)
        f.setPointSize(pt(8))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, tag)
        p.end()
        return QIcon(pix)
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
