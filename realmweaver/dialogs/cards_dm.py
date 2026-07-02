"""DM-side card management: library dialog + card editor with rich-text body."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCharFormat
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QCheckBox, QPushButton, QTextEdit, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QSplitter, QWidget, QFrame,
)

from realmweaver import theme
from realmweaver.theme import (
    px, pt, _touch_scroll, make_accent, make_danger,
    IMAGE_EXT, MEDIA_DIR, _DIALOG_OPTS,
    C_VOID, C_CARD, C_ACCENT_GOLD, C_TEXT_PARCH, C_TEXT_AGED, C_TEXT_RUNE,
)
from realmweaver.models import Card, ROLE_PLAYER_MAP
from realmweaver.widgets.cards import CardWidget

RARITIES = ["common", "uncommon", "rare", "legendary"]
KINDS    = ["item", "npc", "handout"]


class CardEditorDialog(QDialog):
    def __init__(self, card: Card, parent=None):
        super().__init__(parent)
        self.card = card
        self.setWindowTitle(f"Edit Card: {card.name}" if card.name else "New Card")
        self.setMinimumSize(px(520), px(520))
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(px(8))
        lay.setContentsMargins(px(16), px(16), px(16), px(16))

        def row(label):
            r = QHBoxLayout()
            l = QLabel(label)
            l.setMinimumWidth(px(100))
            l.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(10)}pt;")
            r.addWidget(l)
            lay.addLayout(r)
            return r

        r = row("Name:")
        self._name = QLineEdit(self.card.name)
        r.addWidget(self._name, 1)

        r = row("Kind / Rarity:")
        self._kind = QComboBox(); self._kind.addItems([k.capitalize() for k in KINDS])
        self._kind.setCurrentIndex(KINDS.index(self.card.kind) if self.card.kind in KINDS else 0)
        self._rarity = QComboBox(); self._rarity.addItems([x.capitalize() for x in RARITIES])
        self._rarity.setCurrentIndex(RARITIES.index(self.card.rarity) if self.card.rarity in RARITIES else 0)
        r.addWidget(self._kind, 1)
        r.addWidget(self._rarity, 1)

        r = row("Charges:")
        self._has_charges = QCheckBox("Track charges")
        self._has_charges.setChecked(self.card.charges is not None)
        self._charges = QSpinBox()
        self._charges.setRange(0, 99)
        self._charges.setValue(self.card.charges or 0)
        self._charges.setEnabled(self.card.charges is not None)
        self._has_charges.toggled.connect(self._charges.setEnabled)
        r.addWidget(self._has_charges)
        r.addWidget(self._charges, 1)

        r = row("Tags:")
        self._tags = QLineEdit(", ".join(self.card.tags))
        self._tags.setPlaceholderText("sword, artifact, act iii")
        r.addWidget(self._tags, 1)

        r = row("Portrait:")
        self._portrait = QLineEdit(os.path.basename(self.card.portrait_path or ""))
        self._portrait.setReadOnly(True)
        self._portrait.setToolTip(self.card.portrait_path or "")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_portrait)
        clear = QPushButton("✕")
        clear.setMinimumWidth(px(48))
        clear.clicked.connect(self._clear_portrait)
        r.addWidget(self._portrait, 1)
        r.addWidget(browse)
        r.addWidget(clear)

        # Rich-text body with a minimal formatting toolbar
        bar = QHBoxLayout()
        for text, cb in (("B", self._bold), ("I", self._italic), ("H", self._heading)):
            b = QPushButton(text)
            b.setFixedSize(px(56), px(56))
            b.clicked.connect(cb)
            bar.addWidget(b)
        hint = QLabel("Stat block — select text then B / I / H")
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(8)}pt;")
        bar.addWidget(hint)
        bar.addStretch(1)
        lay.addLayout(bar)

        self._body = QTextEdit()
        self._body.setAcceptRichText(True)
        self._body.setHtml(self.card.body_html)
        _touch_scroll(self._body)
        lay.addWidget(self._body, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _merge_fmt(self, fmt: QTextCharFormat):
        cur = self._body.textCursor()
        if cur.hasSelection():
            cur.mergeCharFormat(fmt)
        self._body.mergeCurrentCharFormat(fmt)

    def _bold(self):
        fmt = QTextCharFormat()
        is_bold = self._body.currentCharFormat().fontWeight() > QFont.Weight.Normal
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self._merge_fmt(fmt)

    def _italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._body.currentCharFormat().fontItalic())
        self._merge_fmt(fmt)

    def _heading(self):
        fmt = QTextCharFormat()
        big = self._body.currentCharFormat().fontPointSize() > pt(10)
        fmt.setFontPointSize(pt(9) if big else pt(13))
        fmt.setFontWeight(QFont.Weight.Normal if big else QFont.Weight.Bold)
        self._merge_fmt(fmt)

    def _browse_portrait(self):
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXT))
        path, _ = QFileDialog.getOpenFileName(
            self, "Card portrait", MEDIA_DIR, f"Images ({exts})", options=_DIALOG_OPTS)
        if path:
            self.card.portrait_path = path
            self._portrait.setText(os.path.basename(path))
            self._portrait.setToolTip(path)

    def _clear_portrait(self):
        self.card.portrait_path = None
        self._portrait.setText("")
        self._portrait.setToolTip("")

    def _on_accept(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Card", "Give the card a name.")
            return
        self.card.name = name
        self.card.kind = KINDS[self._kind.currentIndex()]
        self.card.rarity = RARITIES[self._rarity.currentIndex()]
        self.card.charges = self._charges.value() if self._has_charges.isChecked() else None
        self.card.tags = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        self.card.body_html = self._body.toHtml()
        self.accept()


class CardLibraryDialog(QDialog):
    """Browse/manage the card library and push cards to screens."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Card Library")
        self.setMinimumSize(px(760), px(560))
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(px(8))
        lay.setContentsMargins(px(16), px(16), px(16), px(16))

        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        _touch_scroll(self._list)
        ll.addWidget(self._list, 1)

        row1 = QHBoxLayout()
        new_b = QPushButton("+ New")
        make_accent(new_b)
        new_b.clicked.connect(self._new_card)
        edit_b = QPushButton("Edit…")
        edit_b.clicked.connect(self._edit_card)
        del_b = QPushButton("Delete")
        make_danger(del_b)
        del_b.clicked.connect(self._delete_card)
        for b in (new_b, edit_b, del_b):
            row1.addWidget(b)
        ll.addLayout(row1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self._preview_holder = QVBoxLayout()
        rl.addLayout(self._preview_holder, 1)

        push_row = QHBoxLayout()
        to_table = QPushButton("▶ Add to card dock")
        make_accent(to_table)
        to_table.clicked.connect(self._push_to_table)
        self._screen_combo = QComboBox()
        for i in range(len(self.controller.outputs)):
            if i != self.controller._main_screen_idx:
                self._screen_combo.addItem(f"Screen {i + 1}", i)
        to_screen = QPushButton("▶ Show on screen")
        to_screen.clicked.connect(self._push_to_screen)
        clear_screen = QPushButton("Clear screen")
        clear_screen.clicked.connect(self._clear_screen)
        push_row.addWidget(to_table)
        push_row.addWidget(self._screen_combo)
        push_row.addWidget(to_screen)
        push_row.addWidget(clear_screen)
        rl.addLayout(push_row)
        split.addWidget(right)
        split.setSizes([px(280), px(460)])
        lay.addWidget(split, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.clicked.connect(self.accept)
        lay.addWidget(btns)

        self._preview_widget = None

    def _refresh(self, select_row: int = -1):
        self._list.clear()
        for c in self.controller.cards:
            tag = {"item": "⚔", "npc": "☺", "handout": "✉"}.get(c.kind, "•")
            self._list.addItem(f"{tag}  {c.name}   [{c.rarity}]")
        if 0 <= select_row < self._list.count():
            self._list.setCurrentRow(select_row)

    def _current(self):
        row = self._list.currentRow()
        if 0 <= row < len(self.controller.cards):
            return self.controller.cards[row]
        return None

    def _on_select(self, row: int):
        if self._preview_widget:
            self._preview_holder.removeWidget(self._preview_widget)
            self._preview_widget.deleteLater()
            self._preview_widget = None
        card = self._current()
        if card:
            self._preview_widget = CardWidget(card)
            self._preview_holder.addWidget(self._preview_widget)

    def _new_card(self):
        card = Card(name="")
        dlg = CardEditorDialog(card, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.controller.cards.append(card)
            self.controller._save_scenes()
            self._refresh(len(self.controller.cards) - 1)

    def _edit_card(self):
        card = self._current()
        if not card:
            return
        row = self._list.currentRow()
        dlg = CardEditorDialog(card, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.controller._save_scenes()
            self._refresh(row)

    def _delete_card(self):
        card = self._current()
        if not card:
            return
        reply = QMessageBox.question(
            self, "Delete Card", f'Delete "{card.name}" from the library?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.controller.cards = [c for c in self.controller.cards if c is not card]
        for s in self.controller.scenes:
            s.card_ids = [cid for cid in s.card_ids if cid != card.id]
        self.controller._save_scenes()
        self._refresh()

    def _push_to_table(self):
        card = self._current()
        if card:
            self.controller.push_card_to_table(card)

    def _chosen_screen(self):
        return self._screen_combo.currentData()

    def _push_to_screen(self):
        card = self._current()
        idx = self._chosen_screen()
        if card is not None and idx is not None:
            self.controller.push_cards_to_screen(idx, [card])

    def _clear_screen(self):
        idx = self._chosen_screen()
        if idx is not None:
            self.controller.push_cards_to_screen(idx, [])
