# -*- coding: utf-8 -*-
# youtube.py - Descargador de YouTube - JOMB
# Ajustado: "Guardar como" usa título original, guarda solo tema y última carpeta.
import os
import sys
import json
import tempfile
import imageio_ffmpeg as ffmpeg
import subprocess
from pytubefix import YouTube
import webbrowser
import re
import urllib.request
from io import BytesIO
from PIL import Image, ImageOps
import socket
import time
import threading
import platform
import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox, PhotoImage, Toplevel
from config import cargar_config, guardar_config

from mutagen import File
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TDRC, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

# ---------------- Config ----------------
config = cargar_config()
GITHUB_REPO = "JhojanOMB/Youtube-JOMB"
VERSION_FILE = "VERSION"
THEME_DARK_JSON = "temas/tema_morado.json"
ICON_DIR = "iconos"  # carpeta de iconos
# ----------------------------------------------------------------

# ---------------- Appearance / UI constants ----------------
APPEARANCE_DARK = "dark"
APPEARANCE_LIGHT = "light"

PAD_X = 12
PAD_Y = 8
ENTRY_H = 38
BTN_H = 36
THUMB_SIZE = 140

# ---------------- Storage y config ----------------
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
    "theme": "Oscuro",     # "Oscuro" o "Claro"
    "last_folder": ""      # última carpeta seleccionada
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
    except Exception as e:
        print("No se pudo guardar config:", e)

config = load_config()

# ---------------- Appearance init ----------------
try:
    if config.get("theme", "Oscuro") == "Oscuro":
        ctk.set_appearance_mode(APPEARANCE_DARK)
        if os.path.exists(THEME_DARK_JSON):
            ctk.set_default_color_theme(THEME_DARK_JSON)
        else:
            ctk.set_default_color_theme("dark-blue")
    else:
        ctk.set_appearance_mode(APPEARANCE_LIGHT)
except Exception:
    ctk.set_appearance_mode(APPEARANCE_DARK)
    ctk.set_default_color_theme("dark-blue")

# ----------------------------------------------------------------
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
formato_audio_preferido = 'mp3'
formato_video_preferido = 'mp4'

# Utility: evitar ventana consola en subprocess en Windows
NO_CONSOLE = 0x08000000 if platform.system().lower().startswith("win") else 0

def tiene_conexion():
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        return True
    except:
        return False

# ---------------- Version local (robusto) ----------------
def get_local_version():
    candidates = []
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, VERSION_FILE))
    except:
        pass
    try:
        argv0_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        candidates.append(os.path.join(argv0_dir, VERSION_FILE))
    except:
        pass
    candidates.append(os.path.join(os.getcwd(), VERSION_FILE))
    try:
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(os.path.join(meipass, VERSION_FILE))
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            candidates.append(os.path.join(exe_dir, VERSION_FILE))
    except:
        pass
    for p in candidates:
        try:
            if p and os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                    if v:
                        return v
        except:
            continue
    return "0.0.0"

LOCAL_VERSION = get_local_version()

def version_tuple(v):
    parts = re.findall(r'\d+', str(v))
    return tuple(int(x) for x in parts) if parts else (0,)

def is_newer_version(remote, local):
    return version_tuple(remote) > version_tuple(local)

# ---------------- Utilidades (conversión / metadatos / miniatura) ----------------
def on_progress(stream, chunk, bytes_remaining):
    try:
        total = getattr(stream, "filesize", 0)
        downloaded = total - bytes_remaining if total else 0
        percent = (downloaded / total * 100) if total else 0
        try:
            progress_bar.set(percent/100.0)
            status_label.configure(text=f"Descargando... {percent:.1f}%")
        except:
            pass
    except Exception:
        pass

def limpiar_nombre_simple(nombre):
    return re.sub(r'[<>:"/\\|?*]', '', str(nombre) if nombre else '')

def convertir(input_path, output_path, bitrate=None):
    try:
        target_ext = os.path.splitext(output_path)[1].lstrip('.').lower()
        cmd = [ffmpeg_path, '-y', '-i', input_path]
        if target_ext == 'mp3':
            cmd += ['-vn', '-c:a', 'libmp3lame']
            if bitrate:
                cmd += ['-b:a', bitrate]
        elif target_ext in ('m4a', 'mp4', 'aac', 'alac'):
            cmd += ['-vn', '-c:a', 'aac']
            if bitrate:
                cmd += ['-b:a', bitrate]
        else:
            cmd += ['-vn']
            if bitrate:
                cmd += ['-b:a', bitrate]
        cmd.append(output_path)
        run_kwargs = {"check": True}
        if NO_CONSOLE:
            run_kwargs["creationflags"] = NO_CONSOLE
        subprocess.run(cmd, **run_kwargs)
        try: os.remove(input_path)
        except: pass
    except subprocess.CalledProcessError as e:
        mostrar_error(f"Fallo en conversión:\n{e}")
        raise

