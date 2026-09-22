# utils.py
import os
import re
import socket

# Lista de extensiones conocidas para audio y video
KNOWN_EXTS = {
    "mp3",
    "m4a",
    "mp4",
    "wav",
    "flac",
    "aac",
    "alac",
    "wma",
    "aiff",
    "ogg",
    "webm",
    "mkv",
    "avi",
}


def limpiar_nombre_simple(nombre):
    """Elimina caracteres prohibidos en sistemas de archivos (Windows/Linux/Mac)

    y elimina espacios en blanco innecesarios al inicio/final.
    """
    if not nombre:
        return ""
    # Remover caracteres invalidos para nombres de archivo
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(nombre))
    # Limpiar espacios repetidos y de los extremos
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def strip_known_extension(name):
    """Remueve la extensión del nombre si coincide con la lista de formatos conocidos."""
    if not name:
        return ""
    base, ext = os.path.splitext(name)
    if ext:
        ext_clean = ext.lstrip(".").lower()
        if ext_clean in KNOWN_EXTS:
            return base
    return name


def tiene_conexion(host="8.8.8.8", port=53, timeout=3):
    """Verifica si hay conexión a internet activa.

    Por defecto utiliza el DNS de Google (8.8.8.8:53) que es más rápido
    y liviano que una resolución HTTP completa.
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except (socket.error, OSError):
        return False


def version_tuple(v):
    """Convierte un string de versión (ej: '1.2.3b') en una tupla de enteros (1, 2, 3)

    para permitir comparaciones numéricas directas.
    """
    parts = re.findall(r"\d+", str(v))
    return tuple(int(x) for x in parts) if parts else (0,)


def is_newer_version(remote, local):
    """Retorna True si la versión remota es numéricamente superior a la versión local."""
    return version_tuple(remote) > version_tuple(local)