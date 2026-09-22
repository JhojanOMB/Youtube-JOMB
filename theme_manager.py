# theme_manager.py
"""
Theme manager robusto para CustomTkinter.
Repara JSONs de tema incompletos (evita KeyError por claves nuevas)
y aplica fallbacks seguros. También carga/actualiza iconos.
"""

import json
import tempfile
import os
import traceback
from pathlib import Path
from PIL import Image, ImageOps

from consts import THEME_DARK_JSON, THEME_LIGHT_JSON, ICON_DIR

# ---------- Valores por defecto (seguros) ----------
def _default_values():
    return {
        "fg_color": ["#FFFFFF", "#EDEDED"],
        "fg_color2": ["#F7F7F7", "#EAEAEA"],
        "text_color": ["#000000", "#FFFFFF"],
        "text_color_disabled": ["#A0A0A0", "#7F7F7F"],
        "placeholder_text_color": ["#888888", "#AAAAAA"],
        "hover_color": ["#7E57C2", "#6C4AB6"],
        "button_color": ["#6C4AB6", "#7E57C2"],
        "button_hover_color": ["#5E35B1", "#5E35B1"],
        "entry_border_color": ["#633AA6", "#633AA6"],
        "progressbar_color": ["#7E57C2", "#7E57C2"],
        "menu_color": ["#E5E5E5", "#E5E5E5"],
        "indicator_color": ["#7E57C2", "#6C4AB6"],
        "select_color": ["#7E57C2", "#6C4AB6"],
        "border_color": ["#2E1636", "#2E1636"],
        "border_width": 2,
        "corner_radius": 8,
        "font": {"family": "Arial", "size": 13, "weight": "normal"},
    }

def _expected_widgets():
    # lista ampliada a widgets que suelen aparecer en distintas versiones
    return [
        "CTk", "CTkFrame", "CTkButton", "CTkLabel", "CTkEntry",
        "CTkProgressBar", "CTkComboBox", "CTkToplevel", "CTkScrollbar",
        "CTkCheckBox", "CTkRadioButton", "CTkFont",
        "CTkOptionMenu", "CTkSwitch", "DropdownMenu", "SegmentedButton",
        "CTkSlider", "CTkButtonMenu", "CTkTabview"
    ]

# ---------- Extraer la parte útil del JSON ----------
def _extract_primary_dict(raw):
    """
    Acepta varios formatos y devuelve el dict principal que contiene valores.
    """
    if raw is None:
        return {}
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        return {}

    # color_scheme variantes
    for key in ("color_scheme", "colorScheme", "colors"):
        if key in raw and isinstance(raw[key], dict):
            cs = raw[key]
            # Si dentro hay CTk
            if "CTk" in cs and isinstance(cs["CTk"], dict):
                return cs
            return cs

    if "CTk" in raw and isinstance(raw["CTk"], dict):
        return raw

    # fallback: buscar primer dict con keys de color
    for v in raw.values():
        if isinstance(v, dict) and ("fg_color" in v or "text_color" in v or "button_color" in v):
            return raw

    return raw

# ---------- Merge / reparación ----------
def _merge_defaults_into_widget(widget_dict, defaults, extra_keys_from_theme=None):
    """
    Rellena widget_dict con defaults y con keys encontradas en extra_keys_from_theme.
    Modifica in-place y devuelve widget_dict.
    """
    if not isinstance(widget_dict, dict):
        widget_dict = {}

    # propiedades comunes
    for k, v in (
        ("fg_color", defaults["fg_color"]),
        ("fg_color2", defaults["fg_color2"]),
        ("text_color", defaults["text_color"]),
        ("text_color_disabled", defaults["text_color_disabled"]),
        ("placeholder_text_color", defaults["placeholder_text_color"]),
        ("hover_color", defaults["hover_color"]),
        ("button_color", defaults["button_color"]),
        ("button_hover_color", defaults["button_hover_color"]),
        ("entry_border_color", defaults["entry_border_color"]),
        ("progressbar_color", defaults["progressbar_color"]),
        ("menu_color", defaults["menu_color"]),
        ("indicator_color", defaults["indicator_color"]),
        ("select_color", defaults["select_color"]),
        ("border_color", defaults["border_color"]),
    ):
        widget_dict.setdefault(k, v)

    widget_dict.setdefault("border_width", defaults["border_width"])
    widget_dict.setdefault("corner_radius", defaults["corner_radius"])

    # si ThemeManager.theme ya tiene claves explícitas (keys dinámicas), respetarlas o crearlas
    if isinstance(extra_keys_from_theme, dict):
        # añadir cualquier key presente en extra_keys_from_theme[w] si falta
        for extra_k, extra_v in extra_keys_from_theme.items():
            widget_dict.setdefault(extra_k, extra_v)

    return widget_dict

