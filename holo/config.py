# -*- coding: utf-8 -*-
"""Config loading, in one place.

Every front end used to resolve ``experiment_config.yaml`` its own way, which
is how the background modifier ended up defaulting to 1.0 in one path and 0.8
in another. Load it here.
"""

from pathlib import Path

import yaml

from .runtime import CONFIG_FILE


def default_path():
    """The config the app ships with / writes next to a frozen build."""
    return Path(CONFIG_FILE)


def load(path=None):
    """Read a config file into a dict. ``None`` means the default location."""
    p = Path(path) if path is not None else default_path()
    if not p.exists():
        raise FileNotFoundError(
            f"config not found: {p}\n"
            f"Pass --config, or copy experiment_config.yaml next to the app.")
    return yaml.safe_load(p.read_text()) or {}


def processing(config):
    """The ``processing:`` block, or an empty dict."""
    return (config or {}).get("processing") or {}


def multiport(config):
    """The ``processing.multiport:`` block -- this rig's fiber parameters.

    Deliberately separate from ``processing.core_radius``: the two disagree
    about the same physical lantern. See CLAUDE.md, "Two open physics
    questions".
    """
    return processing(config).get("multiport") or {}
