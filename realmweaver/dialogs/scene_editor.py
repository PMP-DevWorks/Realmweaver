"""Scene editor dialog: tabbed editor for map layers, audio, lighting,
cards, notes and beats."""

import os
from dataclasses import asdict

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QGuiApplication, QColor
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QScrollArea, QFrame, QWidget,
    QTabWidget, QSlider, QCheckBox, QListWidget, QListWidgetItem, QTextEdit,
    QColorDialog, QFileDialog, QInputDialog, QMessageBox,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from realmweaver import theme
from realmweaver.theme import (
    px, pt, _touch_scroll, make_accent, make_danger,
    IMAGE_EXT, GIF_EXT, ALL_EXT, AUDIO_EXT, MEDIA_DIR, MUSIC_DIR,
    _DIALOG_OPTS, C_BORDER, C_TEXT_RUNE, C_TEXT_AGED,
)
from realmweaver.media import _pick_media_files
from realmweaver.models import Scene, SceneBeat


class SceneEditorDialog(QDialog):
    def __init__(self, scene: Scene, screen_count: int, parent=None, cards: list = None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Scene: {scene.name}")
        self.setMinimumWidth(px(640))
        self.scene        = scene
        self.screen_count = screen_count
        self.cards        = cards or []
        self._bg: dict[str, str]        = {}
        self._overlay: dict[str, str]   = {}
        self._rotations: dict[str, int]  = dict(scene.rotations)
        self._fill_modes: dict[str, bool] = dict(scene.fill_modes)
        self._music: str = scene.music_path or ""
        self._lighting: dict = dict(scene.lighting or {})
        self._beats: list[dict] = [dict(b) if isinstance(b, dict) else asdict(b)
                                   for b in scene.beats]
        self._preview_player = None

        for k, v in scene.assignments.items():
            layers = v if isinstance(v, list) else [v]
            if len(layers) > 0 and layers[0]:
                self._bg[k] = layers[0]
            if len(layers) > 1 and layers[1]:
                self._overlay[k] = layers[1]

        lay = QVBoxLayout(self)
        lay.setSpacing(px(8))

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_map_tab(),      "Map")
        self._tabs.addTab(self._build_audio_tab(),    "Audio")
        self._tabs.addTab(self._build_lighting_tab(), "Lighting")
        self._tabs.addTab(self._build_cards_tab(),    "Cards")
        self._tabs.addTab(self._build_notes_tab(),    "Notes")
        self._tabs.addTab(self._build_beats_tab(),    "Beats")
        lay.addWidget(self._tabs, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._fit_to_screen(parent)

    # ── Map tab (per-screen bg / overlay / rotation / fill) ───────────────────

    def _build_map_tab(self) -> QWidget:
        lbl_style = f"color:{C_TEXT_RUNE}; font-size:{pt(10)}pt;"
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        _touch_scroll(scroll)

        screens_container = QWidget()
        screens_lay = QVBoxLayout(screens_container)
        screens_lay.setContentsMargins(0, 0, 0, 0)
        screens_lay.setSpacing(px(8))

        for i in range(self.screen_count):
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
        return scroll

    # ── Audio tab ─────────────────────────────────────────────────────────────

    def _build_audio_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(px(8))

        mgrp = QGroupBox("Music")
        mrow = QHBoxLayout(mgrp)
        ml = QLabel("Track:")
        ml.setMinimumWidth(px(88))
        ml.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(10)}pt;")
        self._music_edit = QLineEdit(os.path.basename(self._music) if self._music else "")
        self._music_edit.setObjectName("music_track")
        self._music_edit.setReadOnly(True)
        self._music_edit.setToolTip(self._music)
        mb = QPushButton("Browse…")
        mb.setMinimumWidth(px(80))
        mb.clicked.connect(self._browse_music)
        mp = QPushButton("▶ Preview")
        mp.clicked.connect(self._preview_music)
        ms = QPushButton("⏹")
        ms.setMinimumWidth(px(48))
        ms.clicked.connect(self._stop_preview)
        mc = QPushButton("✕")
        mc.setMinimumWidth(px(48))
        mc.clicked.connect(self._clear_music)
        mrow.addWidget(ml)
        mrow.addWidget(self._music_edit, 1)
        mrow.addWidget(mb)
        mrow.addWidget(mp)
        mrow.addWidget(ms)
        mrow.addWidget(mc)
        lay.addWidget(mgrp)
        lay.addStretch(1)
        return w

    def _preview_music(self):
        if not self._music or not os.path.exists(self._music):
            return
        if self._preview_player is None:
            self._preview_player = QMediaPlayer(self)
            self._preview_audio = QAudioOutput(self)
            self._preview_audio.setVolume(0.7)
            self._preview_player.setAudioOutput(self._preview_audio)
        self._preview_player.setSource(QUrl.fromLocalFile(self._music))
        self._preview_player.play()

    def _stop_preview(self):
        if self._preview_player:
            self._preview_player.stop()

    def done(self, result):
        self._stop_preview()
        super().done(result)

    # ── Lighting tab ──────────────────────────────────────────────────────────

    def _build_lighting_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(px(10))

        self._light_chk = QCheckBox("Tint the map screens for this scene")
        self._light_chk.setChecked(bool(self._lighting.get("tint")))
        lay.addWidget(self._light_chk)

        color_row = QHBoxLayout()
        cl = QLabel("Tint color:")
        cl.setMinimumWidth(px(120))
        cl.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(10)}pt;")
        self._light_color = self._lighting.get("tint", "#1a1033")
        self._light_color_btn = QPushButton()
        self._light_color_btn.setFixedHeight(px(56))
        self._light_color_btn.clicked.connect(self._pick_light_color)
        self._update_light_btn()
        color_row.addWidget(cl)
        color_row.addWidget(self._light_color_btn, 1)
        lay.addLayout(color_row)

        op_row = QHBoxLayout()
        ol = QLabel("Intensity:")
        ol.setMinimumWidth(px(120))
        ol.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(10)}pt;")
        self._light_slider = QSlider(Qt.Orientation.Horizontal)
        self._light_slider.setRange(5, 90)
        self._light_slider.setValue(int(float(self._lighting.get("opacity", 0.3)) * 100))
        self._light_val = QLabel(f"{self._light_slider.value()}%")
        self._light_val.setMinimumWidth(px(52))
        self._light_slider.valueChanged.connect(
            lambda v: self._light_val.setText(f"{v}%"))
        op_row.addWidget(ol)
        op_row.addWidget(self._light_slider, 1)
        op_row.addWidget(self._light_val)
        lay.addLayout(op_row)

        hint = QLabel("Examples: deep blue for night, warm amber for candlelight, "
                      "green for a poison fog.")
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch(1)
        return w

    def _update_light_btn(self):
        self._light_color_btn.setStyleSheet(
            f"background:{self._light_color}; border:1px solid {C_BORDER}; "
            f"border-radius:{px(6)}px;")

    def _pick_light_color(self):
        color = QColorDialog.getColor(QColor(self._light_color), self, "Tint Color")
        if color.isValid():
            self._light_color = color.name()
            self._update_light_btn()
            self._light_chk.setChecked(True)

    # ── Cards tab ─────────────────────────────────────────────────────────────

    def _build_cards_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        hint = QLabel("Cards checked here appear in the map dock when the "
                      "scene is activated.")
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self._cards_list = QListWidget()
        _touch_scroll(self._cards_list)
        for card in self.cards:
            item = QListWidgetItem(f"{card.name}   [{card.rarity}]")
            item.setData(Qt.ItemDataRole.UserRole, card.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked
                               if card.id in self.scene.card_ids
                               else Qt.CheckState.Unchecked)
            self._cards_list.addItem(item)
        lay.addWidget(self._cards_list, 1)
        if not self.cards:
            empty = QLabel("No cards yet — create some via the Cards… button "
                           "on the control panel.")
            empty.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
            lay.addWidget(empty)
        return w

    # ── Notes tab ─────────────────────────────────────────────────────────────

    def _build_notes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        hint = QLabel("Shown in the Notes panel on the map screens.")
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        lay.addWidget(hint)
        self._notes_edit = QTextEdit()
        self._notes_edit.setAcceptRichText(True)
        self._notes_edit.setHtml(self.scene.notes_html)
        _touch_scroll(self._notes_edit)
        lay.addWidget(self._notes_edit, 1)
        return w

    # ── Beats tab ─────────────────────────────────────────────────────────────

    def _build_beats_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        hint = QLabel("Beats are moments inside this scene — each can swap the "
                      "notes, music, lighting or cards without changing the map.")
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self._beats_list = QListWidget()
        _touch_scroll(self._beats_list)
        lay.addWidget(self._beats_list, 1)
        self._refresh_beats()

        row = QHBoxLayout()
        add_b = QPushButton("+ Add beat")
        make_accent(add_b)
        add_b.clicked.connect(self._add_beat)
        edit_b = QPushButton("Edit…")
        edit_b.clicked.connect(self._edit_beat)
        up_b = QPushButton("▲")
        up_b.setMinimumWidth(px(56))
        up_b.clicked.connect(lambda: self._move_beat(-1))
        dn_b = QPushButton("▼")
        dn_b.setMinimumWidth(px(56))
        dn_b.clicked.connect(lambda: self._move_beat(1))
        del_b = QPushButton("Delete")
        make_danger(del_b)
        del_b.clicked.connect(self._del_beat)
        for b in (add_b, edit_b, up_b, dn_b, del_b):
            row.addWidget(b)
        lay.addLayout(row)
        return w

    def _refresh_beats(self):
        self._beats_list.clear()
        for b in self._beats:
            bits = [b.get("name", "beat")]
            if b.get("music_path"):
                bits.append("♪")
            if b.get("lighting"):
                bits.append("☀")
            if b.get("card_ids"):
                bits.append(f"🃏×{len(b['card_ids'])}")
            self._beats_list.addItem("  ".join(bits))

    def _add_beat(self):
        name, ok = QInputDialog.getText(self, "New Beat", "Beat name:")
        if ok and name.strip():
            self._beats.append(asdict(SceneBeat(name=name.strip())))
            self._refresh_beats()
            self._beats_list.setCurrentRow(len(self._beats) - 1)
            self._edit_beat()

    def _edit_beat(self):
        row = self._beats_list.currentRow()
        if not (0 <= row < len(self._beats)):
            return
        dlg = BeatEditorDialog(self._beats[row], self.cards, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._beats[row] = dlg.beat
            self._refresh_beats()
            self._beats_list.setCurrentRow(row)

    def _move_beat(self, direction: int):
        row = self._beats_list.currentRow()
        new = row + direction
        if 0 <= row < len(self._beats) and 0 <= new < len(self._beats):
            self._beats[row], self._beats[new] = self._beats[new], self._beats[row]
            self._refresh_beats()
            self._beats_list.setCurrentRow(new)

    def _del_beat(self):
        row = self._beats_list.currentRow()
        if 0 <= row < len(self._beats):
            del self._beats[row]
            self._refresh_beats()

    # ── shared helpers ────────────────────────────────────────────────────────

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
                    min(max(self.sizeHint().height(), px(420)), self.maximumHeight()))
        x = avail.x() + (avail.width() - self.width()) // 2
        y = avail.y() + (avail.height() - self.height()) // 2
        self.move(x, y)

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

    # ── apply ─────────────────────────────────────────────────────────────────

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

        if self._light_chk.isChecked():
            self.scene.lighting = {"tint": self._light_color,
                                   "opacity": self._light_slider.value() / 100.0}
        else:
            self.scene.lighting = None

        card_ids = []
        for i in range(self._cards_list.count()):
            item = self._cards_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                card_ids.append(item.data(Qt.ItemDataRole.UserRole))
        self.scene.card_ids = card_ids

        html = self._notes_edit.toHtml()
        self.scene.notes_html = html if self._notes_edit.toPlainText().strip() else ""
        self.scene.beats = list(self._beats)


