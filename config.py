import json
import os
import copy

CONFIG_FILE = "config.json"

# Configuración por defecto
DEFAULT_CONFIG = {
    "ultima_carpeta": "",
    "tema": "dark",  # valores esperados: "dark" o "light"
    "ultima_version_check": "",
}

def cargar_config():
    """Carga la configuración desde config.json o crea una por defecto."""
    if not os.path.exists(CONFIG_FILE):
        guardar_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Rellenar con valores por defecto si faltan claves
        for key, value in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = value

        return data
    except Exception as e:
        print(f"[Error] No se pudo leer config, cargando valores por defecto: {e}")
        return copy.deepcopy(DEFAULT_CONFIG)

def guardar_config(config):
    """Guarda la configuración en config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Error] No se pudo guardar config: {e}")