def parse_artist_title(title, author=None):
    if not title:
        return (None, author)
    seps = [' - ', ' — ', ' – ', ' | ']
    for sep in seps:
        if sep in title:
            left, right = title.split(sep, 1)
            if len(left.split()) <= 5:
                return (right.strip(), left.strip())
            else:
                return (left.strip(), right.strip())
    m = re.search(r'^(?P<title>.+)\s+[bB]y\s+(?P<artist>.+)$', title)
    if m:
        return (m.group('title').strip(), m.group('artist').strip())
    return (title.strip(), author)

def agregar_metadatos_y_miniatura(out_file, yt_obj, img_data=None, title_override=None, artist_override=None):
    try:
        lower = out_file.lower()
        title_val = title_override if title_override else getattr(yt_obj, 'title', None)
        artist_val = artist_override if artist_override else getattr(yt_obj, 'author', None)
        publish = getattr(yt_obj, 'publish_date', None)
        if lower.endswith('.mp3'):
            try:
                tags = ID3(out_file)
            except ID3NoHeaderError:
                tags = ID3()
            if title_val:
                try: tags.delall('TIT2')
                except: pass
                tags.add(TIT2(encoding=3, text=title_val))
            if artist_val:
                try: tags.delall('TPE1')
                except: pass
                tags.add(TPE1(encoding=3, text=artist_val))
            if publish:
                try: tags.delall('TDRC')
                except: pass
                tags.add(TDRC(encoding=3, text=str(publish)))
            if img_data:
                try: tags.delall('APIC')
                except: pass
                tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data))
            tags.save(out_file, v2_version=3)
            return "Metadatos y miniatura agregados a MP3."
        elif lower.endswith('.flac'):
            audio = FLAC(out_file)
            if title_val: audio['title'] = title_val
            if artist_val: audio['artist'] = artist_val
            if publish: audio['date'] = str(publish)
            if img_data:
                pic = Picture(); pic.data = img_data; pic.type = 3; pic.mime = "image/jpeg"
                audio.add_picture(pic)
            audio.save()
            return "Metadatos y miniatura agregados a FLAC."
        elif lower.endswith(('.m4a', '.mp4', '.aac', '.alac')):
            audio = MP4(out_file)
            if title_val: audio['\xa9nam'] = [title_val]
            if artist_val: audio['\xa9ART'] = [artist_val]
            if publish: audio['\xa9day'] = [str(publish)]
            if img_data:
                audio.tags['covr'] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
            return "Metadatos y miniatura agregados a M4A/MP4."
        else:
            return "Formato no soportado para metadatos/miniatura."
    except Exception as e:
        return f"No se pudo agregar metadatos: {e}"

def fetch_best_thumbnail(yt_obj):
    try:
        pr = getattr(yt_obj, "player_response", None)
        if pr and isinstance(pr, dict):
            thumbs = pr.get('videoDetails', {}).get('thumbnail', {}).get('thumbnails', [])
            if thumbs:
                thumbs_sorted = sorted(thumbs, key=lambda x: x.get('width', 0), reverse=True)
                for t in thumbs_sorted:
                    url = t.get('url')
                    if url:
                        try:
                            with urllib.request.urlopen(url, timeout=6) as u:
                                return u.read()
                        except:
                            continue
    except Exception:
        pass
    base = getattr(yt_obj, "thumbnail_url", None) or getattr(yt_obj, "thumbnail", None)
    if base:
        candidates = []
        if "hqdefault" in base:
            candidates = [base.replace('hqdefault', 'maxresdefault'),
                          base.replace('hqdefault', 'sddefault'),
                          base]
        else:
            candidates = [base]
        for url in candidates:
            try:
                with urllib.request.urlopen(url, timeout=6) as u:
                    data = u.read()
                    if len(data) > 1024:
                        return data
            except:
                continue
    try:
        video_id = getattr(yt_obj, "video_id", None)
        if video_id:
            for suf in ("maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg"):
                url = f"https://img.youtube.com/vi/{video_id}/{suf}"
                try:
                    with urllib.request.urlopen(url, timeout=6) as u:
                        data = u.read()
                        if len(data) > 1024:
                            return data
                except:
                    continue
    except Exception:
        pass
    return None

# ---------------- Mensajes ----------------
def mostrar_error(mensaje, title="Error"):
    try:
        top = Toplevel()
        top.withdraw()
        try:
            icon_path = os.path.join(ICON_DIR, "icono.png")
            if os.path.exists(icon_path):
                icon = PhotoImage(file=icon_path)
                top.iconphoto(False, icon)
        except:
            pass
        messagebox.showerror(title, mensaje, parent=top)
        top.destroy()
    except:
        messagebox.showerror(title, mensaje)

