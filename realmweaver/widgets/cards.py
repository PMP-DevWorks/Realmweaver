"""Card rendering: item / NPC / handout cards with portrait + rich stat block."""

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QScrollArea, QSizePolicy,
)

from realmweaver import theme
from realmweaver.theme import (
    px, pt, _touch_scroll,
    C_VOID, C_CARD, C_BORDER, C_BORDER_GOLD, C_ACCENT_GOLD, C_ACCENT_PURPLE,
    C_GLOW_PURPLE, C_TEXT_PARCH, C_TEXT_AGED, C_TEXT_RUNE,
)
from realmweaver.models import Card

RARITY_COLORS = {
    "common":    C_BORDER,
    "uncommon":  "#3fa15a",
    "rare":      C_ACCENT_PURPLE,
    "legendary": C_ACCENT_GOLD,
}


def rarity_color(rarity: str) -> str:
    return RARITY_COLORS.get((rarity or "common").lower(), C_BORDER)


def load_portrait(path, max_w: int, max_h: int):
    if not path or not os.path.exists(path):
        return None
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    pix = QPixmap.fromImage(reader.read())
    if pix.isNull():
        return None
    return pix.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


class CardWidget(QFrame):
    """One card: rarity-colored frame, portrait, name banner, stat block."""

    clicked = pyqtSignal(object)   # emits the Card

    def __init__(self, card: Card, compact: bool = False, parent=None):
        super().__init__(parent)
        self.card = card
        self._compact = compact
        self._build_ui()

    def _build_ui(self):
        color = rarity_color(self.card.rarity)
        self.setStyleSheet(
            f"CardWidget {{ background:{C_CARD}; border:2px solid {color}; "
            f"border-radius:{px(12)}px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(10), px(10), px(10), px(10))
        lay.setSpacing(px(6))

        port_h = px(120) if self._compact else px(320)
        pix = load_portrait(self.card.portrait_path, port_h * 2, port_h)
        if pix:
            img = QLabel()
            img.setPixmap(pix)
            img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img.setStyleSheet("border:none; background:transparent;")
            lay.addWidget(img)

        kind_lbl = QLabel(self.card.kind.upper())
        kind_lbl.setStyleSheet(
            f"border:none; background:transparent; color:{C_TEXT_RUNE}; "
            f"font-size:{pt(8)}pt; letter-spacing:3px;")
        kind_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(kind_lbl)

        name = QLabel(self.card.name)
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        name.setStyleSheet(
            f'border:none; background:transparent; font-family:"{theme.FONT_SERIF}"; '
            f"font-size:{pt(13 if not self._compact else 10)}pt; font-weight:700; "
            f"color:{C_ACCENT_GOLD};")
        lay.addWidget(name)

        if not self._compact and self.card.body_html:
            body = QTextBrowser()
            body.setHtml(self.card.body_html)
            body.setOpenExternalLinks(False)
            body.setStyleSheet(
                f"QTextBrowser {{ background:{C_VOID}; color:{C_TEXT_PARCH}; "
                f"border:1px solid {C_BORDER}; border-radius:{px(6)}px; "
                f"font-size:{pt(9)}pt; padding:{px(6)}px; }}")
            _touch_scroll(body)
            lay.addWidget(body, 1)

        meta_bits = []
        if self.card.rarity:
            meta_bits.append(self.card.rarity.capitalize())
        if self.card.charges is not None:
            meta_bits.append(f"{self.card.charges} charge(s)")
        if self.card.tags:
            meta_bits.append(" · ".join(self.card.tags))
        if meta_bits:
            meta = QLabel("  •  ".join(meta_bits))
            meta.setWordWrap(True)
            meta.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            meta.setStyleSheet(
                f"border:none; background:transparent; color:{C_TEXT_AGED}; "
                f"font-size:{pt(8)}pt;")
            lay.addWidget(meta)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.card)
        super().mousePressEvent(event)


class PlayerInfoView(QWidget):
    """Full-screen page shown on 'player_info' (and secondary DM) monitors:
    a void-black table surface displaying one or more cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C_VOID};")
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"background:{C_VOID}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        self._holder = QWidget()
        self._holder.setStyleSheet(f"background:{C_VOID};")
        self._row = QHBoxLayout(self._holder)
        self._row.setContentsMargins(px(24), px(24), px(24), px(24))
        self._row.setSpacing(px(24))
        self._row.addStretch(1)
        self._row.addStretch(1)
        self._scroll.setWidget(self._holder)
        self._card_widgets: list[CardWidget] = []

    def show_cards(self, cards: list):
        self.clear()
        for card in cards:
            w = CardWidget(card)
            w.setMaximumWidth(px(420))
            w.setSizePolicy(QSizePolicy.Policy.Preferred,
                            QSizePolicy.Policy.Expanding)
            # insert before the trailing stretch
            self._row.insertWidget(self._row.count() - 1, w)
            self._card_widgets.append(w)

    def clear(self):
        for w in self._card_widgets:
            self._row.removeWidget(w)
            w.deleteLater()
        self._card_widgets.clear()
