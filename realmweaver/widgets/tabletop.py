"""Tabletop HUD: player name plates, notes/initiative panel, card dock and
soundtrack pill overlaid on a Player Map output (matches the mockup layout)."""

import os

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QPushButton,
)

from realmweaver import theme
from realmweaver.theme import (
    px, pt, _touch_scroll,
    C_VOID, C_PANEL, C_CARD, C_BORDER, C_BORDER_GOLD, C_ACCENT_GOLD,
    C_ACCENT_PURPLE, C_GLOW_PURPLE, C_TEXT_PARCH, C_TEXT_AGED, C_TEXT_RUNE,
)
from realmweaver.models import PlayerPlate, InitiativeEntry, Card
from realmweaver.widgets.cards import CardWidget, load_portrait, rarity_color


class PlayerPlateWidget(QWidget):
    """Rounded name plate: small player name over large character name."""

    def __init__(self, plate: PlayerPlate, parent=None):
        super().__init__(parent)
        self.plate = plate
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def sizeHint(self):
        return QSize(px(180), px(52))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -2, -2)
        p.setBrush(QColor(10, 8, 20, 215))
        p.setPen(QPen(QColor(C_BORDER_GOLD), 2))
        radius = r.height() / 2
        p.drawRoundedRect(r, radius, radius)

        player_f = QFont(theme.FONT_BODY)
        player_f.setPointSize(pt(7))
        player_f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        p.setFont(player_f)
        p.setPen(QColor(C_TEXT_RUNE))
        top = r.adjusted(0, int(r.height() * 0.12), 0, 0)
        p.drawText(top, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   self.plate.player_name.upper())

        char_f = QFont(theme.FONT_SERIF)
        char_f.setPointSize(pt(11))
        char_f.setBold(True)
        p.setFont(char_f)
        p.setPen(QColor(C_TEXT_PARCH))
        bottom = r.adjusted(0, 0, 0, -int(r.height() * 0.10))
        p.drawText(bottom, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                   self.plate.character_name)
        p.end()


class SoundtrackIndicator(QFrame):
    """Round pill in the corner showing the current music track."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            f"QFrame {{ background:rgba(10,8,20,215); border:2px solid {C_BORDER_GOLD}; "
            f"border-radius:{px(16)}px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(14), px(8), px(14), px(8))
        lay.setSpacing(0)
        cap = QLabel("SOUNDTRACK")
        cap.setStyleSheet(
            f"border:none; background:transparent; color:{C_TEXT_RUNE}; "
            f"font-size:{pt(7)}pt; letter-spacing:3px;")
        cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._track = QLabel("—")
        self._track.setStyleSheet(
            f'border:none; background:transparent; color:{C_TEXT_PARCH}; '
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(10)}pt; font-weight:600;')
        self._track.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(cap)
        lay.addWidget(self._track)

    def set_track(self, path):
        if path:
            name = os.path.splitext(os.path.basename(path))[0]
            self._track.setText(name)
            self.setVisible(True)
        else:
            self.setVisible(False)


class NotesPanel(QFrame):
    """Right-side notes panel with initiative order, like the mockup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background:rgba(10,8,20,225); border:2px solid {C_BORDER}; "
            f"border-radius:{px(12)}px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(10), px(8), px(10), px(10))
        lay.setSpacing(px(4))
        hdr = QLabel("N O T E S")
        hdr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hdr.setStyleSheet(
            f"border:none; background:transparent; color:{C_TEXT_PARCH}; "
            f"font-size:{pt(10)}pt; letter-spacing:4px; font-weight:700;")
        lay.addWidget(hdr)
        self._body = QTextBrowser()
        self._body.setStyleSheet(
            f"QTextBrowser {{ background:{C_TEXT_PARCH}; color:#1a1410; "
            f"border:none; border-radius:{px(6)}px; font-size:{pt(9)}pt; "
            f"padding:{px(6)}px; }}")
        _touch_scroll(self._body)
        lay.addWidget(self._body, 1)
        self._notes_html = ""
        self._initiative: list[InitiativeEntry] = []

    def set_notes(self, html: str):
        self._notes_html = html or ""
        self._render()

    def set_initiative(self, entries: list):
        self._initiative = list(entries or [])
        self._render()

    def _render(self):
        parts = []
        if self._initiative:
            parts.append("<b>Initiative</b><br>")
            rows = []
            for e in self._initiative:
                row = f"{e.value} - {e.name}"
                if e.is_current:
                    row = f'<span style="background:#e8d48a;"><b>▶ {row}</b></span>'
                rows.append(row)
            parts.append("<br>".join(rows))
        if self._notes_html:
            if parts:
                parts.append("<hr>")
            parts.append(self._notes_html)
        self._body.setHtml("".join(parts))
        self.setVisible(bool(parts))


