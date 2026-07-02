"""Main control panel window."""
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

from realmweaver.media import (media_kind, MediaTile, MediaListWidget,
                               _pick_media_files)
from realmweaver import store
from realmweaver.models import Scene, AssetItem, PlacedAsset
from realmweaver.dialogs.cards_dm import CardLibraryDialog
from realmweaver.dialogs.party import PartyDialog
from realmweaver.widgets.story_tree import StoryOutlineSidebar
from realmweaver.widgets.carousel import SceneCarouselDialog

THUMBS_DIR = os.path.join(DATA_DIR, "thumbs")
os.makedirs(THUMBS_DIR, exist_ok=True)
from realmweaver.output.output_window import OutputWindow
from realmweaver.widgets.panels import ScreenCard
from realmweaver.dialogs.scene_editor import SceneEditorDialog

# ─────────────────────────────────────────────────────────────────────────────
# ControlWindow — main control panel
# ─────────────────────────────────────────────────────────────────────────────
class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SceneCaster — Control")
        self.resize(1200, 820)
        self._apply_dark_theme()

        self.outputs: list[OutputWindow]    = []
        self.screen_cards: list[ScreenCard] = []
        self.scenes: list[Scene]            = []
        self.live_assignments: dict[int, str] = {}
        self.live_overlays: dict[int, str]    = {}
        self.live_grid_settings: dict[int, dict] = {}
        self.live_placed_assets: dict[int, list] = {}
        self.screen_sizes: dict[str, dict]    = {}
        self.asset_library: list[AssetItem]   = []
        self.arcs: list = []           # Arc dataclasses (story structure)
        self.cards: list = []          # Card dataclasses (item/NPC/handout)
        self.players: list = []        # PlayerPlate dataclasses
        self.initiative: list = []     # InitiativeEntry dataclasses
        self.screen_flags: dict = {}   # str(screen_idx) -> {"scenes","hud"}
        self._main_screen_idx: int = 0
        self.live_table_cards: list = []   # Cards currently in the map dock

        # timers kept alive for music fade operations
        self._music_fade_out_timer: Optional[QTimer] = None
        self._music_fade_in_timer:  Optional[QTimer] = None

        self._build_outputs()
        self._build_music_backend()
        self._build_ui()
        self._load_scenes()

    # ── theming ───────────────────────────────────────────────────────────────

    def _apply_dark_theme(self):
        f = QFont(theme.FONT_BODY)
        f.setPointSize(pt(10))
        QApplication.instance().setFont(f)

        qss = f"""
        QWidget {{
            background: {C_PANEL};
            color: {C_TEXT_PARCH};
            font-family: "{theme.FONT_BODY}";
            font-size: {pt(10)}pt;
        }}
        ControlWindow {{
            background: {C_VOID};
        }}
        QLabel {{
            border: none;
            background: transparent;
        }}
        QPushButton {{
            background: {C_CARD};
            color: {C_TEXT_PARCH};
            border: none;
            border-top: 2px solid {C_GOLD_DIM};
            padding: {px(10)}px {px(24)}px;
            border-radius: {px(10)}px;
            font-size: {pt(11)}pt;
            min-height: {px(72)}px;
        }}
        QPushButton:hover {{
            background: {C_HOVER};
            border-top: 1px solid {C_ACCENT_GOLD};
        }}
        QPushButton:pressed {{
            background: {C_ACCENT_PURPLE};
            color: white;
        }}
        QPushButton:disabled {{
            background: {C_VOID};
            color: {C_TEXT_RUNE};
            border-top: 1px solid {C_BORDER};
        }}
        QPushButton:checked {{
            background: {C_ACCENT_PURPLE};
            color: white;
            border-top: 1px solid {C_GLOW_PURPLE};
        }}
        QPushButton[accent="true"] {{
            background: {C_ACCENT_GOLD};
            color: {C_VOID};
            font-weight: 700;
            border: none;
        }}
        QPushButton[accent="true"]:hover {{
            background: #d4aa30;
        }}
        QPushButton[accent="true"]:pressed {{
            background: #b08a1a;
        }}
        QPushButton[danger="true"] {{
            background: #1a0505;
            color: #ff7070;
            border-top: 1px solid {C_DANGER};
        }}
        QPushButton[danger="true"]:hover {{
            background: #2a0a0a;
        }}
        QListWidget {{
            background: {C_VOID};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_BORDER};
            border-radius: {px(8)}px;
            padding: {px(3)}px;
        }}
        QListWidget::item {{
            padding: {px(14)}px {px(10)}px;
            border-radius: {px(6)}px;
            min-height: {px(64)}px;
        }}
        QListWidget::item:selected {{
            background: {C_CARD};
            color: {C_ACCENT_GOLD};
            border-left: 3px solid {C_ACCENT_GOLD};
        }}
        QListWidget::item:hover:!selected {{
            background: {C_HOVER};
        }}
        QComboBox {{
            background: {C_INPUT};
            color: {C_TEXT_PARCH};
            padding: {px(12)}px {px(16)}px;
            border-radius: {px(8)}px;
            border: 1px solid {C_BORDER};
            font-size: {pt(11)}pt;
            min-height: {px(60)}px;
        }}
        QComboBox:hover {{
            border: 1px solid {C_GOLD_DIM};
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background: {C_CARD};
            color: {C_TEXT_PARCH};
            selection-background-color: {C_HOVER};
            selection-color: {C_ACCENT_GOLD};
            border: 1px solid {C_BORDER};
        }}
        QLineEdit {{
            background: {C_INPUT};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_BORDER};
            border-radius: {px(8)}px;
            padding: {px(10)}px {px(14)}px;
            min-height: {px(56)}px;
        }}
        QLineEdit:focus {{
            border: 1px solid {C_ACCENT_GOLD};
        }}
        QGroupBox {{
            color: {C_ACCENT_GOLD};
            font-weight: 600;
            font-size: {pt(10)}pt;
            border: 1px solid {C_ACCENT_PURPLE};
            border-radius: {px(8)}px;
            margin-top: {px(10)}px;
            padding-top: {px(12)}px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {px(12)}px;
            color: {C_ACCENT_GOLD};
        }}
        QSlider::groove:horizontal {{
            background: {C_BORDER};
            height: {px(6)}px;
            border-radius: {px(3)}px;
        }}
        QSlider::handle:horizontal {{
            background: {C_ACCENT_GOLD};
            width: {px(32)}px;
            height: {px(32)}px;
            border-radius: {px(16)}px;
            margin: {px(-14)}px 0;
        }}
        QSlider::sub-page:horizontal {{
            background: {C_ACCENT_PURPLE};
            border-radius: {px(2)}px;
        }}
        QScrollBar:vertical {{
            width: {px(8)}px;
            background: {C_VOID};
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {C_GOLD_DIM};
            border-radius: {px(4)}px;
            min-height: {px(24)}px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {C_ACCENT_GOLD};
        }}
        QScrollBar:horizontal {{
            height: {px(8)}px;
            background: {C_VOID};
        }}
        QScrollBar::handle:horizontal {{
            background: {C_GOLD_DIM};
            border-radius: {px(4)}px;
            min-width: {px(24)}px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {C_ACCENT_GOLD};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; }}
        QFrame#screenCard {{
            background: {C_CARD};
            border: 1px solid {C_BORDER};
            border-top: 2px solid {C_BORDER_GOLD};
            border-radius: {px(10)}px;
        }}
        QFrame#screenCard:hover {{
            border: 1px solid {C_ACCENT_PURPLE};
            border-top: 2px solid {C_ACCENT_GOLD};
        }}
        QFrame#musicPanel {{
            background: {C_CARD};
            border: 1px solid {C_BORDER};
            border-top: 2px solid {C_BORDER_GOLD};
            border-radius: {px(8)}px;
        }}
        QCheckBox {{
            color: {C_TEXT_AGED};
            spacing: {px(8)}px;
        }}
        QCheckBox::indicator {{
            width: {px(28)}px;
            height: {px(28)}px;
            border: 1px solid {C_BORDER};
            border-radius: {px(6)}px;
            background: {C_INPUT};
        }}
        QCheckBox::indicator:checked {{
            background: {C_ACCENT_GOLD};
            border-color: {C_ACCENT_GOLD};
        }}
        QSpinBox, QDoubleSpinBox {{
            background: {C_INPUT};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_BORDER};
            border-radius: {px(8)}px;
            padding: {px(8)}px {px(10)}px;
            min-height: {px(52)}px;
        }}
        QSplitter::handle {{
            background: {C_BORDER};
        }}
        QSplitter::handle:horizontal {{
            width: {px(2)}px;
        }}
        QToolTip {{
            background: {C_CARD};
            color: {C_TEXT_PARCH};
            border: 1px solid {C_ACCENT_GOLD};
            padding: {px(5)}px;
            border-radius: {px(4)}px;
        }}
        QScrollArea {{
            background: {C_VOID};
            border: none;
        }}
        QDialog {{
            background: {C_PANEL};
        }}
        """
        self.setStyleSheet(qss)

    def btn_style(self):
        return ""

    def accent_btn_style(self):
        return ""

    def _combo_style(self):
        return ""

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _runic_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(9)}pt; '
            f'color:{C_ACCENT_GOLD}; letter-spacing:3px; font-weight:600;'
        )
        return lbl

    @staticmethod
    def _make_accent(btn: QPushButton) -> QPushButton:
        btn.setProperty("accent", "true")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    @staticmethod
    def _make_danger(btn: QPushButton) -> QPushButton:
        btn.setProperty("danger", "true")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    # ── music backend ─────────────────────────────────────────────────────────

    def _build_music_backend(self):
        self._music_player = QMediaPlayer()
        self._music_audio  = QAudioOutput()
        self._music_player.setAudioOutput(self._music_audio)
        self._music_audio.setVolume(0.7)
        self._music_loop   = True
        self._music_player.mediaStatusChanged.connect(self._on_music_status)

    def _on_music_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._music_loop:
            self._music_player.setPosition(0)
            self._music_player.play()

    def _on_speaker_changed(self, idx: int):
        if 0 <= idx < len(self._audio_devices):
            self._music_audio.setDevice(self._audio_devices[idx])

    def _play_music(self, path: str):
        if not path or not os.path.exists(path):
            return
        self._music_player.setSource(QUrl.fromLocalFile(path))
        self._music_player.play()
        self._music_track_label.setText(os.path.basename(path))

    def _play_music_with_fade(self, path: str):
        target_vol = self._vol_slider.value() / 100.0
        is_playing = (self._music_player.playbackState() ==
                      QMediaPlayer.PlaybackState.PlayingState)
        if is_playing:
            self._music_fade_out(
                MUSIC_FADE_MS,
                lambda: self._start_and_fade_in(path, target_vol))
        else:
            self._start_and_fade_in(path, target_vol)

    def _start_and_fade_in(self, path: str, target_vol: float):
        self._music_audio.setVolume(0.0)
        self._play_music(path)
        self._music_fade_in(MUSIC_FADE_MS, target_vol)

    def _music_fade_out(self, duration_ms: int, callback):
        if self._music_fade_out_timer:
            self._music_fade_out_timer.stop()
        start_vol = self._music_audio.volume()
        if start_vol <= 0.001:
            self._music_player.stop()
            callback()
            return
        steps    = max(1, duration_ms // 30)
        step_vol = start_vol / steps
        current  = [start_vol]
        timer    = QTimer(self)
        def tick():
            current[0] = max(0.0, current[0] - step_vol)
            self._music_audio.setVolume(current[0])
            if current[0] <= 0.0:
                timer.stop()
                self._music_player.stop()
                callback()
        timer.timeout.connect(tick)
        timer.start(30)
        self._music_fade_out_timer = timer

    def _music_fade_in(self, duration_ms: int, target_vol: float):
        if self._music_fade_in_timer:
            self._music_fade_in_timer.stop()
        if target_vol <= 0:
            return
        steps    = max(1, duration_ms // 30)
        step_vol = target_vol / steps
        current  = [0.0]
        timer    = QTimer(self)
        def tick():
            current[0] = min(target_vol, current[0] + step_vol)
            self._music_audio.setVolume(current[0])
            if current[0] >= target_vol:
                timer.stop()
        timer.timeout.connect(tick)
        timer.start(30)
        self._music_fade_in_timer = timer

    # ── output windows ────────────────────────────────────────────────────────

    def _build_outputs(self):
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        self._primary = primary
        self._main_screen_idx = screens.index(primary) if primary in screens else 0
        for idx, scr in enumerate(screens):
            win = OutputWindow(idx, scr)
            self.outputs.append(win)
            if idx != self._main_screen_idx:
                win.place_on_screen()
        QTimer.singleShot(300, self._reclaim_focus)

    def _reclaim_focus(self):
        self.raise_()
        self.activateWindow()

    # ── grid live update ──────────────────────────────────────────────────────

    def update_live_grid(self, idx: int, settings: dict):
        self.live_grid_settings[idx] = settings
        if idx < len(self.outputs):
            self.outputs[idx].apply_grid(settings)

    # ── placed asset management ───────────────────────────────────────────────

    def set_placed_assets(self, idx: int, assets: list):
        self.live_placed_assets[idx] = list(assets)
        if idx < len(self.outputs):
            self.outputs[idx].set_placed_assets(assets)
        if idx < len(self.screen_cards):
            self._refresh_thumb(idx)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(px(16), px(16), px(16), px(16))
        root.setSpacing(px(10))

        header = QLabel("SceneCaster")
        header.setStyleSheet(
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(22)}pt; font-weight:700; color:{C_ACCENT_GOLD};'
        )
        sub = QLabel("Arcane Screen Weaver  •  D&D Storytelling Display Controller")
        sub.setStyleSheet(
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(10)}pt; color:{C_TEXT_RUNE}; letter-spacing:1px;'
        )
        exit_btn = QPushButton("⏻  Exit")
        exit_btn.setProperty("danger", True)
        exit_btn.setMinimumHeight(px(72))
        exit_btn.setMinimumWidth(px(140))
        exit_btn.clicked.connect(self._confirm_exit)

        head_row = QHBoxLayout()
        head_row.setSpacing(px(12))
        head_col = QVBoxLayout()
        head_col.setSpacing(0)
        head_col.addWidget(header)
        head_col.addWidget(sub)
        head_row.addLayout(head_col)
        head_row.addStretch(1)
        head_row.addWidget(exit_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(head_row)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(f"background:{C_GOLD_DIM}; max-height:1px; border:none;")
        rule.setFixedHeight(1)
        root.addWidget(rule)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # ── LEFT: media library + scenes ──────────────────────────────────────
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(px(6))

        lib_lbl = self._runic_label("Media Library")
        ll.addWidget(lib_lbl)

        self.media_list = MediaListWidget()
        self.media_list.setIconSize(QSize(px(40), px(40)))
        self.media_list.setAcceptDrops(True)
        self.media_list.itemDoubleClicked.connect(self._preview_or_hint)
        _touch_scroll(self.media_list)
        ll.addWidget(self.media_list, 1)

        mb_row = QHBoxLayout()
        mb_row.setSpacing(px(6))
        for lbl, cb in (("Add files…", self._add_files_dialog),
                        ("Add folder…", self._add_folder_dialog)):
            b = QPushButton(lbl)
            b.clicked.connect(cb)
            mb_row.addWidget(b)
        ll.addLayout(mb_row)

        scn_lbl = self._runic_label("Story")
        ll.addWidget(scn_lbl)

        # Hidden flat list: keeps "current scene index" state for the rest of
        # the app; the story tree is the visible navigation.
        self.scene_list = QListWidget()
        self.scene_list.itemDoubleClicked.connect(self._activate_scene_item)
        _touch_scroll(self.scene_list)
        self.scene_list.setVisible(False)
        ll.addWidget(self.scene_list)

        self.story_tree = StoryOutlineSidebar(self)
        self.story_tree.scene_activated.connect(self._activate_scene_by_id)
        self.story_tree.beat_activated.connect(self._activate_beat)
        ll.addWidget(self.story_tree, 1)

        sb_row = QHBoxLayout()
        sb_row.setSpacing(px(6))
        for lbl, cb in (("Save current", self._save_scene),
                        ("Edit scene…",  self._edit_scene),
                        ("Delete",       self._delete_scene)):
            b = QPushButton(lbl)
            b.clicked.connect(cb)
            if lbl == "Delete":
                self._make_danger(b)
            sb_row.addWidget(b)
        ll.addLayout(sb_row)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(px(6))
        prev_btn = QPushButton("◀ Prev")
        prev_btn.clicked.connect(lambda: self._step_scene(-1))
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(lambda: self._step_scene(1))
        self._make_accent(next_btn)
        browse_btn = QPushButton("🕰 Browse")
        browse_btn.clicked.connect(self._open_carousel)
        nav_row.addWidget(prev_btn)
        nav_row.addWidget(next_btn)
        nav_row.addWidget(browse_btn)
        ll.addLayout(nav_row)

        splitter.addWidget(left)

        # ── RIGHT: screen cards + music + global ──────────────────────────────
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(px(8))

        scr_lbl = self._runic_label("Connected Screens")
        rl.addWidget(scr_lbl)

        ctrl_row = QHBoxLayout()
        ctrl_lbl = QLabel("Control panel on:")
        ctrl_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(10)}pt;")
        self.main_screen_combo = QComboBox()
        for i in range(len(self.outputs)):
            self.main_screen_combo.addItem(f"Screen {i + 1}")
        self.main_screen_combo.setCurrentIndex(self._main_screen_idx)
        self.main_screen_combo.currentIndexChanged.connect(self._set_main_screen)
        ctrl_row.addWidget(ctrl_lbl)
        ctrl_row.addWidget(self.main_screen_combo, 1)
        rl.addLayout(ctrl_row)

        cards_scroll  = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        _touch_scroll(cards_scroll)
        cards_holder  = QWidget()
        self.cards_grid = QGridLayout(cards_holder)
        self.cards_grid.setSpacing(px(12))

        for idx, scr in enumerate(QGuiApplication.screens()):
            card = ScreenCard(idx, self)
            geo  = scr.geometry()
            dpr  = scr.devicePixelRatio()
            rw   = int(geo.width() * dpr)
            rh   = int(geo.height() * dpr)
            tag  = " (primary)" if scr == self._primary else ""
            res  = f"{rw}×{rh}{tag}" + ("  • 4K" if rw >= 3840 else "")
            card.set_resolution_text(res)
            card.set_is_main(idx == self._main_screen_idx)
            self.screen_cards.append(card)
            self.cards_grid.addWidget(card, idx // 2, idx % 2)

        cards_scroll.setWidget(cards_holder)
        rl.addWidget(cards_scroll, 1)

        # ── Music panel ───────────────────────────────────────────────────────
        mf = QFrame()
        mf.setObjectName("musicPanel")
        mfl = QVBoxLayout(mf)
        mfl.setContentsMargins(px(12), px(10), px(12), px(10))
        mfl.setSpacing(px(6))

        mf_hdr = QLabel("♪  Music Layer")
        mf_hdr.setStyleSheet(
            f'font-family:"{theme.FONT_SERIF}"; font-size:{pt(11)}pt; font-weight:600; color:{C_ACCENT_GOLD};'
        )
        mfl.addWidget(mf_hdr)

        spk_row = QHBoxLayout()
        spk_lbl = QLabel("Output:")
        spk_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self._speaker_combo = QComboBox()
        self._audio_devices = QMediaDevices.audioOutputs()
        default_dev = QMediaDevices.defaultAudioOutput()
        for dev in self._audio_devices:
            self._speaker_combo.addItem(dev.description())
        default_idx = next(
            (i for i, d in enumerate(self._audio_devices) if d.id() == default_dev.id()), 0)
        self._speaker_combo.setCurrentIndex(default_idx)
        self._speaker_combo.currentIndexChanged.connect(self._on_speaker_changed)
        spk_row.addWidget(spk_lbl)
        spk_row.addWidget(self._speaker_combo, 1)
        mfl.addLayout(spk_row)

        self._music_track_label = QLabel("No track loaded")
        self._music_track_label.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        mfl.addWidget(self._music_track_label)

        mc_row = QHBoxLayout()
        mc_row.setSpacing(px(6))
        play_b  = QPushButton("▶ Play")
        pause_b = QPushButton("⏸ Pause")
        stop_b  = QPushButton("⏹ Stop")
        add_m_b = QPushButton("Add music…")
        play_b.clicked.connect(self._music_player.play)
        pause_b.clicked.connect(self._music_player.pause)
        stop_b.clicked.connect(self._music_player.stop)
        add_m_b.clicked.connect(self._add_music_dialog)
        self._make_accent(play_b)
        for b in (play_b, pause_b, stop_b, add_m_b):
            mc_row.addWidget(b)
        mfl.addLayout(mc_row)

        vol_row = QHBoxLayout()
        vol_lbl = QLabel("Vol:")
        vol_lbl.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.valueChanged.connect(
            lambda v: self._music_audio.setVolume(v / 100.0))
        self._loop_chk = QCheckBox("Loop")
        self._loop_chk.setChecked(True)
        self._loop_chk.toggled.connect(self._set_music_loop)
        vol_row.addWidget(vol_lbl)
        vol_row.addWidget(self._vol_slider, 1)
        vol_row.addWidget(self._loop_chk)
        mfl.addLayout(vol_row)

        rl.addWidget(mf)

        # Global controls
        glob_row = QHBoxLayout()
        glob_row.setSpacing(px(8))
        blank_all_b = QPushButton("⬛  Blank all screens")
        blank_all_b.clicked.connect(self.blank_all)
        self._make_danger(blank_all_b)
        self.mute_combo = QComboBox()
        self.mute_combo.addItems(["Video audio: ON", "Video audio: MUTED"])
        cards_b = QPushButton("🃏 Cards…")
        cards_b.clicked.connect(self._open_cards)
        party_b = QPushButton("👥 Party…")
        party_b.clicked.connect(self._open_party)
        glob_row.addWidget(blank_all_b)
        glob_row.addWidget(cards_b)
        glob_row.addWidget(party_b)
        glob_row.addStretch(1)
        glob_row.addWidget(self.mute_combo)
        rl.addLayout(glob_row)

        splitter.addWidget(right)
        splitter.setSizes([px(400), px(900)])

        hint = QLabel(
            "Select media → 'Set BG →' for background, 'Set overlay →' for composited overlay. "
            "Double-click a scene to activate it. ◀ / ▶ or ← / → to step scenes. B = blank all. "
            "Use 'Edit scene…' to configure bg/overlay/music per screen without going live first."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{C_TEXT_RUNE}; font-size:{pt(9)}pt;")
        root.addWidget(hint)

    def _set_music_loop(self, checked: bool):
        self._music_loop = checked

    # ── main screen ───────────────────────────────────────────────────────────

    def _move_control_to_screen(self, screen_idx: int):
        screens = QGuiApplication.screens()
        if screen_idx < len(screens):
            geo = screens[screen_idx].geometry()
            self.move(geo.topLeft())
            self.showMaximized()

    def _set_main_screen(self, new_idx: int):
        old_idx = self._main_screen_idx
        if old_idx == new_idx:
            return
        self._main_screen_idx = new_idx
        if old_idx < len(self.outputs):
            self.outputs[old_idx].place_on_screen()
        if new_idx < len(self.outputs):
            self.outputs[new_idx].hide()
        for i, card in enumerate(self.screen_cards):
            card.set_is_main(i == new_idx)
        self._move_control_to_screen(new_idx)
        self._save_scenes()
        QTimer.singleShot(300, self._reclaim_focus)

    # ── per-screen switches ───────────────────────────────────────────────────

    def screen_flag(self, idx: int, key: str) -> bool:
        return self.screen_flags.get(str(idx), {}).get(key,
                                                       store.DEFAULT_FLAGS[key])

    def screen_shows_scenes(self, idx: int) -> bool:
        return idx != self._main_screen_idx and self.screen_flag(idx, "scenes")

    def screen_shows_hud(self, idx: int) -> bool:
        return idx != self._main_screen_idx and self.screen_flag(idx, "hud")

    def set_screen_flag(self, idx: int, key: str, value: bool):
        """Flip one switch for one screen. Turning scenes back ON immediately
        re-applies the current scene there, so the screen never stays black
        without an obvious way to bring it back."""
        flags = self.screen_flags.setdefault(str(idx), dict(store.DEFAULT_FLAGS))
        flags[key] = value
        self._save_scenes()
        if key == "hud":
            self.refresh_tabletops()
        elif key == "scenes" and value:
            row = self.scene_list.currentRow()
            if 0 <= row < len(self.scenes):
                self._apply_scene_to_screen(self.scenes[row], idx)

    def _sync_flag_checkboxes(self):
        for idx, card in enumerate(self.screen_cards):
            card.set_flags(self.screen_flag(idx, "scenes"),
                           self.screen_flag(idx, "hud"))

    # ── tabletop HUD & cards ──────────────────────────────────────────────────

    def _open_cards(self):
        CardLibraryDialog(self, parent=self).exec()

    def _open_party(self):
        PartyDialog(self, parent=self).exec()

    def card_by_id(self, card_id: str):
        return next((c for c in self.cards if c.id == card_id), None)

    def current_scene(self):
        row = self.scene_list.currentRow()
        if 0 <= row < len(self.scenes):
            return self.scenes[row]
        return None

    def refresh_tabletops(self):
        """Push players, notes, initiative, dock cards and the current track
        to the HUD of every screen whose HUD switch is checked."""
        scene = self.current_scene()
        notes = scene.notes_html if scene else ""
        track = scene.music_path if scene else None
        for idx, out in enumerate(self.outputs):
            if idx == self._main_screen_idx:
                continue
            tt = out.tabletop
            if not self.screen_shows_hud(idx):
                tt.set_enabled(False)
                continue
            tt.set_players(self.players)
            tt.set_initiative(self.initiative)
            tt.set_notes(notes)
            tt.set_cards(self.live_table_cards)
            tt.set_track(track)
            tt.set_enabled(True)

    def push_card_to_table(self, card):
        """Add a card to the map dock and remember it on the current scene."""
        if all(c.id != card.id for c in self.live_table_cards):
            self.live_table_cards.append(card)
        scene = self.current_scene()
        if scene is not None and card.id not in scene.card_ids:
            scene.card_ids.append(card.id)
            self._save_scenes()
        self.refresh_tabletops()

    def _apply_scene_to_screen(self, scene, idx: int):
        """Re-apply the current scene's content to one screen (used when its
        'Show scenes' switch is turned back on)."""
        if idx >= len(self.outputs) or idx == self._main_screen_idx:
            return
        k = str(idx)
        layers = scene.assignments.get(k, [])
        ls = layers if isinstance(layers, list) else [layers]
        bg = ls[0] if len(ls) > 0 else ""
        ov = ls[1] if len(ls) > 1 else ""
        self.outputs[idx].set_rotation(scene.rotations.get(k, 0))
        self.outputs[idx].set_fill_mode(scene.fill_modes.get(k, False))
        if bg:
            self.push_to_screen(idx, bg)
        if ov:
            self.push_overlay_to_screen(idx, ov)
        self.outputs[idx].apply_grid(scene.grid_settings.get(k, {}))
        self.outputs[idx].set_lighting(scene.lighting)
        self.refresh_tabletops()

    def push_cards_to_screen(self, idx: int, cards: list):
        """Show cards on exactly the screen the DM picked; empty list clears
        them and uncovers whatever media that screen was showing."""
        if idx == self._main_screen_idx or idx >= len(self.outputs):
            return
        if cards:
            self.outputs[idx].show_cards(cards)
        else:
            self.outputs[idx].clear_cards()

    # ── rotation / fill ───────────────────────────────────────────────────────

    def set_rotation(self, screen_idx: int, degrees: int):
        if screen_idx < len(self.outputs):
            self.outputs[screen_idx].set_rotation(degrees)

    def set_fill_mode(self, screen_idx: int, fill: bool):
        if screen_idx < len(self.outputs):
            self.outputs[screen_idx].set_fill_mode(fill)

    # ── media library ─────────────────────────────────────────────────────────

    def add_media(self, path: str):
        for i in range(self.media_list.count()):
            if self.media_list.item(i).path == path:
                return
        self.media_list.addItem(MediaTile(path))

    def _add_files_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(ALL_EXT))
        files = _pick_media_files(self, "Add media", MEDIA_DIR, f"Media ({exts})", multi=True)
        for f in files:
            self.add_media(f)

    def _add_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(
            self, "Add folder", MEDIA_DIR,
            options=QFileDialog.Option.ShowDirsOnly | _DIALOG_OPTS)
        if not d:
            return
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isfile(p) and media_kind(p):
                self.add_media(p)

    def _add_music_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Add music", MUSIC_DIR, f"Audio ({exts})", options=_DIALOG_OPTS)
        if path:
            self._play_music(path)

    def selected_media_path(self) -> Optional[str]:
        it = self.media_list.currentItem()
        return it.path if isinstance(it, MediaTile) else None

    def _preview_or_hint(self, item):
        if isinstance(item, MediaTile):
            target = next(
                (i for i in range(len(self.outputs)) if i != self._main_screen_idx), None)
            if target is not None:
                self.push_to_screen(target, item.path)

    # ── pushing media ─────────────────────────────────────────────────────────

    def _is_muted(self) -> bool:
        return self.mute_combo.currentIndex() == 1

    def push_to_screen(self, idx: int, path: str):
        if idx >= len(self.outputs) or idx == self._main_screen_idx:
            return
        self.outputs[idx].display(path, mute=self._is_muted())
        self.live_assignments[idx] = path
        self.screen_cards[idx].update_current(path)
        thumb = self.outputs[idx].get_thumbnail()
        if thumb:
            self.screen_cards[idx].set_preview(thumb)
        else:
            QTimer.singleShot(700, lambda i=idx: self._refresh_thumb(i))

    def _refresh_thumb(self, idx: int):
        if idx < len(self.outputs) and idx < len(self.screen_cards):
            thumb = self.outputs[idx].get_thumbnail()
            if thumb:
                self.screen_cards[idx].set_preview(thumb)

    def _refresh_all_thumbs(self):
        for i in range(len(self.outputs)):
            if i != self._main_screen_idx:
                self._refresh_thumb(i)

    def push_overlay_to_screen(self, idx: int, path: str):
        if idx >= len(self.outputs) or idx == self._main_screen_idx:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (IMAGE_EXT | GIF_EXT):
            QMessageBox.warning(self, "Overlay",
                                "Overlays must be image (.png/.jpg/…) or GIF files.")
            return
        self.outputs[idx].display_overlay(path)
        self.live_overlays[idx] = path
        self.screen_cards[idx].update_overlay_label(path)
        self._refresh_thumb(idx)

    def clear_overlay_screen(self, idx: int):
        if idx < len(self.outputs) and idx != self._main_screen_idx:
            self.outputs[idx].clear_overlay()
            self.live_overlays.pop(idx, None)
            self.screen_cards[idx].update_overlay_label(None)
            self._refresh_thumb(idx)

    def clear_screen(self, idx: int):
        if idx < len(self.outputs) and idx != self._main_screen_idx:
            self.outputs[idx].show_blank()
            self.live_assignments.pop(idx, None)
            self.live_overlays.pop(idx, None)
            self.screen_cards[idx].update_current(None)
            self.screen_cards[idx].update_overlay_label(None)
            self.screen_cards[idx].set_preview(None)

    def blank_all(self):
        for i in range(len(self.outputs)):
            self.clear_screen(i)

    # ── scenes ────────────────────────────────────────────────────────────────

    def _save_scene(self):
        if not self.live_assignments:
            QMessageBox.information(self, "Nothing to save",
                                    "Put something on a screen first.")
            return
        name, ok = QInputDialog.getText(self, "Save scene", "Scene name:")
        if not ok or not name.strip():
            return
        assignments   = {}
        rotations     = {}
        fill_modes    = {}
        grid_settings = {}
        placed_assets = {}
        for k, bg in self.live_assignments.items():
            ov = self.live_overlays.get(k, "")
            assignments[str(k)] = [bg, ov] if ov else [bg]
            if k < len(self.outputs):
                rotations[str(k)]  = self.outputs[k].rotation
                fill_modes[str(k)] = self.outputs[k].fill_mode
            gs = self.live_grid_settings.get(k)
            if gs:
                grid_settings[str(k)] = gs
            pa_list = self.live_placed_assets.get(k, [])
            if pa_list:
                placed_assets[str(k)] = [asdict(pa) for pa in pa_list
                                          if isinstance(pa, PlacedAsset)]
        self.scenes.append(Scene(
            name=name.strip(), assignments=assignments,
            rotations=rotations, fill_modes=fill_modes,
            grid_settings=grid_settings, placed_assets=placed_assets))
        self._refresh_scene_list()
        self._save_scenes()

    def _edit_scene(self):
        row = self.scene_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Edit scene", "Select a scene first.")
            return
        dlg = SceneEditorDialog(self.scenes[row], len(self.outputs), parent=self,
                                cards=self.cards)
        dlg.setStyleSheet("")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to_scene()
            self._refresh_scene_list()
            self._save_scenes()
            scene = self.scenes[row]
            for layers in scene.assignments.values():
                for p in (layers if isinstance(layers, list) else [layers]):
                    if p and os.path.exists(p):
                        self.add_media(p)

    def _delete_scene(self):
        row = self.scene_list.currentRow()
        if row < 0:
            return
        del self.scenes[row]
        self._refresh_scene_list()
        self._save_scenes()

    def _refresh_scene_list(self):
        self.scene_list.clear()
        for s in self.scenes:
            music_tag = " ♪" if s.music_path else ""
            self.scene_list.addItem(
                f"{s.name}  ({len(s.assignments)} screens){music_tag}")
        # Keep arcs consistent (new scenes join the last arc), then redraw tree
        store._ensure_structure(self._as_config())
        self.story_tree.refresh()

    def _activate_scene_item(self, item):
        self._activate_scene(self.scene_list.row(item))

    def _activate_scene(self, row: int):
        if row < 0 or row >= len(self.scenes):
            return
        screens_to_fade = [i for i in range(len(self.outputs))
                           if i != self._main_screen_idx]
        if screens_to_fade:
            pending = [len(screens_to_fade)]
            def on_all_faded():
                self._do_activate_scene(row)
                for i in screens_to_fade:
                    self.outputs[i].fade_from_black(TRANSITION_MS)
            def make_cb():
                def cb():
                    pending[0] -= 1
                    if pending[0] == 0:
                        on_all_faded()
                return cb
            for i in screens_to_fade:
                self.outputs[i].fade_to_black(TRANSITION_MS, make_cb())
        else:
            self._do_activate_scene(row)

    def _do_activate_scene(self, row: int):
        scene = self.scenes[row]
        used  = set()
        for k, layers in scene.assignments.items():
            idx  = int(k)
            used.add(idx)
            # Screens with "Show scenes" unchecked are left exactly as-is.
            if not self.screen_shows_scenes(idx):
                continue
            ls   = layers if isinstance(layers, list) else [layers]
            bg   = ls[0] if len(ls) > 0 else ""
            ov   = ls[1] if len(ls) > 1 else ""

            rot  = scene.rotations.get(k, 0)
            fill = scene.fill_modes.get(k, False)
            if idx < len(self.outputs):
                self.outputs[idx].set_rotation(rot)
                self.outputs[idx].set_fill_mode(fill)
            if idx < len(self.screen_cards):
                card = self.screen_cards[idx]
                card.rot_combo.blockSignals(True)
                card.rot_combo.setCurrentIndex(
                    [0, 90, 180, 270].index(rot) if rot in [0, 90, 180, 270] else 0)
                card.rot_combo.blockSignals(False)
                card.fill_combo.blockSignals(True)
                card.fill_combo.setCurrentIndex(1 if fill else 0)
                card.fill_combo.blockSignals(False)

            if bg:
                self.push_to_screen(idx, bg)
            if ov:
                self.push_overlay_to_screen(idx, ov)
            elif idx in self.live_overlays:
                self.clear_overlay_screen(idx)

            # Apply grid settings for this screen
            gs = dict(scene.grid_settings.get(k, {}))
            sz = self.screen_sizes.get(k, {})
            if sz:
                if not gs.get("screen_w_in"):
                    gs["screen_w_in"] = sz.get("w", 0.0)
                if not gs.get("screen_h_in"):
                    gs["screen_h_in"] = sz.get("h", 0.0)
            self.live_grid_settings[idx] = gs
            if idx < len(self.outputs):
                self.outputs[idx].apply_grid(gs)
            if idx < len(self.screen_cards):
                self.screen_cards[idx].update_grid_ui(gs, sz)

            # Restore placed assets for this screen
            pa_dicts = scene.placed_assets.get(k, [])
            pa_list  = []
            for pa_d in pa_dicts:
                try:
                    pa_list.append(PlacedAsset(**{
                        kk: vv for kk, vv in pa_d.items()
                        if kk in ("asset_path", "x", "y", "w", "h",
                                  "locked", "visible", "sound_path")}))
                except Exception:
                    pass
            self.live_placed_assets[idx] = pa_list
            if idx < len(self.outputs):
                self.outputs[idx].set_placed_assets(pa_list)

        for i in range(len(self.outputs)):
            if i not in used and self.screen_shows_scenes(i):
                self.clear_screen(i)
                if i < len(self.outputs):
                    self.outputs[i].clear_grid()
                    self.outputs[i].set_placed_assets([])
                self.live_grid_settings.pop(i, None)
                self.live_placed_assets[i] = []
                if i < len(self.screen_cards):
                    self.screen_cards[i].update_grid_ui({})

        self.scene_list.setCurrentRow(row)
        if scene.music_path and os.path.exists(scene.music_path):
            self._play_music_with_fade(scene.music_path)

        # Load the scene's cards into the map dock and refresh the HUD
        self.live_table_cards = [c for cid in scene.card_ids
                                 if (c := self.card_by_id(cid))]
        self.refresh_tabletops()

        # Scene lighting tint on map screens
        for idx, out in enumerate(self.outputs):
            if self.screen_shows_scenes(idx):
                out.set_lighting(scene.lighting)

        QTimer.singleShot(500, self._refresh_all_thumbs)
        QTimer.singleShot(1200, self._refresh_all_thumbs)
        QTimer.singleShot(1500, self._cache_current_scene_thumbnail)

    # ── story navigation (tree + carousel) ────────────────────────────────────

    def _open_carousel(self):
        if not self.scenes:
            QMessageBox.information(self, "Browse", "No scenes saved yet.")
            return
        SceneCarouselDialog(self, parent=self).exec()

    def _scene_row_by_id(self, scene_id: str) -> int:
        return next((i for i, s in enumerate(self.scenes) if s.id == scene_id), -1)

    def _activate_scene_by_id(self, scene_id: str):
        row = self._scene_row_by_id(scene_id)
        if row >= 0:
            self._activate_scene(row)

    def _activate_beat(self, scene_id: str, beat_idx: int):
        """Jump to a beat: activate its scene if needed, then apply the beat's
        notes / music / card overrides on top of the scene."""
        row = self._scene_row_by_id(scene_id)
        if row < 0:
            return
        if self.scene_list.currentRow() != row:
            self._activate_scene(row)
            QTimer.singleShot(TRANSITION_MS * 2 + 100,
                              lambda: self._apply_beat(row, beat_idx))
        else:
            self._apply_beat(row, beat_idx)

    def _apply_beat(self, row: int, beat_idx: int):
        if not (0 <= row < len(self.scenes)):
            return
        scene = self.scenes[row]
        if not (0 <= beat_idx < len(scene.beats)):
            return
        beat = scene.beats[beat_idx]
        get = beat.get if isinstance(beat, dict) else lambda k, d=None: getattr(beat, k, d)

        music = get("music_path")
        if music and os.path.exists(music):
            self._play_music_with_fade(music)

        notes = get("notes_html") or scene.notes_html
        card_ids = get("card_ids") or scene.card_ids
        self.live_table_cards = [c for cid in card_ids
                                 if (c := self.card_by_id(cid))]
        for idx, out in enumerate(self.outputs):
            if idx == self._main_screen_idx:
                continue
            if not self.screen_shows_hud(idx):
                continue
            out.tabletop.set_notes(notes)
            out.tabletop.set_cards(self.live_table_cards)
            out.set_lighting(get("lighting") or scene.lighting)
            if music:
                out.tabletop.set_track(music)

    # ── scene thumbnails (cached on disk for tree + carousel) ─────────────────

    def scene_thumbnail(self, scene):
        p = scene.thumbnail_path
        if p and os.path.exists(p):
            pix = QPixmap(p)
            if not pix.isNull():
                return pix
        return None

    def _cache_current_scene_thumbnail(self):
        """Snapshot the current scene from the first Player Map output and
        cache it to data/thumbs/{scene_id}.png. Called once after a scene has
        settled — never per paint (video snapshots are expensive)."""
        scene = self.current_scene()
        if scene is None:
            return
        for idx, out in enumerate(self.outputs):
            if idx == self._main_screen_idx:
                continue
            if not self.screen_shows_scenes(idx):
                continue
            frame = out.get_scene_frame(include_placed=True,
                                        target_size=QSize(px(320), px(180)))
            if frame and not frame.isNull():
                path = os.path.join(THUMBS_DIR, f"{scene.id}.png")
                if frame.save(path, "PNG"):
                    if scene.thumbnail_path != path:
                        scene.thumbnail_path = path
                        self._save_scenes()
                    self.story_tree.refresh()
            break

    def _step_scene(self, direction: int):
        if not self.scenes:
            return
        cur = self.scene_list.currentRow()
        nxt = max(0, min(len(self.scenes) - 1, cur + direction)) if cur >= 0 else 0
        self._activate_scene(nxt)

    # ── persistence ───────────────────────────────────────────────────────────

    def _as_config(self) -> store.Config:
        cfg = store.Config()
        cfg.screen_sizes    = self.screen_sizes
        cfg.main_screen_idx = self._main_screen_idx
        cfg.asset_library   = self.asset_library
        cfg.scenes          = self.scenes
        cfg.arcs            = self.arcs
        cfg.cards           = self.cards
        cfg.players         = self.players
        cfg.initiative      = self.initiative
        cfg.screen_flags    = self.screen_flags
        return cfg

    def _save_scenes(self):
        try:
            store.save_config(self._as_config())
        except Exception as e:
            print("Could not save scenes:", e)

    def _load_scenes(self):
        try:
            cfg = store.load_config()
        except Exception as e:
            print("Could not load scenes:", e)
            return
        try:
            self.screen_sizes  = cfg.screen_sizes
            self.asset_library = cfg.asset_library
            self.scenes        = cfg.scenes
            self.arcs          = cfg.arcs
            self.cards         = cfg.cards
            self.players       = cfg.players
            self.initiative    = cfg.initiative
            self.screen_flags = cfg.screen_flags

            saved_main = cfg.main_screen_idx
            if isinstance(saved_main, int) and saved_main < len(self.outputs):
                if saved_main != self._main_screen_idx:
                    old_main = self._main_screen_idx
                    self._main_screen_idx = saved_main
                    self.main_screen_combo.blockSignals(True)
                    self.main_screen_combo.setCurrentIndex(saved_main)
                    self.main_screen_combo.blockSignals(False)
                    for i, card in enumerate(self.screen_cards):
                        card.set_is_main(i == saved_main)
                    # Place the previously-skipped old main screen as an output
                    if old_main < len(self.outputs):
                        self.outputs[old_main].place_on_screen()
                    # Hide the new main screen's output window
                    self.outputs[saved_main].hide()
                    self._move_control_to_screen(saved_main)

            # Populate screen size spinboxes from saved global sizes
            for k, sz in self.screen_sizes.items():
                idx = int(k)
                if idx < len(self.screen_cards):
                    card = self.screen_cards[idx]
                    card._grid_w_spin.blockSignals(True)
                    card._grid_w_spin.setValue(sz.get("w", 27.0))
                    card._grid_w_spin.blockSignals(False)
                    card._grid_h_spin.blockSignals(True)
                    card._grid_h_spin.setValue(sz.get("h", 15.0))
                    card._grid_h_spin.blockSignals(False)

            for s in self.scenes:
                for layers in s.assignments.values():
                    for p in (layers if isinstance(layers, list) else [layers]):
                        if p and os.path.exists(p):
                            self.add_media(p)
            self._refresh_scene_list()
            self._sync_flag_checkboxes()
            self.refresh_tabletops()
        except Exception as e:
            print("Could not restore state:", e)

    # ── keyboard shortcuts ────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right:
            self._step_scene(1)
        elif event.key() == Qt.Key.Key_Left:
            self._step_scene(-1)
        elif event.key() == Qt.Key.Key_B:
            self.blank_all()
        else:
            super().keyPressEvent(event)

    def _confirm_exit(self):
        box = QMessageBox(self)
        box.setWindowTitle("Exit SceneCaster")
        box.setText("Close SceneCaster and all output screens?")
        box.setIcon(QMessageBox.Icon.Question)
        exit_b   = box.addButton("⏻  Exit", QMessageBox.ButtonRole.AcceptRole)
        cancel_b = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        # Big tap targets for the touch panel
        for b in (exit_b, cancel_b):
            if b:
                b.setMinimumSize(px(160), px(80))
        box.setDefaultButton(cancel_b)
        box.exec()
        if box.clickedButton() is exit_b:
            self.close()

    def closeEvent(self, event):
        for w in self.outputs:
            w.close()
        super().closeEvent(event)
