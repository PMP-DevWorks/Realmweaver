"""Story outline sidebar: Arc > Scene > Beat tree with thumbnails."""

import os

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QInputDialog, QMessageBox,
)

from realmweaver import theme
from realmweaver.theme import (
    px, pt, _touch_scroll, make_accent,
    C_VOID, C_CARD, C_HOVER, C_BORDER, C_ACCENT_GOLD, C_ACCENT_PURPLE,
    C_TEXT_PARCH, C_TEXT_RUNE,
)
from realmweaver.models import Arc

KIND_ARC, KIND_SCENE, KIND_BEAT = "arc", "scene", "beat"


class StoryOutlineSidebar(QWidget):
    """Hierarchical Arc > Scene > Beat outline. Activating a scene or beat
    fires the corresponding signal; the controller does the heavy lifting."""

    scene_activated = pyqtSignal(str)        # scene_id
    beat_activated  = pyqtSignal(str, int)   # scene_id, beat index

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(px(6))

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(px(72), px(40)))
        self.tree.setIndentation(px(18))
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {C_VOID}; color: {C_TEXT_PARCH};
                border: 1px solid {C_BORDER}; border-radius: {px(8)}px;
                font-size: {pt(10)}pt;
            }}
            QTreeWidget::item {{
                min-height: {px(56)}px; padding: {px(4)}px;
                border-radius: {px(6)}px;
            }}
            QTreeWidget::item:selected {{
                background: {C_CARD}; color: {C_ACCENT_GOLD};
                border-left: 3px solid {C_ACCENT_GOLD};
            }}
            QTreeWidget::item:hover:!selected {{ background: {C_HOVER}; }}
        """)
        _touch_scroll(self.tree)
        self.tree.itemDoubleClicked.connect(self._on_item_activated)
        lay.addWidget(self.tree, 1)

        row = QHBoxLayout()
        row.setSpacing(px(6))
        add_arc = QPushButton("+ Arc")
        add_arc.clicked.connect(self._add_arc)
        ren = QPushButton("Rename")
        ren.clicked.connect(self._rename)
        row.addWidget(add_arc)
        row.addWidget(ren)
        lay.addLayout(row)

    # ── refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        self.tree.clear()
        scenes_by_id = {s.id: s for s in self.controller.scenes}
        current = self.controller.current_scene()
        for arc in self.controller.arcs:
            arc_item = QTreeWidgetItem([arc.name.upper()])
            arc_item.setData(0, Qt.ItemDataRole.UserRole, (KIND_ARC, arc))
            f = arc_item.font(0)
            f.setBold(True)
            arc_item.setFont(0, f)
            arc_item.setForeground(0, self.tree.palette().brush(
                self.tree.foregroundRole()))
            self.tree.addTopLevelItem(arc_item)
            for sid in arc.scene_ids:
                scene = scenes_by_id.get(sid)
                if scene is None:
                    continue
                s_item = QTreeWidgetItem([scene.name])
                s_item.setData(0, Qt.ItemDataRole.UserRole, (KIND_SCENE, scene))
                thumb = self._thumb_icon(scene)
                if thumb:
                    s_item.setIcon(0, thumb)
                arc_item.addChild(s_item)
                if scene is current:
                    self.tree.setCurrentItem(s_item)
                for bi, beat in enumerate(scene.beats):
                    bname = beat.get("name") if isinstance(beat, dict) else beat.name
                    b_item = QTreeWidgetItem([f"· {bname}"])
                    b_item.setData(0, Qt.ItemDataRole.UserRole,
                                   (KIND_BEAT, (scene, bi)))
                    s_item.addChild(b_item)
            arc_item.setExpanded(True)

    def _thumb_icon(self, scene):
        p = scene.thumbnail_path
        if p and os.path.exists(p):
            pix = QPixmap(p)
            if not pix.isNull():
                return QIcon(pix)
        return None

    # ── interaction ───────────────────────────────────────────────────────────

    def _on_item_activated(self, item, _col):
        kind, payload = item.data(0, Qt.ItemDataRole.UserRole)
        if kind == KIND_SCENE:
            self.scene_activated.emit(payload.id)
        elif kind == KIND_BEAT:
            scene, bi = payload
            self.beat_activated.emit(scene.id, bi)

    def _selected(self):
        item = self.tree.currentItem()
        if item is None:
            return None, None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _add_arc(self):
        name, ok = QInputDialog.getText(self, "New Arc", "Arc name:")
        if ok and name.strip():
            self.controller.arcs.append(Arc(name=name.strip()))
            self.controller._save_scenes()
            self.refresh()

    def _rename(self):
        kind, payload = self._selected()
        if kind == KIND_ARC:
            name, ok = QInputDialog.getText(self, "Rename Arc", "Name:",
                                            text=payload.name)
            if ok and name.strip():
                payload.name = name.strip()
        elif kind == KIND_SCENE:
            name, ok = QInputDialog.getText(self, "Rename Scene", "Name:",
                                            text=payload.name)
            if ok and name.strip():
                payload.name = name.strip()
        else:
            return
        self.controller._save_scenes()
        self.controller._refresh_scene_list()