def mostrar_info(mensaje, title="Éxito"):
    try:
        top = Toplevel()
        top.withdraw()
        try:
            icon_path = os.path.join(ICON_DIR, "icono.png")
            if os.path.exists(icon_path):
                icon = PhotoImage(file=icon_path)
                top.iconphoto(False, icon)
        except:
            pass
        messagebox.showinfo(title, mensaje, parent=top)
        top.destroy()
    except:
        messagebox.showinfo(title, mensaje)

# ---------------- Guardar/cargar última carpeta (persistida en config) ----------------
def guardar_ultima_carpeta(path):
    try:
        config["last_folder"] = path or ""
        save_config(config)
    except Exception as e:
        print("No se pudo guardar la última carpeta en config:", e)

def cargar_ultima_carpeta():
    try:
        return config.get("last_folder", "") or ""
    except:
        return ""

# ---------------- GitHub updates helpers (iguales) ----------------
def get_github_latest_release(repo, token=None):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f"token {token}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def find_installer_asset(release_json):
    if not release_json:
        return (None, None)
    assets = release_json.get('assets', [])
    for a in assets:
        name = a.get('name', '') or ''
        if name.lower().endswith('.exe'):
            return (a.get('name'), a.get('browser_download_url'))
    return (None, None)

def download_file_with_progress(url, dest_path, status_label_obj=None, progress_bar_obj=None):
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        chunk_size = 8192
        downloaded = 0
        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and progress_bar_obj:
                        try:
                            progress_bar_obj.set(min(downloaded/total, 1.0))
                        except:
                            pass
                    if status_label_obj:
                        try:
                            pct = (downloaded/total*100) if total else 0
                            status_label_obj.configure(text=f"Descargando actualización... {pct:.1f}%")
                        except:
                            pass

# threaded check wrapper
def check_for_updates_background(show_ui=True):
    try:
        if not tiene_conexion():
            if show_ui:
                try: status_label.configure(text="Sin conexión para verificar actualizaciones")
                except: pass
            return
        token = os.environ.get("GITHUB_TOKEN")
        release = get_github_latest_release(GITHUB_REPO, token=token)
        if not release:
            if show_ui:
                try: status_label.configure(text="No se pudo consultar actualizaciones.")
                except: pass
            return
        tag_name = release.get('tag_name') or release.get('name') or ''
        remote_version = tag_name.lstrip('vV') if tag_name else release.get('name','0.0.0')
        if is_newer_version(remote_version, LOCAL_VERSION):
            if show_ui:
                ask = messagebox.askyesno("Actualización disponible",
                                        f"Hay una nueva versión disponible: {remote_version}\nTu versión: {LOCAL_VERSION}\n\n¿Deseas descargar e instalar ahora?")
            else:
                ask = True
            if not ask:
                try: status_label.configure(text=f"Actualización disponible: {remote_version}")
                except: pass
                return
            asset_name, download_url = find_installer_asset(release)
            if not download_url:
                expected = f"YouTubeDownloaderSetup_{remote_version}.exe"
                for a in release.get('assets', []):
                    if a.get('name') == expected:
                        download_url = a.get('browser_download_url')
                        asset_name = a.get('name')
                        break
            if not download_url:
                if show_ui:
                    messagebox.showinfo("Actualización",
                                        "Se encontró una versión más reciente pero no se encontró un instalador .exe en los assets del release.")
                try: status_label.configure(text="Actualización disponible pero sin instalador .exe")
                except: pass
                return
            try:
                tmp_dir = tempfile.gettempdir()
                dest_path = os.path.join(tmp_dir, asset_name or f"update_{remote_version}.exe")
                try:
                    status_label.configure(text="Descargando instalador...")
                    progress_bar.set(0.0)
                except:
                    pass
                download_file_with_progress(download_url, dest_path, status_label_obj=status_label, progress_bar_obj=progress_bar)
                try:
                    status_label.configure(text="Descarga completada. Lanzando instalador...")
                except:
                    pass
                if platform.system().lower().startswith("win"):
                    try:
                        os.startfile(dest_path)
                    except Exception:
                        subprocess.Popen([dest_path], shell=True)
                else:
                    try:
                        if platform.system().lower() == "darwin":
                            subprocess.Popen(["open", dest_path])
                        else:
                            subprocess.Popen(["xdg-open", dest_path])
                    except Exception:
                        if show_ui:
                            messagebox.showinfo("Instalador descargado", f"Instalador descargado en:\n{dest_path}\nEjecuta manualmente para actualizar.")
                if show_ui:
                    if messagebox.askyesno("Instalador lanzado", "Se lanzó el instalador. ¿Deseas cerrar la aplicación para continuar con la instalación?"):
                        ttkwindow.after(200, ttkwindow.destroy)
                return
            except Exception as e:
                if show_ui:
                    mostrar_error(f"No se pudo descargar/ejecutar instalador:\n{e}")
                else:
                    try: status_label.configure(text="Error descargando instalador")
                    except: pass
                return
        else:
            if show_ui:
                messagebox.showinfo("Actualizaciones", f"Estás en la última versión ({LOCAL_VERSION}).")
            try: status_label.configure(text=f"Versión actual: {LOCAL_VERSION}")
            except: pass
            return
    except Exception as e:
        if show_ui:
            print("Error checking updates:", e)
            try: status_label.configure(text="Error comprobando actualizaciones")
            except: pass