def _repair_theme_if_partial(theme_dict, ctk_theme_template=None):
    """
    Construye un theme completo a partir de theme_dict:
      - si theme_dict ya tiene CTk, lo toma como base
      - si no, usa la sección principal extraída y crea las keys esperadas
      - usa ctk_theme_template para conocer claves dinámicas existentes en la versión instalada
    Devuelve un dict listo para escribir en JSON y pasar a set_default_color_theme.
    """
    try:
        defaults = _default_values()
        expected = _expected_widgets()

        primary = _extract_primary_dict(theme_dict)

        # Si theme_dict ya es la estructura completa con CTk, usarla; si no, crear base.
        if isinstance(theme_dict, dict) and "CTk" in theme_dict and isinstance(theme_dict["CTk"], dict):
            base = dict(theme_dict)  # copia superficial para no mutar original
        else:
            base = {}
            # si primary tiene CTk internamente (p.ej. color_scheme con CTk), úsalo
            if isinstance(primary, dict) and "CTk" in primary and isinstance(primary["CTk"], dict):
                base = dict(primary)
            else:
                # construir base mínima con lo que tengamos
                base["CTk"] = dict(primary.get("CTk", {}) if isinstance(primary, dict) else {})
                # incorporar otras keys que existan en theme_dict
                if isinstance(theme_dict, dict):
                    for k, v in theme_dict.items():
                        if k not in base:
                            base[k] = v if isinstance(v, dict) else {}

        # preparar mapa con keys adicionales por widget tomadas de ctk_theme_template si existe
        extra_keys_map = {}
        if isinstance(ctk_theme_template, dict):
            for w in expected:
                # tomar keys del template para w si existen
                tpl = ctk_theme_template.get(w)
                if isinstance(tpl, dict):
                    extra_keys_map[w] = {}
                    for kk, vv in tpl.items():
                        # si es un valor simple, usar como fallback genérico
                        extra_keys_map[w][kk] = vv

        # Asegurar todas las widgets esperadas
        for w in expected:
            if w not in base or not isinstance(base[w], dict):
                # usar CTk como plantilla si existe
                template = base.get("CTk", {}) if isinstance(base.get("CTk", {}), dict) else {}
                base[w] = dict(template)

            if w == "CTkFont":
                # aseguramos las keys de fuente
                font_defaults = defaults["font"].copy()
                fe = base.get("CTkFont", {})
                if not isinstance(fe, dict):
                    fe = {}
                for fk, fv in font_defaults.items():
                    fe.setdefault(fk, fv)
                base["CTkFont"] = fe
                continue

            # mezclar defaults + posibles keys extra desde el template de ctk
            _merge_defaults_into_widget(base[w], defaults, extra_keys_map.get(w))

            # Por si aparecen keys nuevas en el JSON original (ej: top_fg_color), preservarlas:
            if isinstance(theme_dict, dict) and w in theme_dict and isinstance(theme_dict[w], dict):
                for key_k, key_v in theme_dict[w].items():
                    base[w].setdefault(key_k, key_v)

        # Además, conservar cualquier otra key del JSON original que sea dict
        if isinstance(theme_dict, dict):
            for k, v in theme_dict.items():
                if k not in base and isinstance(v, dict):
                    base[k] = v

        return base

    except Exception:
        # si algo falla, devolver un theme mínimo seguro
        defaults = _default_values()
        return {
            "CTk": {
                "fg_color": defaults["fg_color"],
                "text_color": defaults["text_color"],
            },
            "CTkFont": defaults["font"]
        }

