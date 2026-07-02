"""Persistence: load / save / migrate the scenes JSON config.

Schema v2 adds top-level keys: version, arcs, cards, players, initiative,
monitor_roles. v1 files (no "version" key, or a bare list of scenes) are
migrated in memory on load; a .bak copy of the original is written once so
nothing is lost the first time a v2 save overwrites it.
"""

import json
import os
import shutil
from dataclasses import asdict, fields

from realmweaver.theme import CONFIG_FILE
from realmweaver.models import (
    Scene, AssetItem, Arc, Card, PlayerPlate, InitiativeEntry, new_id,
)

# Per-screen feature switches. Everything defaults to "scenes on, HUD off":
# a screen shows scene media unless the user unchecks it, and never shows
# HUD overlays unless the user checks it. No implicit coupling between them.
DEFAULT_FLAGS = {"scenes": True, "hud": False}

CONFIG_VERSION = 2


def _from_dict(cls, d: dict):
    """Defensive dataclass construction: ignore unknown keys so configs
    written by newer/older versions never crash the loader."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})


class Config:
    """In-memory representation of the whole saved state."""

    def __init__(self):
        self.screen_sizes: dict = {}
        self.main_screen_idx: int = 0
        self.asset_library: list[AssetItem] = []
        self.scenes: list[Scene] = []
        self.arcs: list[Arc] = []
        self.cards: list[Card] = []
        self.players: list[PlayerPlate] = []
        self.initiative: list[InitiativeEntry] = []
        self.screen_flags: dict = {}   # str(screen_idx) -> {"scenes": bool, "hud": bool}


def load_config(path: str = CONFIG_FILE) -> Config:
    cfg = Config()
    if not os.path.exists(path):
        return cfg
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # Oldest format: a bare list of scenes
    if isinstance(raw, list):
        raw = {"scenes": raw}

    is_v1 = raw.get("version", 1) < 2
    if is_v1:
        _backup_once(path)

    cfg.screen_sizes    = raw.get("screen_sizes", {})
    cfg.main_screen_idx = raw.get("main_screen_idx", 0)

    for a in raw.get("asset_library", []):
        try:
            ai = _from_dict(AssetItem, a)
            if os.path.exists(ai.path):
                cfg.asset_library.append(ai)
        except Exception:
            pass

    for d in raw.get("scenes", []):
        try:
            assignments = d.get("assignments", {})
            for k, v in assignments.items():
                if isinstance(v, str):
                    assignments[k] = [v]
            d["assignments"] = assignments
            scene = _from_dict(Scene, d)
            if not scene.id:
                scene.id = new_id()
            cfg.scenes.append(scene)
        except Exception:
            pass

    for d in raw.get("arcs", []):
        try:
            cfg.arcs.append(_from_dict(Arc, d))
        except Exception:
            pass
    for d in raw.get("cards", []):
        try:
            cfg.cards.append(_from_dict(Card, d))
        except Exception:
            pass
    for d in raw.get("players", []):
        try:
            cfg.players.append(_from_dict(PlayerPlate, d))
        except Exception:
            pass
    for d in raw.get("initiative", []):
        try:
            cfg.initiative.append(_from_dict(InitiativeEntry, d))
        except Exception:
            pass

    flags = raw.get("screen_flags", {})
    if flags:
        cfg.screen_flags = {str(k): {"scenes": bool(v.get("scenes", True)),
                                     "hud": bool(v.get("hud", False))}
                            for k, v in flags.items() if isinstance(v, dict)}
    else:
        # Migrate the old role model: player_map showed scenes, everything
        # else didn't; HUD was global so it starts off everywhere.
        for k, role in raw.get("monitor_roles", {}).items():
            cfg.screen_flags[str(k)] = {"scenes": role == "player_map",
                                        "hud": False}

    _ensure_structure(cfg)
    return cfg


def save_config(cfg: Config, path: str = CONFIG_FILE):
    _ensure_structure(cfg)
    data = {
        "version":         CONFIG_VERSION,
        "screen_sizes":    cfg.screen_sizes,
        "main_screen_idx": cfg.main_screen_idx,
        "screen_flags":    cfg.screen_flags,
        "asset_library":   [asdict(a) for a in cfg.asset_library],
        "scenes":          [asdict(s) for s in cfg.scenes],
        "arcs":            [asdict(a) for a in cfg.arcs],
        "cards":           [asdict(c) for c in cfg.cards],
        "players":         [asdict(p) for p in cfg.players],
        "initiative":      [asdict(i) for i in cfg.initiative],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _backup_once(path: str):
    bak = path + ".bak"
    if not os.path.exists(bak):
        try:
            shutil.copyfile(path, bak)
        except Exception as e:
            print("Could not back up config:", e)


def _ensure_structure(cfg: Config):
    """Every scene must have an id and belong to exactly one arc; roles must
    cover only known values. Called on load and save so state self-heals."""
    for s in cfg.scenes:
        if not s.id:
            s.id = new_id()
    known = {s.id for s in cfg.scenes}
    seen: set = set()
    for arc in cfg.arcs:
        arc.scene_ids = [sid for sid in arc.scene_ids
                         if sid in known and sid not in seen]
        seen.update(arc.scene_ids)
    orphans = [s.id for s in cfg.scenes if s.id not in seen]
    if orphans:
        if not cfg.arcs:
            cfg.arcs.append(Arc(name="Arc I", scene_ids=orphans))
        else:
            cfg.arcs[-1].scene_ids.extend(orphans)
