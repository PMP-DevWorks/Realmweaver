"""Data models for scenes, assets, placed props, cards, and story structure."""

import uuid
from dataclasses import dataclass, field
from typing import Optional


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class SceneBeat:
    """A moment within a scene — narrower than a scene change (notes swap,
    music cue, a card revealed) but still a step in the story timeline."""
    name: str
    notes_html: str = ""
    card_ids: list = field(default_factory=list)
    music_path: Optional[str] = None
    lighting: Optional[dict] = None   # {"tint": "#332200", "opacity": 0.3}


@dataclass
class Scene:
    name: str
    assignments: dict   = field(default_factory=dict)
    music_path: Optional[str] = None
    rotations: dict     = field(default_factory=dict)
    fill_modes: dict    = field(default_factory=dict)
    grid_settings: dict = field(default_factory=dict)
    placed_assets: dict = field(default_factory=dict)  # str(idx) -> list of PlacedAsset dicts
    id: str = ""
    beats: list = field(default_factory=list)          # list of SceneBeat dicts
    notes_html: str = ""
    card_ids: list = field(default_factory=list)       # cards on the table for this scene
    thumbnail_path: Optional[str] = None
    lighting: Optional[dict] = None                    # {"tint": "#332200", "opacity": 0.3}


@dataclass
class Arc:
    """A story arc grouping scenes in play order."""
    name: str
    scene_ids: list = field(default_factory=list)


@dataclass
class Card:
    """An item / NPC / handout card: portrait plus rich-text stat block."""
    name: str
    id: str = field(default_factory=new_id)
    portrait_path: Optional[str] = None
    body_html: str = ""            # rich text (QTextDocument HTML)
    tags: list = field(default_factory=list)
    rarity: str = "common"         # common | uncommon | rare | legendary
    charges: Optional[int] = None
    kind: str = "item"             # item | npc | handout


@dataclass
class PlayerPlate:
    player_name: str
    character_name: str
    portrait_path: Optional[str] = None
    edge: str = "bottom"           # top | bottom | left | right


@dataclass
class InitiativeEntry:
    name: str
    value: int
    is_current: bool = False


@dataclass
class AssetItem:
    path: str
    size_w: float = 0.15       # fraction of screen width (0.0–1.0)
    size_h: float = 0.15       # fraction of screen height (0.0–1.0)
    sound_path: Optional[str] = None
    effect: Optional[str] = None


@dataclass
class PlacedAsset:
    asset_path: str
    x: float = 0.5            # center x, 0.0–1.0 relative to screen
    y: float = 0.5            # center y, 0.0–1.0 relative to screen
    w: float = 0.15           # width, 0.0–1.0 relative to screen
    h: float = 0.15           # height, 0.0–1.0 relative to screen
    locked: bool = False
    visible: bool = True      # False = greyed + red-X overlay
    sound_path: Optional[str] = None


# Monitor roles
ROLE_PLAYER_MAP  = "player_map"
ROLE_PLAYER_INFO = "player_info"
ROLE_DM_SCREEN   = "dm_screen"
ROLE_OFF         = "off"
ROLES = (ROLE_PLAYER_MAP, ROLE_PLAYER_INFO, ROLE_DM_SCREEN, ROLE_OFF)
ROLE_LABELS = {
    ROLE_PLAYER_MAP:  "Player Map",
    ROLE_PLAYER_INFO: "Player Info",
    ROLE_DM_SCREEN:   "DM Screen",
    ROLE_OFF:         "Off",
}