class CardDockBar(QFrame):
    """Bottom-corner dock of card thumbnails; tapping one opens the inspector."""

    card_tapped = pyqtSignal(object)

    THUMB = 96

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background:transparent; border:none; }")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(px(6))
        self._buttons: list[QPushButton] = []

    def set_cards(self, cards: list):
        for b in self._buttons:
            self._row.removeWidget(b)
            b.deleteLater()
        self._buttons.clear()
        for card in cards:
            b = QPushButton()
            b.setFixedSize(px(self.THUMB), int(px(self.THUMB) * 1.4))
            color = rarity_color(card.rarity)
            b.setStyleSheet(
                f"QPushButton {{ background:{C_CARD}; border:2px solid {color}; "
                f"border-radius:{px(8)}px; color:{C_TEXT_PARCH}; "
                f"font-size:{pt(7)}pt; }}"
                f"QPushButton:pressed {{ background:{C_ACCENT_PURPLE}; }}")
            pix = load_portrait(card.portrait_path,
                                px(self.THUMB) - 8, int(px(self.THUMB) * 1.4) - 8)
            if pix:
                from PyQt6.QtGui import QIcon
                b.setIcon(QIcon(pix))
                b.setIconSize(pix.size())
            else:
                b.setText(card.name)
            b.setToolTip(card.name)
            b.clicked.connect(lambda _, c=card: self.card_tapped.emit(c))
            self._row.addWidget(b)
            self._buttons.append(b)
        self.setVisible(bool(cards))

    def sizeHint(self):
        n = max(1, len(self._buttons))
        return QSize(n * (px(self.THUMB) + px(6)), int(px(self.THUMB) * 1.4))


class CardInspectorPanel(QFrame):
    """Enlarged card view opened from the dock; tap anywhere to dismiss."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background:rgba(0,0,0,140); border:none; }")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(px(40), px(40), px(40), px(40))
        self._card_widget = None
        self.hide()

    def show_card(self, card: Card):
        if self._card_widget:
            self._lay.removeWidget(self._card_widget)
            self._card_widget.deleteLater()
        self._card_widget = CardWidget(card)
        self._card_widget.setMaximumWidth(px(460))
        self._lay.addStretch(1)
        self._lay.addWidget(self._card_widget)
        self._lay.addStretch(1)
        self.show()
        self.raise_()

    def mousePressEvent(self, event):
        self.hide()
        event.accept()


class TabletopLayout:
    """Owns and positions the HUD widgets on an OutputWindow. Not itself a
    widget: children are parented straight onto the output so the map keeps
    receiving its own touch events between them."""

    def __init__(self, output):
        self._output = output
        self._plates: list[PlayerPlateWidget] = []
        self.soundtrack = SoundtrackIndicator(output)
        self.soundtrack.setVisible(False)
        self.notes = NotesPanel(output)
        self.notes.setVisible(False)
        self.dock = CardDockBar(output)
        self.dock.setVisible(False)
        self.inspector = CardInspectorPanel(output)
        self.dock.card_tapped.connect(self.inspector.show_card)
        self._enabled = False

    # ── content ───────────────────────────────────────────────────────────────

    def set_players(self, plates: list):
        for w in self._plates:
            w.deleteLater()
        self._plates = []
        for plate in plates:
            w = PlayerPlateWidget(plate, self._output)
            w.setVisible(self._enabled)
            self._plates.append(w)
        self.relayout()

    def set_notes(self, html: str):
        self.notes.set_notes(html)
        self._apply_visibility()

    def set_initiative(self, entries: list):
        self.notes.set_initiative(entries)
        self._apply_visibility()

    def set_cards(self, cards: list):
        self.dock.set_cards(cards)
        self._apply_visibility()

    def set_track(self, path):
        self.soundtrack.set_track(path)
        self._apply_visibility()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._apply_visibility()
        if enabled:
            self.relayout()

    def _apply_visibility(self):
        on = self._enabled
        for w in self._plates:
            w.setVisible(on)
        self.soundtrack.setVisible(on and self.soundtrack._track.text() not in ("", "—"))
        self.notes.setVisible(on and bool(self.notes._body.toPlainText().strip()))
        self.dock.setVisible(on and bool(self.dock._buttons))
        if not on:
            self.inspector.hide()

    # ── geometry ──────────────────────────────────────────────────────────────

    def relayout(self):
        W = self._output.width()
        H = self._output.height()
        if W <= 0 or H <= 0:
            return
        m = px(12)

        # Player plates distributed along their edges
        edges = {"top": [], "bottom": [], "left": [], "right": []}
        for w in self._plates:
            edges.setdefault(w.plate.edge, edges["bottom"]).append(w)
        pw, ph = px(200), px(56)
        for edge, ws in edges.items():
            n = len(ws)
            for i, w in enumerate(ws):
                frac = (i + 1) / (n + 1)
                if edge in ("top", "bottom"):
                    w.resize(pw, ph)
                    x = int(W * frac - pw / 2)
                    y = m if edge == "top" else H - ph - m
                    w.move(x, y)
                else:
                    w.resize(ph, pw)   # vertical plate: swap
                    y = int(H * frac - pw / 2)
                    x = m if edge == "left" else W - ph - m
                    w.move(x, y)
                w.raise_()

        # Soundtrack pill: top-left
        self.soundtrack.adjustSize()
        self.soundtrack.move(m, m)
        self.soundtrack.raise_()

        # Notes panel: top-right
        nw = min(px(260), max(px(180), W // 6))
        nh = min(px(420), H // 2)
        self.notes.resize(nw, nh)
        self.notes.move(W - nw - m, m)
        self.notes.raise_()

        # Card dock: bottom-left
        ds = self.dock.sizeHint()
        self.dock.resize(ds)
        self.dock.move(m, H - ds.height() - m)
        self.dock.raise_()

        # Inspector covers everything
        self.inspector.resize(W, H)
        if self.inspector.isVisible():
            self.inspector.raise_()
