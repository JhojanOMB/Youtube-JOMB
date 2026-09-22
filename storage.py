# storage.py
import os, platform, json
from consts import ICON_DIR

def get_storage_dir():
    try:
        if platform.system().lower().startswith("win"):
            base = os.getenv("APPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "Youtube-JOMB")
        else:
            d = os.path.join(os.path.expanduser("~"), ".youtube_jomb")
        os.makedirs(d, exist_ok=True)
        return d
    except:
        return os.getcwd()

STORAGE_DIR = get_storage_dir()
CONFIG_PATH = os.path.join(STORAGE_DIR, "config.json")

DEFAULT_CONFIG = {
    "theme": "Oscuro",
    "last_folder": ""
}

def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
                out = DEFAULT_CONFIG.copy()
                out.update(c)
                return out
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def get_last_folder(cfg):
    if not isinstance(cfg, dict): return ""
    return cfg.get("last_folder") or cfg.get("ultima_carpeta") or ""

def set_last_folder(cfg, path):
    if not isinstance(cfg, dict):
        cfg = {}
    cfg["last_folder"] = path or ""
    cfg["ultima_carpeta"] = path or ""
    save_config(cfg)
    return cfg

def load_app_state():
    """Alias para que gui.py pueda cargar la configuración sin fallar."""
    return load_config()

def save_app_state(state):
    """Alias para que gui.py pueda guardar el estado sin fallar."""
    if isinstance(state, dict):
        return save_config(state)
    return False