class BeatEditorDialog(QDialog):
    """Edit one beat: name, music cue, notes, cards."""

    def __init__(self, beat: dict, cards: list, parent=None):
        super().__init__(parent)
        self.beat = dict(beat)
        self.cards = cards
        self.setWindowTitle(f"Beat: {self.beat.get('name', '')}")
        self.setMinimumSize(px(480), px(480))
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(px(8))
        lay.setContentsMargins(px(16), px(16), px(16), px(16))

        r = QHBoxLayout()
        l = QLabel("Name:")
        l.setMinimumWidth(px(88))
        l.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(10)}pt;")
        self._name = QLineEdit(self.beat.get("name", ""))
        r.addWidget(l)
        r.addWidget(self._name, 1)
        lay.addLayout(r)

        r = QHBoxLayout()
        l = QLabel("Music cue:")
        l.setMinimumWidth(px(88))
        l.setStyleSheet(f"color:{C_TEXT_AGED}; font-size:{pt(10)}pt;")
        music = self.beat.get("music_path") or ""
        self._music_edit = QLineEdit(os.path.basename(music))
        self._music_edit.setReadOnly(True)
        self._music_edit.setToolTip(music)
        b = QPushButton("Browse…")
        b.clicked.connect(self._browse_music)
        c = QPushButton("✕")
        c.setMinimumWidth(px(48))
        c.clicked.connect(self._clear_music)
        r.addWidget(l)
        r.addWidget(self._music_edit, 1)
        r.addWidget(b)
        r.addWidget(c)
        lay.addLayout(r)

        lbl = QLabel("Notes (replace scene notes while this beat is live):")
        lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        lay.addWidget(lbl)
        self._notes = QTextEdit()
        self._notes.setAcceptRichText(True)
        self._notes.setHtml(self.beat.get("notes_html", ""))
        _touch_scroll(self._notes)
        lay.addWidget(self._notes, 1)

        lbl = QLabel("Cards revealed at this beat:")
        lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        lay.addWidget(lbl)
        self._cards_list = QListWidget()
        _touch_scroll(self._cards_list)
        chosen = set(self.beat.get("card_ids") or [])
        for card in self.cards:
            item = QListWidgetItem(f"{card.name}   [{card.rarity}]")
            item.setData(Qt.ItemDataRole.UserRole, card.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if card.id in chosen
                               else Qt.CheckState.Unchecked)
            self._cards_list.addItem(item)
        lay.addWidget(self._cards_list, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _browse_music(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Music cue", MUSIC_DIR,
                                              f"Audio ({exts})", options=_DIALOG_OPTS)
        if path:
            self.beat["music_path"] = path
            self._music_edit.setText(os.path.basename(path))
            self._music_edit.setToolTip(path)

    def _clear_music(self):
        self.beat["music_path"] = None
        self._music_edit.setText("")
        self._music_edit.setToolTip("")

    def _on_accept(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Beat", "Give the beat a name.")
            return
        self.beat["name"] = name
        html = self._notes.toHtml()
        self.beat["notes_html"] = html if self._notes.toPlainText().strip() else ""
        card_ids = []
        for i in range(self._cards_list.count()):
            item = self._cards_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                card_ids.append(item.data(Qt.ItemDataRole.UserRole))
        self.beat["card_ids"] = card_ids
        self.accept()