def check_for_updates_threaded(show_ui=True):
    t = threading.Thread(target=check_for_updates_background, args=(show_ui,), daemon=True)
    t.start()

# ---------------- descarga principal (threaded con save-as) ----------------
KNOWN_EXTS = ['mp3','m4a','mp4','wav','flac','aac','alac','wma','aiff','ogg','webm','mkv','avi']

def strip_known_extension(name):
    if not name:
        return name
    base, ext = os.path.splitext(name)
    if ext:
        ext_clean = ext.lstrip('.').lower()
        if ext_clean in KNOWN_EXTS:
            return base
    return name

# Debounce / state para cargar formatos
_last_fetch_ts = 0
user_edited = {'val': False}
programmatic_set = {'val': False}

def set_save_as_programmatic(val):
    programmatic_set['val'] = True
    val_clean = strip_known_extension(limpiar_nombre_simple(val))
    save_as_var.set(val_clean)
    programmatic_set['val'] = False

def _on_save_as_changed(*args):
    if not programmatic_set['val']:
        current = save_as_var.get() or ""
        stripped = strip_known_extension(current)
        if stripped != current:
            programmatic_set['val'] = True
            save_as_var.set(stripped)
            programmatic_set['val'] = False
        user_edited['val'] = True

def update_default_filename_from_original(original_title):
    """Establece 'Guardar como' con el título original (quitando chars inválidos).
        Si el usuario editó manualmente, solo se actualiza si es una nueva búsqueda.
    """
    if not original_title:
        return
    base = limpiar_nombre_simple(original_title).strip()
    if not base:
        base = "video"
    if not user_edited['val']:  # solo si no está marcado como editado manual
        set_save_as_programmatic(base)

