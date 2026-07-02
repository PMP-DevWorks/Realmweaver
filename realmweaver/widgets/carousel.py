"""Time Machine-style scene carousel: stacked scene previews receding into
depth; scroll / drag to flip through, tap the front scene to activate it."""

import os

from PyQt6.QtCore import Qt, QVariantAnimation, QEasingCurve, QPointF, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsDropShadowEffect, QFrame,
)

from realmweaver import theme
from realmweaver.theme import (
    px, pt, C_VOID, C_PANEL, C_CARD, C_BORDER_GOLD, C_ACCENT_GOLD,
    C_ACCENT_PURPLE, C_TEXT_PARCH, C_TEXT_RUNE,
)

MAX_VISIBLE = 6          # scenes shown behind the focused one
SCALE_STEP  = 0.88       # size falloff per depth step
FADE_STEP   = 0.16       # opacity falloff per depth step


def _placeholder_pixmap(name: str, w: int, h: int) -> QPixmap:
    pix = QPixmap(w, h)
    pix.fill(QColor(C_CARD))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(C_BORDER_GOLD), 2))
    p.drawRect(1, 1, w - 2, h - 2)
    f = QFont(theme.FONT_SERIF)
    f.setPointSize(pt(12))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(C_TEXT_PARCH))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, name)
    p.end()
    return pix


class SceneCarouselView(QGraphicsView):
    scene_chosen = pyqtSignal(int)   # index into the scene list

    def __init__(self, scenes: list, thumbs: list, parent=None):
        super().__init__(parent)
        self._scenes = scenes
        self._focus = 0.0
        self._anim = None
        self._drag_start_y = None
        self._drag_start_focus = 0.0
        self._dragged = False

        self._gscene = QGraphicsScene(self)
        self.setScene(self._gscene)
        self.setStyleSheet(f"background:{C_VOID}; border:none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(QFrame.Shape.NoFrame)

        card_w = px(560)
        card_h = int(card_w * 9 / 16)
        self._card_w, self._card_h = card_w, card_h
        self._items: list[QGraphicsPixmapItem] = []
        for i, scene in enumerate(scenes):
            pix = thumbs[i]
            if pix is None or pix.isNull():
                pix = _placeholder_pixmap(scene.name, card_w, card_h)
            else:
                pix = pix.scaled(card_w, card_h,
                                 Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
            item = QGraphicsPixmapItem(pix)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            item.setOffset(-pix.width() / 2, -pix.height() / 2)
            self._gscene.addItem(item)
            self._items.append(item)

        # Qt owns and deletes an installed QGraphicsEffect when it is replaced
        # or cleared, so the glow is re-created whenever the front item changes.
        self._front_item = None

        self._name_lbl = QLabel(self)
        self._name_lbl.setStyleSheet(
            f'background:transparent; color:{C_ACCENT_GOLD}; '
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(16)}pt; font-weight:700;')
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._apply_focus()

    # ── layout ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setSceneRect(0, 0, self.viewport().width(), self.viewport().height())
        self._apply_focus()

    def _apply_focus(self):
        W = self.viewport().width() or 800
        H = self.viewport().height() or 600
        cx = W / 2
        base_y = H * 0.62
        step_y = px(64)
        front = None
        front_d = 1e9
        for i, item in enumerate(self._items):
            d = i - self._focus
            if d < -0.6 or d > MAX_VISIBLE:
                item.setVisible(False)
                continue
            item.setVisible(True)
            scale = SCALE_STEP ** max(0.0, d)
            if d < 0:   # scene sliding off the front
                scale *= 1 + (-d) * 0.35
            item.setScale(scale)
            item.setPos(QPointF(cx, base_y - max(0.0, d) * step_y))
            item.setZValue(1000 - d)
            item.setOpacity(max(0.05, 1.0 - FADE_STEP * max(0.0, d))
                            if d >= 0 else max(0.0, 1.0 + d * 1.4))
            if abs(d) < front_d:
                front_d = abs(d)
                front = item

        if front is not self._front_item:
            if self._front_item is not None:
                self._front_item.setGraphicsEffect(None)
            if front is not None:
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(px(30))
                shadow.setColor(QColor(C_ACCENT_PURPLE))
                shadow.setOffset(0, 0)
                front.setGraphicsEffect(shadow)
            self._front_item = front

        idx = round(self._focus)
        if 0 <= idx < len(self._scenes):
            self._name_lbl.setText(self._scenes[idx].name)
        self._name_lbl.setGeometry(0, int(H * 0.82), W, px(48))

    # ── navigation ────────────────────────────────────────────────────────────

    def _animate_to(self, target: float):
        target = max(0.0, min(len(self._items) - 1.0, target))
        if self._anim:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self._focus))
        anim.setEndValue(float(target))
        anim.setDuration(260)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_anim)
        anim.start()
        self._anim = anim

    def _on_anim(self, value):
        self._focus = float(value)
        self._apply_focus()

    def step(self, direction: int):
        self._animate_to(round(self._focus) + direction)

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if steps:
            self.step(1 if steps > 0 else -1)
        event.accept()

    def mousePressEvent(self, event):
        self._drag_start_y = event.position().y()
        self._drag_start_focus = self._focus
        self._dragged = False
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_start_y is None:
            return
        dy = event.position().y() - self._drag_start_y
        if abs(dy) > px(8):
            self._dragged = True
        if self._anim:
            self._anim.stop()
        # dragging down pulls earlier scenes forward
        self._focus = max(0.0, min(len(self._items) - 1.0,
                                   self._drag_start_focus + dy / px(90)))
        self._apply_focus()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_start_y is None:
            return
        if self._dragged:
            self._animate_to(round(self._focus))
        else:
            self.scene_chosen.emit(int(round(self._focus)))
        self._drag_start_y = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Right):
            self.step(1)
        elif event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Left):
            self.step(-1)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.scene_chosen.emit(int(round(self._focus)))
        else:
            super().keyPressEvent(event)


class SceneCarouselDialog(QDialog):
    """Full-screen overlay hosting the carousel. Emits nothing; calls the
    controller's _activate_scene when a scene is chosen."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Browse Scenes")
        self.setStyleSheet(f"QDialog {{ background:{C_VOID}; }}")

        thumbs = [controller.scene_thumbnail(s) for s in controller.scenes]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(10), px(10), px(10), px(10))
        lay.setSpacing(px(6))

        top = QHBoxLayout()
        title = QLabel("SCENES")
        title.setStyleSheet(
            f'color:{C_ACCENT_GOLD}; font-family:"{theme.FONT_SERIF}"; '
            f"font-size:{pt(13)}pt; letter-spacing:4px; font-weight:700;")
        hint = QLabel("Swipe / scroll to travel • Tap the front scene to go there")
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        close_b = QPushButton("✕ Close")
        close_b.setMinimumSize(px(120), px(64))
        close_b.clicked.connect(self.reject)
        top.addWidget(title)
        top.addSpacing(px(16))
        top.addWidget(hint)
        top.addStretch(1)
        top.addWidget(close_b)
        lay.addLayout(top)

        self.view = SceneCarouselView(controller.scenes, thumbs, parent=self)
        self.view.scene_chosen.connect(self._on_chosen)
        lay.addWidget(self.view, 1)

        cur = controller.scene_list.currentRow()
        if cur > 0:
            self.view._focus = float(cur)
            self.view._apply_focus()

        self.showMaximized()

    def _on_chosen(self, idx: int):
        self.accept()
        self.controller._activate_scene(idx)
