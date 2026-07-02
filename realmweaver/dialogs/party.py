"""DM-side party management: player plates and initiative order."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QPushButton, QListWidget, QGroupBox, QMessageBox,
    QInputDialog, QWidget, QCheckBox,
)

from realmweaver.theme import (
    px, pt, _touch_scroll, make_accent, make_danger,
    C_TEXT_AGED, C_TEXT_RUNE, C_ACCENT_GOLD,
)
from realmweaver.models import PlayerPlate, InitiativeEntry

EDGES = ["top", "bottom", "left", "right"]


class PartyDialog(QDialog):
    """Edit player plates (shown around the map) and the initiative order."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Party & Initiative")
        self.setMinimumSize(px(640), px(560))
        self._build_ui()
        self._refresh_players()
        self._refresh_initiative()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(px(10))
        lay.setContentsMargins(px(16), px(16), px(16), px(16))

        # ── players ───────────────────────────────────────────────────────────
        pg = QGroupBox("Player Plates")
        pl = QVBoxLayout(pg)
        self._players = QListWidget()
        _touch_scroll(self._players)
        pl.addWidget(self._players, 1)
        prow = QHBoxLayout()
        add_p = QPushButton("+ Add player")
        make_accent(add_p)
        add_p.clicked.connect(self._add_player)
        edit_p = QPushButton("Edit…")
        edit_p.clicked.connect(self._edit_player)
        del_p = QPushButton("Remove")
        make_danger(del_p)
        del_p.clicked.connect(self._del_player)
        for b in (add_p, edit_p, del_p):
            prow.addWidget(b)
        pl.addLayout(prow)
        lay.addWidget(pg, 1)

        # ── initiative ────────────────────────────────────────────────────────
        ig = QGroupBox("Initiative Order")
        il = QVBoxLayout(ig)
        self._init_list = QListWidget()
        _touch_scroll(self._init_list)
        il.addWidget(self._init_list, 1)
        irow = QHBoxLayout()
        add_i = QPushButton("+ Add")
        make_accent(add_i)
        add_i.clicked.connect(self._add_init)
        cur_i = QPushButton("▶ Set current")
        cur_i.clicked.connect(self._set_current)
        next_i = QPushButton("Next turn")
        next_i.clicked.connect(self._next_turn)
        del_i = QPushButton("Remove")
        make_danger(del_i)
        del_i.clicked.connect(self._del_init)
        clear_i = QPushButton("Clear all")
        clear_i.clicked.connect(self._clear_init)
        for b in (add_i, cur_i, next_i, del_i, clear_i):
            irow.addWidget(b)
        il.addLayout(irow)
        lay.addWidget(ig, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.clicked.connect(self.accept)
        lay.addWidget(btns)

    # ── players ───────────────────────────────────────────────────────────────

    def _refresh_players(self):
        self._players.clear()
        for p in self.controller.players:
            self._players.addItem(f"{p.character_name}  ({p.player_name})  · {p.edge}")

    def _player_form(self, plate: PlayerPlate) -> bool:
        dlg = QDialog(self)
        dlg.setWindowTitle("Player Plate")
        dlg.setMinimumWidth(px(420))
        v = QVBoxLayout(dlg)

        def row(label, w):
            r = QHBoxLayout()
            l = QLabel(label)
            l.setMinimumWidth(px(120))
            l.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(10)}pt;")
            r.addWidget(l)
            r.addWidget(w, 1)
            v.addLayout(r)

        name = QLineEdit(plate.player_name)
        char = QLineEdit(plate.character_name)
        edge = QComboBox()
        edge.addItems([e.capitalize() for e in EDGES])
        edge.setCurrentIndex(EDGES.index(plate.edge) if plate.edge in EDGES else 1)
        row("Player name:", name)
        row("Character:", char)
        row("Table edge:", edge)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted and char.text().strip():
            plate.player_name = name.text().strip()
            plate.character_name = char.text().strip()
            plate.edge = EDGES[edge.currentIndex()]
            return True
        return False

    def _add_player(self):
        plate = PlayerPlate(player_name="", character_name="")
        if self._player_form(plate):
            self.controller.players.append(plate)
            self._commit()
            self._refresh_players()

    def _edit_player(self):
        row = self._players.currentRow()
        if 0 <= row < len(self.controller.players):
            if self._player_form(self.controller.players[row]):
                self._commit()
                self._refresh_players()

    def _del_player(self):
        row = self._players.currentRow()
        if 0 <= row < len(self.controller.players):
            del self.controller.players[row]
            self._commit()
            self._refresh_players()

    # ── initiative ────────────────────────────────────────────────────────────

    def _refresh_initiative(self):
        self._init_list.clear()
        for e in self.controller.initiative:
            mark = "▶ " if e.is_current else "   "
            self._init_list.addItem(f"{mark}{e.value} — {e.name}")

    def _add_init(self):
        name, ok = QInputDialog.getText(self, "Initiative", "Name:")
        if not ok or not name.strip():
            return
        val, ok = QInputDialog.getInt(self, "Initiative", "Initiative value:", 10, -20, 99)
        if not ok:
            return
        self.controller.initiative.append(InitiativeEntry(name=name.strip(), value=val))
        self.controller.initiative.sort(key=lambda e: -e.value)
        self._commit()
        self._refresh_initiative()

    def _set_current(self):
        row = self._init_list.currentRow()
        if 0 <= row < len(self.controller.initiative):
            for i, e in enumerate(self.controller.initiative):
                e.is_current = (i == row)
            self._commit()
            self._refresh_initiative()

    def _next_turn(self):
        ents = self.controller.initiative
        if not ents:
            return
        cur = next((i for i, e in enumerate(ents) if e.is_current), -1)
        for e in ents:
            e.is_current = False
        ents[(cur + 1) % len(ents)].is_current = True
        self._commit()
        self._refresh_initiative()

    def _del_init(self):
        row = self._init_list.currentRow()
        if 0 <= row < len(self.controller.initiative):
            del self.controller.initiative[row]
            self._commit()
            self._refresh_initiative()

    def _clear_init(self):
        if not self.controller.initiative:
            return
        reply = QMessageBox.question(
            self, "Initiative", "Clear the whole initiative order?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.initiative = []
            self._commit()
            self._refresh_initiative()

    def _commit(self):
        self.controller._save_scenes()
        self.controller.refresh_tabletops()