# ---------------- cargar formatos (auto-fetch con debounce) ----------------
def cargar_formatos(debounce_ms=600):
    global _last_fetch_ts
    now = time.time() * 1000
    if now - _last_fetch_ts < debounce_ms:
        return
    _last_fetch_ts = now

    if not tiene_conexion():
        mostrar_error("No hay conexión a Internet. Por favor verifica tu red Wi-Fi o datos móviles.")
        return

    # bloqueamos inputs visualmente
    entry_url.configure(state='disabled')
    tipo_combo.configure(state='disabled')
    formato_combo.configure(state='disabled')
    calidad_combo.configure(state='disabled')
    bt_elegir.configure(state='disabled')
    btn.configure(state='disabled')

    url = url_var.get().strip()
    tipo = tipo_var.get().strip().lower()
    if not url:
        mostrar_error("Ingresa una URL.")
        entry_url.configure(state='normal')
        tipo_combo.configure(state='normal')
        return

    try:
        yt_temp = YouTube(url)
    except Exception as e:
        mostrar_error(f"URL inválida:\n{e}")
        entry_url.configure(state='normal')
        tipo_combo.configure(state='normal')
        return

    # título original
    original_title = getattr(yt_temp, 'title', None)
    # actualizamos "guardar como" con el título original si el usuario no lo editó
    update_default_filename_from_original(original_title)

    # --- Miniatura (cuadrada, fit) ---
    try:
        img_data = fetch_best_thumbnail(yt_temp)
        if img_data:
            img = Image.open(BytesIO(img_data)).convert("RGBA")
            img = ImageOps.fit(img, (THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(THUMB_SIZE, THUMB_SIZE))
            thumbnail_label.configure(image=ctk_img)
            thumbnail_label.image = ctk_img
        else:
            placeholder = Image.new("RGBA", (THUMB_SIZE, THUMB_SIZE), (44, 16, 46, 255))
            ctk_img = ctk.CTkImage(light_image=placeholder, dark_image=placeholder, size=(THUMB_SIZE, THUMB_SIZE))
            thumbnail_label.configure(image=ctk_img)
            thumbnail_label.image = ctk_img
    except Exception as e:
        print("Error cargando miniatura:", e)

    formatos_video = set()
    formatos_audio = set()
    calis = set()

    for f in yt_temp.streams:
        mime = getattr(f, 'mime_type', '') or ''
        ext = mime.split('/')[-1] if mime else ''
        is_video = (hasattr(f, 'resolution') and getattr(f, 'resolution')) or mime.startswith('video')
        is_audio = (hasattr(f, 'abr') and getattr(f, 'abr')) or mime.startswith('audio')

        if tipo == 'video':
            if not is_video:
                continue
            if hasattr(f, 'resolution') and getattr(f, 'resolution'):
                calis.add(getattr(f, 'resolution'))
            if ext:
                formatos_video.add(ext)
            else:
                fname = getattr(f, 'default_filename', '') or ''
                if fname and '.' in fname:
                    formatos_video.add(fname.split('.')[-1])
        else:  # audio
            vcodec = getattr(f, 'vcodec', None)
            is_audio_by_vcodec = (str(vcodec).lower() == 'none') if vcodec is not None else False
            if not (is_audio or is_audio_by_vcodec):
                fname = getattr(f, 'default_filename', '') or ''
                if fname and fname.lower().endswith(('.m4a', '.mp3', '.aac', '.flac')):
                    pass
                else:
                    continue
            if hasattr(f, 'abr') and getattr(f, 'abr'):
                calis.add(getattr(f, 'abr'))
            if ext:
                formatos_audio.add('m4a' if ext == 'mp4' else ext)
            else:
                fname = getattr(f, 'default_filename', '') or ''
                if fname and '.' in fname:
                    formatos_audio.add(fname.split('.')[-1])

    if tipo == 'audio':
        formatos_audio.update(['mp3', 'wav', 'aiff', 'flac', 'alac', 'wma'])

    formatos = formatos_video if tipo == 'video' else formatos_audio
    formato_list = sorted(formatos)

    formato_combo.configure(values=formato_list, state='normal' if formato_list else 'disabled')
    if formato_list:
        if tipo == 'audio' and formato_audio_preferido in formato_list:
            formato_var.set(formato_audio_preferido)
        elif tipo == 'video' and formato_video_preferido in formato_list:
            formato_var.set(formato_video_preferido)
        else:
            formato_var.set(formato_list[0])
    else:
        formato_var.set('')

    def sort_key_cal(c):
        s = str(c)
        nums = re.sub(r'[^0-9]', '', s)
        try:
            return int(nums)
        except:
            return 0

    calidad_list = sorted([c for c in calis], key=sort_key_cal)
    if tipo == 'video':
        calidad_combo.configure(values=calidad_list, state='normal' if calidad_list else 'disabled')
        if calidad_list:
            calidad_var.set(calidad_list[-1])
    else:
        calidad_combo.configure(values=calidad_list, state='normal' if calidad_list else 'disabled')
        if calidad_list:
            calidad_var.set('320kbps' if '320kbps' in calidad_list else calidad_list[-1])

    bt_elegir.configure(state='normal')
    btn.configure(state='normal')
    try:
        status_label.configure(text="Formatos, calidades y miniatura listos.")
    except:
        pass
    entry_url.configure(state='normal')
    tipo_combo.configure(state='normal')

def elegir_ubicacion():
    carpeta = filedialog.askdirectory()
    if carpeta:
        ubicacion_var.set(carpeta)
        guardar_ultima_carpeta(carpeta)

# --------------------- UI --------------------
ttkwindow = ctk.CTk()
ttkwindow.title("Descargador de YouTube - JOMB")

# ventana icon
try:
    ico_path = os.path.join(ICON_DIR, "jomb.ico")
    icono_path = os.path.join(ICON_DIR, "icono.png")
    if os.path.exists(ico_path):
        ttkwindow.iconbitmap(ico_path)
    elif os.path.exists(icono_path):
        img = PhotoImage(file=icono_path)
        ttkwindow.iconphoto(False, img)
except:
    pass

# layout root responsive
ttkwindow.rowconfigure(0, weight=1)
ttkwindow.columnconfigure(0, weight=1)
ttkwindow.geometry("840x600")
ttkwindow.minsize(720, 520)

# Variables
url_var = ctk.StringVar()
tipo_var = ctk.StringVar(value="Audio")
formato_var = ctk.StringVar()
calidad_var = ctk.StringVar()
ubicacion_var = ctk.StringVar(value=cargar_ultima_carpeta() or "")
progress_var = ctk.DoubleVar(value=0.0)
save_as_var = ctk.StringVar()
save_as_var.trace_add("write", _on_save_as_changed)

# Main frame — use grid
frame = ctk.CTkFrame(ttkwindow, corner_radius=12)
frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=(32,18))
frame.columnconfigure(0, weight=0, minsize=150)
frame.columnconfigure(1, weight=3)
frame.columnconfigure(2, weight=1)
frame.columnconfigure(3, weight=3)
frame.columnconfigure(4, weight=0, minsize=THUMB_SIZE+24)
frame.columnconfigure(5, weight=0, minsize=48)
for r in range(16):
    frame.rowconfigure(r, weight=0)
frame.rowconfigure(8, weight=1)
frame.rowconfigure(14, weight=1)

# Header: centered title
title_label = ctk.CTkLabel(frame, text="Descargador de YouTube", font=ctk.CTkFont(size=20, weight="bold"))
title_label.grid(row=0, column=1, columnspan=3, pady=(0,14))

