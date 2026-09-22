# -*- coding: utf-8 -*-
"""
config.py - gestión robusta de configuración para Youtube-JOMB

Características:
- Ubicación consistente del archivo config (AppData / ~/.youtube_jomb).
- Normaliza claves legacy (tema / tema_oscuro / ultima_carpeta, etc).
- Escritura atómica y thread-safe.
- Funciones públicas: cargar_config(), guardar_config()
- Alias de compatibilidad: cargar_config_compatible(), guardar_config_compatible()
"""

import json
import os
import copy
import tempfile
import threading
import platform

# ------------------- Parámetros -------------------
APP_NAME = "Youtube-JOMB"

# Calcula carpeta de almacenamiento (igual que en youtube.py)
def _get_storage_dir():
    try:
        if platform.system().lower().startswith("win"):
            base = os.getenv("APPDATA") or os.path.expanduser("~")
            d = os.path.join(base, APP_NAME)
        else:
            d = os.path.join(os.path.expanduser("~"), ".youtube_jomb")
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return os.getcwd()

CONFIG_FILE = os.path.join(_get_storage_dir(), "config.json")

# Config canónica (a usar por la app)
DEFAULT_CONFIG = {
    "last_folder": "",
    "theme": "Oscuro",            # valores: "Oscuro" o "Claro"
    "ultima_version_check": ""
}

_lock = threading.Lock()

# ------------------- Helpers -------------------
def _normalize_theme_value(v):
    """Normaliza varias posibles representaciones del tema a 'Oscuro' o 'Claro'."""
    if not v:
        return DEFAULT_CONFIG["theme"]
    s = str(v).strip().lower()
    if s in ("dark", "d", "oscuro", "o", "darkmode", "dark-mode"):
        return "Oscuro"
    if s in ("light", "l", "claro", "c", "lightmode", "light-mode"):
        return "Claro"
    # fallback: si contiene 'o' asume oscuro, si contiene 'l' asume claro
    if "oscuro" in s or "dark" in s or s.startswith("o"):
        return "Oscuro"
    if "claro" in s or "light" in s or s.startswith("l"):
        return "Claro"
    return DEFAULT_CONFIG["theme"]

def _atomic_write(path, data_str):
    """
    Escribe data_str a path de forma atómica usando un tempfile + os.replace.
    Garantiza que no quede archivo parcial si falla.
    """
    dirn = os.path.dirname(os.path.abspath(path)) or "."
    # aseguramos que exista el directorio
    os.makedirs(dirn, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dirn, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data_str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise

# ------------------- API pública -------------------
def cargar_config():
    """
    Carga y normaliza la configuración.
    - Si el archivo no existe, lo crea con valores por defecto.
    - Acepta claves legacy y devuelve un dict canónico con keys:
        - last_folder
        - theme (Oscuro/Claro)
        - ultima_version_check
    """
    # Si no existe, crear con default
    if not os.path.exists(CONFIG_FILE):
        try:
            guardar_config(DEFAULT_CONFIG)
        except Exception:
            # no fallar si no se pudo escribir
            pass
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        # si el JSON está corrupto, avisamos por consola y devolvemos defaults
        print(f"[config] Error leyendo {CONFIG_FILE}, usando valores por defecto: {e}")
        return copy.deepcopy(DEFAULT_CONFIG)

    out = DEFAULT_CONFIG.copy()

    if isinstance(raw, dict):
        # last_folder (legacy: ultima_carpeta)
        if raw.get("last_folder"):
            out["last_folder"] = raw.get("last_folder") or ""
        elif raw.get("ultima_carpeta"):
            out["last_folder"] = raw.get("ultima_carpeta") or ""

        # theme (legacy: tema, theme)
        if "theme" in raw:
            out["theme"] = _normalize_theme_value(raw.get("theme"))
        elif "tema" in raw:
            out["theme"] = _normalize_theme_value(raw.get("tema"))
        elif "Theme" in raw:
            out["theme"] = _normalize_theme_value(raw.get("Theme"))

        # ultima_version_check (legacy: last_version_check)
        if "ultima_version_check" in raw:
            out["ultima_version_check"] = raw.get("ultima_version_check") or ""
        elif "last_version_check" in raw:
            out["ultima_version_check"] = raw.get("last_version_check") or ""

    # Intentamos reescribir la config normalizada (silencioso)
    try:
        guardar_config(out)
    except Exception:
        pass

    return out

def guardar_config(cfg):
    """
    Guarda la configuración de forma atómica y thread-safe.
    Espera un dict (puede contener keys legacy; se normalizan).
    """
    if not isinstance(cfg, dict):
        raise TypeError("guardar_config espera un dict")

    save_obj = {
        "last_folder": cfg.get("last_folder") or cfg.get("ultima_carpeta") or "",
        "theme": _normalize_theme_value(cfg.get("theme") or cfg.get("tema") or cfg.get("Theme")),
        "ultima_version_check": cfg.get("ultima_version_check") or cfg.get("last_version_check") or ""
    }

    json_str = json.dumps(save_obj, indent=2, ensure_ascii=False)
    with _lock:
        # backup opcional del anterior
        try:
            if os.path.exists(CONFIG_FILE):
                try:
                    os.replace(CONFIG_FILE, CONFIG_FILE + ".bak")
                except Exception:
                    # si no se pudo renombrar, no es crítico
                    pass
        except Exception:
            pass

        # escritura atómica
        _atomic_write(CONFIG_FILE, json_str)

# ------------------- Alias de compatibilidad -------------------
# muchos de tus módulos ya importan cargar_config / guardar_config
cargar_config_compatible = cargar_config
guardar_config_compatible = guardar_config

# exportar nombres en español (idénticos) — conveniente para imports
# (esto mantiene compatibilidad con código que usaba esos nombres)
__all__ = [
    "cargar_config",
    "guardar_config",
    "cargar_config_compatible",
    "guardar_config_compatible",
    "CONFIG_FILE",
    "DEFAULT_CONFIG",
    "APP_NAME"
]
