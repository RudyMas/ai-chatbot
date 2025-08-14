from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Optional
from bot.config import load_config, get_system_template_path, AppConfig

ROOT = Path(__file__).parents[2]
CONFIG_DIR = ROOT / "config"
PROFILES_DIR = CONFIG_DIR / "profiles"

def list_profiles() -> List[str]:
    """Return profile names (without .yaml) found in config/profiles/."""
    if not PROFILES_DIR.exists():
        return []
    names = []
    for p in PROFILES_DIR.glob("*.yaml"):
        names.append(p.stem)
    return sorted(names)

def resolve_profile_path(profile: Optional[str]) -> Path:
    """
    Resolve a profile name or path to an actual YAML file.
    Rules:
      - None or "default" -> config/default.yaml
      - name without extension -> config/profiles/<name>.yaml if exists; else config/<name>.yaml
      - absolute/relative path -> use directly if exists
    """
    if not profile or profile == "default":
        return CONFIG_DIR / "default.yaml"

    p = Path(profile)
    if p.suffix.lower() in (".yml", ".yaml"):
        if p.is_file():
            return p.resolve()
        # allow relative to config/
        if (CONFIG_DIR / p).is_file():
            return (CONFIG_DIR / p).resolve()
        raise FileNotFoundError(f"Profile file not found: {profile}")

    # treat as bare name
    candidate = PROFILES_DIR / f"{profile}.yaml"
    if candidate.is_file():
        return candidate.resolve()
    candidate2 = CONFIG_DIR / f"{profile}.yaml"
    if candidate2.is_file():
        return candidate2.resolve()

    raise FileNotFoundError(f"Profile '{profile}' not found in {PROFILES_DIR} or {CONFIG_DIR}")

def load_profile(profile: Optional[str]) -> Tuple[AppConfig, dict, Path]:
    """Load a profile and return (AppConfig, raw_yaml_dict, system_template_path)."""
    cfg_path = resolve_profile_path(profile)
    app_cfg, raw = load_config(cfg_path)
    template_path = get_system_template_path(cfg_path, raw)
    return app_cfg, raw, template_path