# ---------- Aplicación segura del theme ----------
def safe_set_default_color_theme(ctk, theme_ref):
    """
    Intenta aplicar theme_ref (ruta o nombre builtin). Si es archivo JSON lo repara
    y lo aplica temporalmente. Devuelve True si ThemeManager.theme contiene al menos 'CTk'.
    """
    try:
        if not isinstance(theme_ref, str):
            return False

        def _theme_has_minimum():
            try:
                tm = getattr(ctk, "ThemeManager", None)
                theme_obj = getattr(tm, "theme", None)
                return isinstance(theme_obj, dict) and "CTk" in theme_obj
            except Exception:
                return False

        # obtener plantilla actual de ThemeManager (si existe) para rellenar claves dinámicas
        ctk_template = None
        try:
            tm = getattr(ctk, "ThemeManager", None)
            if tm is not None:
                current_theme = getattr(tm, "theme", None)
                if isinstance(current_theme, dict):
                    ctk_template = current_theme
        except Exception:
            ctk_template = None

        # Si es un archivo JSON, leer y reparar
        if os.path.isfile(theme_ref):
            try:
                with open(theme_ref, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                return False

            if isinstance(data, list) and data:
                data = data[0]

            repaired = _repair_theme_if_partial(data if isinstance(data, dict) else {}, ctk_theme_template=ctk_template)

            # guardar temporal y aplicar
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
            json.dump(repaired, tf, indent=2, ensure_ascii=False)
            tf_path = tf.name
            tf.close()

            try:
                ctk.set_default_color_theme(tf_path)
            except Exception:
                # no crash: intentaremos fallbacks
                pass
            try:
                os.unlink(tf_path)
            except Exception:
                pass

            if _theme_has_minimum():
                return True

        else:
            # no es archivo: intentar aplicar por nombre (built-in)
            try:
                ctk.set_default_color_theme(theme_ref)
                if _theme_has_minimum():
                    return True
            except Exception:
                pass

        # fallbacks built-in
        for fb in ("dark-blue", "green", "blue", "light"):
            try:
                ctk.set_default_color_theme(fb)
                if _theme_has_minimum():
                    return True
            except Exception:
                continue

        return False

    except Exception:
        print("safe_set_default_color_theme error:", traceback.format_exc())
        return False

def apply_theme_from_config(ctk, config):
    """
    Aplica modo (Oscuro/Claro) según config y luego intenta aplicar theme JSON reparamos.
    """
    try:
        mode = config.get("theme") if isinstance(config, dict) else "Oscuro"
        mode_norm = "Oscuro" if str(mode).lower().startswith("o") else "Claro"
        if mode_norm == "Oscuro":
            try:
                ctk.set_appearance_mode("dark")
            except:
                pass
            if not safe_set_default_color_theme(ctk, THEME_DARK_JSON):
                try:
                    ctk.set_default_color_theme("dark-blue")
                except:
                    pass
        else:
            try:
                ctk.set_appearance_mode("light")
            except:
                pass
            if not safe_set_default_color_theme(ctk, THEME_LIGHT_JSON):
                try:
                    ctk.set_default_color_theme("light")
                except:
                    pass
    except Exception:
        print("apply_theme_from_config error:", traceback.format_exc())
        try:
            ctk.set_appearance_mode("dark")
            try:
                ctk.set_default_color_theme("dark-blue")
            except:
                pass
        except:
            pass

# ---------- Icon loader y refresco (similar al original, más tolerante) ----------
def _current_theme_name(ctk=None):
    try:
        if ctk:
            mode = ctk.get_appearance_mode()
        else:
            mode = os.environ.get("CUSTOMTKINTER_APPEARANCE_MODE", "dark")
        return "light" if str(mode).lower().startswith("l") else "dark"
    except Exception:
        return "dark"

def load_icon_for(name, size=(28, 28), ctk=None):
    """
    Busca iconos en ICON_DIR/<tema>/name.(png|jpg|svg) y luego en ICON_DIR/name.*
    Retorna (ctk_image, used_path) o (None, None).
    """
    def _pil_to_ctk(pil_img, out_size):
        try:
            pil_img = pil_img.convert("RGBA")
            pil_img = ImageOps.fit(pil_img, out_size, Image.Resampling.LANCZOS)
            if ctk:
                return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=out_size)
            return pil_img
        except Exception:
            return None

    theme = _current_theme_name(ctk)
    candidates = []
    for ext in (".png", ".jpg", ".jpeg"):
        candidates.append(os.path.join(str(ICON_DIR), theme, f"{name}{ext}"))
    candidates.append(os.path.join(str(ICON_DIR), theme, f"{name}.svg"))
    for ext in (".png", ".jpg", ".jpeg"):
        candidates.append(os.path.join(str(ICON_DIR), f"{name}{ext}"))
    candidates.append(os.path.join(str(ICON_DIR), f"{name}.svg"))

    for path in candidates:
        try:
            if not path or not os.path.exists(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in (".png", ".jpg", ".jpeg"):
                try:
                    img = Image.open(path)
                    ctk_img = _pil_to_ctk(img, size)
                    if ctk_img:
                        return ctk_img, path
                except Exception:
                    continue
            elif ext == ".svg":
                try:
                    import cairosvg
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                    tf.close()
                    try:
                        cairosvg.svg2png(url=path, write_to=tf.name, output_width=size[0], output_height=size[1])
                        img = Image.open(tf.name)
                        ctk_img = _pil_to_ctk(img, size)
                        try:
                            os.unlink(tf.name)
                        except:
                            pass
                        if ctk_img:
                            return ctk_img, path
                        else:
                            continue
                    except Exception:
                        try:
                            os.unlink(tf.name)
                        except:
                            pass
                        continue
                except Exception:
                    try:
                        img = Image.open(path)
                        ctk_img = _pil_to_ctk(img, size)
                        if ctk_img:
                            return ctk_img, path
                        else:
                            continue
                    except Exception:
                        continue
        except Exception:
            continue

    return None, None

def refresh_ui_icons(ctk, widgets_map=None):
    """
    Recarga iconos según tema y los aplica.
    widgets_map: dict opcional con claves p.ej. {'gear_btn': widget_obj, 'ttkwindow': window_obj}
    """
    try:
        if widgets_map is None:
            widgets_map = {}
        gear_btn = widgets_map.get('gear_btn')
        ttkwindow = widgets_map.get('ttkwindow')

        img, used = load_icon_for("configuracion", size=(28, 28), ctk=ctk)
        if not img:
            img, used = load_icon_for("gear", size=(28, 28), ctk=ctk)

        if gear_btn:
            try:
                if img:
                    gear_btn.configure(image=img, text="")
                    try:
                        gear_btn.image = img
                    except Exception:
                        pass
                else:
                    gear_btn.configure(image=None, text="⚙")
            except Exception:
                pass

        theme_name = _current_theme_name(ctk)
        ico_candidates = [
            Path(ICON_DIR) / theme_name / "jomb.ico",
            Path(ICON_DIR) / "jomb.ico",
            Path(ICON_DIR) / theme_name / "icono.png",
            Path(ICON_DIR) / "icono.png",
        ]

        for p in ico_candidates:
            try:
                if not isinstance(p, Path):
                    p = Path(str(p))
                if not p.exists():
                    continue
                if ttkwindow is None:
                    break
                p_str = str(p)
                if p_str.lower().endswith(".ico"):
                    try:
                        ttkwindow.iconbitmap(p_str)
                    except Exception:
                        try:
                            from tkinter import PhotoImage
                            tkimg = PhotoImage(file=p_str)
                            ttkwindow.iconphoto(False, tkimg)
                            setattr(ttkwindow, "_icon_img", tkimg)
                        except Exception:
                            pass
                else:
                    try:
                        from tkinter import PhotoImage
                        tkimg = PhotoImage(file=p_str)
                        ttkwindow.iconphoto(False, tkimg)
                        setattr(ttkwindow, "_icon_img", tkimg)
                    except Exception:
                        pass
                break
            except Exception:
                continue

    except Exception as e:
        # no romper la app por errores de iconos
        print("theme_manager.refresh_ui_icons error:", e)
