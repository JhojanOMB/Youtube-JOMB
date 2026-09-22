# consts.py 
import os, sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # ejecutable PyInstaller: recursos están en _MEIPASS
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

ICON_DIR = BASE_DIR / "iconos"

# --- Repo / nombre (útil para fallback en importlib.metadata) ---
GITHUB_REPO = "JhojanOMB/Youtube-JOMB"

# --- Otras constantes del proyecto ---
THEME_DARK_JSON = "temas/tema_oscuro.json"
THEME_LIGHT_JSON = "temas/tema_claro.json"
KNOWN_EXTS = [
    "mp3","m4a","mp4","wav","flac","aac","alac",
    "wma","aiff","ogg","webm","mkv","avi"
]

# ------------------ Búsqueda robusta de la carpeta de iconos ------------------
def _exists_icon(p: Path, required_file="configuracion.png"):
    try:
        return p.is_dir() and (p / required_file).exists()
    except Exception:
        return False

def find_icon_dir():
    # 1) Override por variable de entorno (más fiable para instaladores)
    env = os.environ.get("JOMB_ICON_DIR") or os.environ.get("JOMB_ICONS_DIR")
    if env:
        p = Path(env)
        if _exists_icon(p):
            return p

    # 2) Rutas candidatas inmediatas
    candidates = [
        BASE_DIR / "iconos",
        BASE_DIR.parent / "iconos",   # carpeta arriba (p. ej. proyecto padre)
        Path.cwd() / "iconos",        # carpeta iconos en working dir
    ]
    for c in candidates:
        if _exists_icon(c):
            return c

    # 3) Buscar hacia arriba desde BASE_DIR y desde cwd (hasta 6 niveles)
    for start in (BASE_DIR, Path.cwd()):
        p = start
        for _ in range(6):
            cand = p / "iconos"
            if _exists_icon(cand):
                return cand
            if p.parent == p:
                break
            p = p.parent

    # 4) Buscar recursivamente una carpeta 'iconos' dentro del árbol cercano (BASE_DIR.parents[0:4])
    #    (útil cuando la estructura de carpetas cambió y la carpeta está en un subproyecto)
    try:
        # limitar la búsqueda para no recorrer todo el disco: buscar solo dentro de 3 niveles por encima
        search_start = BASE_DIR
        for root_candidate in [search_start, search_start.parent, search_start.parent.parent]:
            if root_candidate is None:
                continue
            for p in root_candidate.rglob("iconos"):
                if _exists_icon(p):
                    return p
    except Exception:
        pass

    # 5) Si no la encontramos: fallback a BASE_DIR/"iconos" (crearla si es posible)
    fallback = BASE_DIR / "iconos"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return fallback

ICON_DIR = find_icon_dir()
# Para debugging descomentar la siguiente línea:
# print("DEBUG: ICON_DIR resolved to:", ICON_DIR.resolve())
# --------------------------------------------------------------------


# ------------------ Lectura robusta de la versión local ------------------
def _read_version_from_file(path: Path):
    try:
        if path.is_file():
            txt = path.read_text(encoding="utf-8").strip()
            if txt:
                return txt
    except Exception:
        pass
    return None

def _search_version_upwards(start: Path, max_levels: int = 4):
    p = start
    for i in range(max_levels + 1):
        ver = _read_version_from_file(p / "VERSION")
        if ver:
            return ver
        p = p.parent
    return None

def _try_importlib_resources(pkg_name: str):
    try:
        import importlib.resources as resources
        if pkg_name:
            try:
                f = resources.files(pkg_name).joinpath("VERSION")
                if f.is_file():
                    return f.read_text(encoding="utf-8").strip() or None
            except Exception:
                pass
    except Exception:
        pass
    return None

def _try_importlib_metadata(dist_name_hint: str):
    """
    Intenta obtener la versión a través de importlib.metadata.
    Maneja los distintos imports (stdlib en py>=3.8 o backport).
    """
    # intentar importar la implementación estándar o el backport
    metadata = None
    try:
        from importlib import metadata as importlib_metadata  # Py3.8+
        metadata = importlib_metadata
    except Exception:
        try:
            import importlib
            importlib_metadata = importlib.import_module("importlib_metadata")
            metadata = importlib_metadata
        except Exception:
            metadata = None

    if metadata is None:
        return None

    # Construir candidatos razonables para el nombre del paquete
    candidates = []
    base = (dist_name_hint or "").lower().replace("_", "-")
    if base:
        candidates.extend([base, base.replace("-", "_"), base.replace("-", "")])
    # también intentar con nombre exacto derivado del repo
    try:
        candidates.append(GITHUB_REPO.split("/")[-1])
    except Exception:
        pass

    # Probar candidatos; capturar PackageNotFoundError
    for cand in dict.fromkeys(candidates):
        try:
            # metadata.version lanza PackageNotFoundError si no existe
            v = metadata.version(cand)
            if v:
                return v
        except Exception as e:
            # no queremos detener la búsqueda por un error; simplemente seguir
            # si quieres depurar, descomenta la linea siguiente temporalmente:
            # print(f"metadata.version('{cand}') -> {e}")
            continue
    return None

# 1) Prioridad 1: variable de entorno (útil para instaladores / CI)
LOCAL_VERSION = os.environ.get("JOMB_LOCAL_VERSION") or os.environ.get("APP_VERSION")
if LOCAL_VERSION:
    LOCAL_VERSION = str(LOCAL_VERSION).strip()

if not LOCAL_VERSION:
    # 2) Prioridad 2: archivo VERSION al lado del módulo (o en padres)
    LOCAL_VERSION = _search_version_upwards(BASE_DIR, max_levels=4)

if not LOCAL_VERSION:
    # 3) Prioridad 3: como recurso empaquetado (si incluiste VERSION en package_data)
    pkg_name = __package__
    if not pkg_name:
        pkg_name = GITHUB_REPO.split("/")[-1].lower().replace("-", "_")
    LOCAL_VERSION = _try_importlib_resources(pkg_name)

if not LOCAL_VERSION:
    # 4) Prioridad 4: metadatos instalados (si el paquete fue instalado con pip)
    dist_hint = GITHUB_REPO.split("/")[-1]
    LOCAL_VERSION = _try_importlib_metadata(dist_hint)

# 5) Fallback final
if not LOCAL_VERSION:
    LOCAL_VERSION = "0.0.0"
