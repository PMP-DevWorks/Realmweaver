#!/usr/bin/env python3
"""
SceneCaster — Multi-screen storytelling display controller
============================================================

Launch shim. The application code lives in the realmweaver/ package:

    realmweaver/theme.py            colors, DPI scaling, paths
    realmweaver/models.py           Scene / AssetItem / PlacedAsset dataclasses
    realmweaver/media.py            media helpers, library tiles, file dialogs
    realmweaver/output/             per-monitor fullscreen output windows
    realmweaver/widgets/            asset library, props, screen cards, minimap
    realmweaver/dialogs/            scene editor
    realmweaver/control_window.py   main control panel
    realmweaver/app.py              entry point

RUN:
    python Realmweaver.py
"""

from realmweaver.app import main

if __name__ == "__main__":
    main()