# Gear icon button
gear_img = None
gear_path = os.path.join(ICON_DIR, "configuracion.png")
try:
    if os.path.exists(gear_path):
        gimg = Image.open(gear_path).convert("RGBA")
        gimg = ImageOps.fit(gimg, (28, 28), Image.Resampling.LANCZOS)
        gear_img = ctk.CTkImage(light_image=gimg, dark_image=gimg, size=(18,18))
except:
    gear_img = None

settings_window = None

def open_settings():
    global settings_window
    try:
        if settings_window is not None and settings_window.winfo_exists():
            try:
                settings_window.lift(); settings_window.focus_force()
            except:
                pass
            return
    except:
        settings_window = None

    try:
        settings_window = ctk.CTkToplevel(ttkwindow)
    except:
        settings_window = Toplevel(ttkwindow)
    settings_window.title("Configuración")
    settings_window.geometry("420x340")
    settings_window.transient(ttkwindow)
    try:
        x = ttkwindow.winfo_rootx(); y = ttkwindow.winfo_rooty()
        settings_window.geometry("+%d+%d" % (x + 80, y + 60))
    except:
        pass

    def _on_close():
        try: settings_window.destroy()
        except: pass
        finally:
            nonlocal_ref_clear()

    def nonlocal_ref_clear():
        global settings_window
        settings_window = None

    settings_window.protocol("WM_DELETE_WINDOW", _on_close)

    # -------------------------
    # Info versión local
    # -------------------------
    ctk.CTkLabel(settings_window, text=f"Versión local: {LOCAL_VERSION}", anchor="w").pack(fill="x", padx=12, pady=(12,6))

    # -------------------------
    # Selector de tema
    # -------------------------
    ctk.CTkLabel(settings_window, text="Tema:").pack(fill="x", padx=12, pady=(8,0))
    theme_var_local = ctk.StringVar(value=config.get("theme", "Oscuro"))

    def apply_theme_local():
        v = theme_var_local.get()
        config["theme"] = v
        save_config(config)
        if v == "Oscuro":
            ctk.set_appearance_mode(APPEARANCE_DARK)
            if os.path.exists(THEME_DARK_JSON):
                ctk.set_default_color_theme(THEME_DARK_JSON)
        else:
            ctk.set_appearance_mode(APPEARANCE_LIGHT)
            ctk.set_default_color_theme(THEME_LIGHT)

    theme_box = ctk.CTkComboBox(settings_window, values=["Oscuro", "Claro"], variable=theme_var_local)
    theme_box.pack(fill="x", padx=12, pady=(4,6))
    apply_theme_btn = ctk.CTkButton(settings_window, text="Aplicar tema", command=apply_theme_local)
    apply_theme_btn.pack(padx=12, pady=(6,10))

    # -------------------------
    # Botón de actualización
    # -------------------------
    def check_update():
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            ultima_version = data.get("tag_name", "").replace("v", "")

            if not ultima_version:
                messagebox.showwarning("Actualización", "No se pudo obtener la versión más reciente.")
                return

            if ultima_version != LOCAL_VERSION:
                if messagebox.askyesno("Actualización disponible",
                    f"Hay una nueva versión ({ultima_version}).\n\n¿Quieres descargarla ahora?"):
                    webbrowser.open(data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"))
            else:
                messagebox.showinfo("Actualización", "Ya estás en la última versión 🎉")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo verificar actualización.\n\n{e}")

    update_btn = ctk.CTkButton(settings_window, text="Buscar actualización", command=check_update)
    update_btn.pack(padx=12, pady=(10,12))

    # -------------------------
    # Botón de cerrar
    # -------------------------
    ctk.CTkButton(settings_window, text="Cerrar", command=_on_close).pack(padx=12, pady=(8,12))

# crear botón gear (solo imagen si existe, sin texto)
if gear_img:
    gear_btn = ctk.CTkButton(frame, image=gear_img, text="", width=36, height=36, corner_radius=18, command=open_settings)
else:
    gear_btn = ctk.CTkButton(frame, text="⚙", width=36, height=36, corner_radius=18, command=open_settings)
gear_btn.grid(row=0, column=5, sticky="ne", padx=(6,6), pady=(6,0))

# Row 1: URL
ctk.CTkLabel(frame, text="URL del video:").grid(row=1, column=0, sticky="w", padx=PAD_X, pady=PAD_Y)
entry_url = ctk.CTkEntry(frame, textvariable=url_var, placeholder_text="Pega la URL del video", corner_radius=8, height=ENTRY_H)
entry_url.grid(row=1, column=1, columnspan=3, sticky="ew", padx=PAD_X, pady=PAD_Y, ipadx=6, ipady=4)
bt_search = ctk.CTkButton(frame, text="Buscar formatos", command=lambda: threading.Thread(target=cargar_formatos, daemon=True).start(), corner_radius=8, height=BTN_H)
bt_search.grid(row=1, column=4, sticky="ew", padx=PAD_X, pady=PAD_Y)

def on_url_change(*args):
    url = url_var.get().strip()
    if url.startswith("http") and ("youtube.com" in url or "youtu.be" in url):
        threading.Thread(target=cargar_formatos, daemon=True).start()
url_var.trace_add("write", on_url_change)

# Row 2: Tipo + thumbnail
ctk.CTkLabel(frame, text="Tipo:").grid(row=2, column=0, sticky="w", padx=PAD_X, pady=PAD_Y)
tipo_combo = ctk.CTkComboBox(frame, values=["Video","Audio"], variable=tipo_var, height=ENTRY_H)
tipo_combo.grid(row=2, column=1, sticky="ew", padx=PAD_X, pady=PAD_Y)
def on_tipo_change(event=None):
    url = url_var.get().strip()
    if url and (url.startswith("http") and ("youtube.com" in url or "youtu.be" in url)):
        threading.Thread(target=cargar_formatos, daemon=True).start()
tipo_combo.bind("<<ComboboxSelected>>", on_tipo_change)

thumbnail_label = ctk.CTkLabel(frame, text="", width=THUMB_SIZE, height=THUMB_SIZE, corner_radius=8)
thumbnail_label.grid(row=2, column=4, rowspan=4, padx=PAD_X, pady=PAD_Y, sticky="n")

# Row 3: Formato + Calidad
ctk.CTkLabel(frame, text="Formato:").grid(row=3, column=0, sticky="w", padx=PAD_X, pady=PAD_Y)
formato_combo = ctk.CTkComboBox(frame, values=[], variable=formato_var, height=ENTRY_H)
formato_combo.grid(row=3, column=1, sticky="ew", padx=PAD_X, pady=PAD_Y)

ctk.CTkLabel(frame, text="Calidad:").grid(row=3, column=2, sticky="w", padx=PAD_X, pady=PAD_Y)
calidad_combo = ctk.CTkComboBox(frame, values=[], variable=calidad_var, height=ENTRY_H)
calidad_combo.grid(row=3, column=3, sticky="ew", padx=PAD_X, pady=PAD_Y)

# Row 4: Guardar como (sin extensión) -> ahora título original (limpiado de caracteres inválidos)
ctk.CTkLabel(frame, text="Guardar como:").grid(row=4, column=0, sticky="w", padx=PAD_X, pady=PAD_Y)
save_as_entry = ctk.CTkEntry(frame, textvariable=save_as_var, placeholder_text="nombre_archivo (sin extensión)", corner_radius=8, height=ENTRY_H)
save_as_entry.grid(row=4, column=1, columnspan=3, sticky="ew", padx=PAD_X, pady=PAD_Y, ipadx=6, ipady=4)

# Row 5: Ubicación (ahora grande)
ctk.CTkLabel(frame, text="Ubicación:").grid(row=5, column=0, sticky="w", padx=PAD_X, pady=PAD_Y)
entry_loc = ctk.CTkEntry(frame, textvariable=ubicacion_var, placeholder_text="Carpeta de descarga", corner_radius=8, height=ENTRY_H)
entry_loc.grid(row=5, column=1, columnspan=3, sticky="ew", padx=PAD_X, pady=PAD_Y, ipadx=6, ipady=4)
bt_elegir = ctk.CTkButton(frame, text="Elegir carpeta", command=elegir_ubicacion, corner_radius=8, height=BTN_H)
bt_elegir.grid(row=5, column=4, padx=PAD_X, pady=PAD_Y, sticky="ew")

# Progress + status
progress_bar = ctk.CTkProgressBar(frame, width=720, height=14)
progress_bar.grid(row=6, column=0, columnspan=6, pady=(12,6), padx=PAD_X, sticky="ew")
progress_bar.set(0.0)

status_label = ctk.CTkLabel(frame, text="Esperando...", font=ctk.CTkFont(size=11, slant="italic"))
status_label.grid(row=7, column=0, columnspan=6, pady=(6,0))

# Descargar (threaded) - sin spinner externo, solo cambio de texto del botón
def descargar_video_threaded():
    url = url_var.get().strip()
    tipo = tipo_var.get().strip().lower()
    formato = formato_var.get().strip().lower()
    calidad = calidad_var.get().strip()
    ubicacion = ubicacion_var.get().strip()
    save_name_base = (save_as_var.get() or "").strip()

    if not url:
        mostrar_error("Ingresa una URL válida.")
        return
    if not ubicacion:
        mostrar_error("Selecciona una carpeta de descarga.")
        return

    save_name_base = strip_known_extension(save_name_base)
    if not save_name_base:
        save_name_base = "video"

    # persistir última carpeta en config
    guardar_ultima_carpeta(ubicacion)
    btn.configure(state="disabled", text="Descargando...")
    progress_bar.set(0.0)

    def _worker():
        try:
            yt = YouTube(url, on_progress_callback=on_progress)
        except Exception as e:
            mostrar_error(f"No se pudo procesar la URL:\n{e}")
            btn.configure(state="normal", text="Descargar")
            return
        parsed_title, parsed_artist = parse_artist_title(getattr(yt, 'title', None), getattr(yt, 'author', None))
        original_title = getattr(yt, 'title', None) or "video"
        titulo_default = limpiar_nombre_simple(original_title)
        os.makedirs(ubicacion, exist_ok=True)
        tmp = tempfile.gettempdir()
        extra = ['mp3', 'wav', 'aiff', 'flac', 'alac', 'wma']
        chosen_format = formato if formato else (formato_audio_preferido if tipo=='audio' else formato_video_preferido)
        final_name = f"{save_name_base}.{chosen_format}" if chosen_format else f"{save_name_base}.mp3"
        out_file = os.path.join(ubicacion, final_name)
        try:
            if tipo == 'video':
                ttkwindow.after(0, lambda: status_label.configure(text="Descargando video..."))
                ttkwindow.after(0, lambda: progress_bar.set(0.0))
                stream = next((s for s in yt.streams.filter(progressive=True) if s.resolution == calidad), None)
                if not stream:
                    stream = next((s for s in yt.streams.filter(adaptive=True, only_video=True) if s.resolution == calidad), None)
                if not stream:
                    mostrar_error("No se encontró video en la calidad seleccionada.")
                    btn.configure(state="normal", text="Descargar")
                    return
                temp_file = stream.download(output_path=tmp, filename_prefix="tmp_")
                temp_ext = os.path.splitext(temp_file)[1].lstrip('.').lower()
                if chosen_format in extra or temp_ext != chosen_format:
                    convertir(temp_file, out_file)
                else:
                    os.replace(temp_file, out_file)
                ttkwindow.after(0, lambda: status_label.configure(text="Video descargado."))
                mostrar_info(f"Video guardado en:\n{out_file}")
            else:
                ttkwindow.after(0, lambda: status_label.configure(text="Descargando audio..."))
                ttkwindow.after(0, lambda: progress_bar.set(0.0))
                stream = next((a for a in yt.streams.filter(only_audio=True).order_by('abr').desc()), None)
                if not stream:
                    mostrar_error("No se encontró stream de audio.")
                    ttkwindow.after(0, lambda: status_label.configure(text="Error: No se encontró stream de audio."))
                    btn.configure(state="normal", text="Descargar")
                    return
                temp_file = stream.download(output_path=tmp, filename_prefix="tmp_")
                ttkwindow.after(0, lambda: status_label.configure(text="Audio descargado."))
                ttkwindow.after(0, lambda: progress_bar.set(1.0))
                temp_ext = os.path.splitext(temp_file)[1].lstrip('.').lower()
                bitrate = None
                if calidad:
                    nums = re.sub(r'[^0-9]', '', calidad)
                    if nums:
                        bitrate = f"{nums}k"
                if chosen_format in extra or temp_ext != chosen_format:
                    convertir(temp_file, out_file, bitrate=bitrate)
                else:
                    os.replace(temp_file, out_file)
                try:
                    ttkwindow.after(0, lambda: status_label.configure(text="Descargando portada..."))
                    img_data = fetch_best_thumbnail(yt)
                    ttkwindow.after(0, lambda: status_label.configure(text="Insertando metadatos..."))
                    miniatura_msg = agregar_metadatos_y_miniatura(out_file, yt, img_data,
                                                                title_override=parsed_title, artist_override=parsed_artist)
                except Exception as e:
                    miniatura_msg = f"No se pudo agregar la miniatura: {e}"
                    ttkwindow.after(0, lambda: status_label.configure(text="¡Descarga finalizada (sin miniatura)!"))
                ttkwindow.after(0, lambda: status_label.configure(text="¡Descarga finalizada!"))
                mostrar_info(f"Descarga completada en:\n{out_file}\n{miniatura_msg}")
        except Exception as e:
            mostrar_error(f"Ocurrió un error:\n{e}")
        finally:
            btn.configure(state="normal", text="Descargar")
    threading.Thread(target=_worker, daemon=True).start()

btn = ctk.CTkButton(frame, text="Descargar", command=descargar_video_threaded,
                    corner_radius=8, fg_color="#6C4AB6", hover_color="#7E57C2", height=BTN_H)
btn.grid(row=8, column=2, pady=(18,6), padx=6, sticky="ew")

# cargar ultima carpeta si existe en config
ultima = cargar_ultima_carpeta()
if ultima:
    ubicacion_var.set(ultima)

# comprobar actualizaciones en background (silencioso)
check_for_updates_threaded(show_ui=False)

if __name__ == "__main__":
    ttkwindow.mainloop()
