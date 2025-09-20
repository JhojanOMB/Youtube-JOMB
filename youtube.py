# -*- coding: utf-8 -*-
# youtube.py - Descargador de YouTube - hecho por JOMB
import os
import sys
import tempfile
import imageio_ffmpeg as ffmpeg
import subprocess
from pytubefix import YouTube
import webbrowser
import re
import urllib.request
from io import BytesIO
from PIL import Image
import socket
import time
import threading
import platform

import requests

import customtkinter as ctk
from tkinter import filedialog, messagebox, PhotoImage, Toplevel

from mutagen import File
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TDRC, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

# ---------------- Config (edítalas si hace falta) ----------------
GITHUB_REPO = "JhojanOMB/Youtube-JOMB"   # owner/repo para comprobar releases
VERSION_FILE = "VERSION"
THEME_DARK_JSON = "temas/tema_morado.json"  # si tienes JSON de tema
# ----------------------------------------------------------------

# ---------------- Theme inicial ----------------
APPEARANCE_DARK = "dark"
APPEARANCE_LIGHT = "light"
THEME_LIGHT = "blue"

try:
    ctk.set_appearance_mode(APPEARANCE_DARK)
    if os.path.exists(THEME_DARK_JSON):
        ctk.set_default_color_theme(THEME_DARK_JSON)
    else:
        ctk.set_default_color_theme("dark-blue")
except Exception:
    ctk.set_appearance_mode(APPEARANCE_DARK)
    ctk.set_default_color_theme("dark-blue")

# ----------------------------------------------------------------
ffmpeg_path = ffmpeg.get_ffmpeg_exe()

formato_audio_preferido = 'mp3'
formato_video_preferido = 'mp4'

def tiene_conexion():
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        return True
    except:
        return False

# ---------------- Version local ----------------
def get_local_version():
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except:
        pass
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
        total = stream.filesize
        downloaded = total - bytes_remaining
        percent = downloaded / total * 100
        try:
            progress_bar.set(percent/100.0)
            status_label.configure(text=f"Descargando... {percent:.1f}%")
        except:
            pass
    except Exception:
        pass

def limpiar_nombre(nombre):
    return re.sub(r'[<>:"/\\|?*]', '', nombre)

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
        subprocess.run(cmd, check=True)
        try:
            os.remove(input_path)
        except:
            pass
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

# ---------------- Mensajes, guardado carpeta ----------------
def mostrar_error(mensaje, title="Error"):
    try:
        top = Toplevel()
        top.withdraw()
        try:
            icon = PhotoImage(file="icono.png")
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
            icon = PhotoImage(file="icono.png")
            top.iconphoto(False, icon)
        except:
            pass
        messagebox.showinfo(title, mensaje, parent=top)
        top.destroy()
    except:
        messagebox.showinfo(title, mensaje)

def guardar_ultima_carpeta(path):
    try:
        with open("ultima_carpeta.txt", "w", encoding="utf-8") as f:
            f.write(path)
    except Exception as e:
        print("No se pudo guardar la última carpeta:", e)

def cargar_ultima_carpeta():
    try:
        if os.path.exists("ultima_carpeta.txt"):
            with open("ultima_carpeta.txt", "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as e:
        print("No se pudo cargar la última carpeta:", e)
    return ""

# ---------------- GitHub updates helpers ----------------
def get_github_latest_release(repo, token=None):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f"token {token}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            return None
    except:
        return None

def find_installer_asset(release_json):
    if not release_json:
        return (None, None)
    assets = release_json.get('assets', [])
    for a in assets:
        name = a.get('name', '').lower()
        if name.endswith('.exe'):
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
                            status_label_obj.configure(text=f"Descargando actualizacion... {pct:.1f}%")
                        except:
                            pass

# threaded check wrapper (usa la implementación previa pero en segundo plano)
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

# ---------------- descarga principal ----------------
def descargar_video():
    if not tiene_conexion():
        mostrar_error("No hay conexión a Internet. Por favor verifica tu red Wi-Fi o datos móviles.")
        return

    url = url_var.get().strip()
    tipo = tipo_var.get().strip().lower()
    formato = formato_var.get().strip().lower()
    calidad = calidad_var.get().strip()
    ubicacion = ubicacion_var.get().strip()

    if not url:
        mostrar_error("Ingresa una URL válida.")
        return
    if not ubicacion:
        mostrar_error("Selecciona una carpeta de descarga.")
        return

    guardar_ultima_carpeta(ubicacion)

    try:
        yt = YouTube(url, on_progress_callback=on_progress)
    except Exception as e:
        mostrar_error(f"No se pudo procesar la URL:\n{e}")
        return

    parsed_title, parsed_artist = parse_artist_title(getattr(yt, 'title', None), getattr(yt, 'author', None))
    titulo = limpiar_nombre(parsed_title or yt.title or "video")
    os.makedirs(ubicacion, exist_ok=True)
    tmp = tempfile.gettempdir()

    extra = ['mp3', 'wav', 'aiff', 'flac', 'alac', 'wma']

    try:
        if tipo == 'video':
            stream = next((s for s in yt.streams.filter(progressive=True) if s.resolution == calidad), None)
            if not stream:
                stream = next((s for s in yt.streams.filter(adaptive=True, only_video=True) if s.resolution == calidad), None)
            if not stream:
                mostrar_error("No se encontró video en la calidad seleccionada.")
                return
            status_label.configure(text="Descargando video...")
            progress_bar.set(0.0)
            ttkwindow.update_idletasks()
            temp_file = stream.download(output_path=tmp, filename_prefix="tmp_")
            out_file = os.path.join(ubicacion, f"{titulo}.{formato}")
            temp_ext = os.path.splitext(temp_file)[1].lstrip('.').lower()
            if formato in extra or temp_ext != formato:
                convertir(temp_file, out_file)
            else:
                os.replace(temp_file, out_file)
            status_label.configure(text="Video descargado.")
            mostrar_info(f"Video guardado en:\n{out_file}")
        else:
            status_label.configure(text="Descargando audio...")
            progress_bar.set(0.0)
            ttkwindow.update_idletasks()

            stream = next((a for a in yt.streams.filter(only_audio=True).order_by('abr').desc()), None)
            if not stream:
                mostrar_error("No se encontró stream de audio.")
                status_label.configure(text="Error: No se encontró stream de audio.")
                return

            temp_file = stream.download(output_path=tmp, filename_prefix="tmp_")
            status_label.configure(text="Audio descargado.")
            progress_bar.set(1.0)
            ttkwindow.update_idletasks()

            out_file = os.path.join(ubicacion, f"{titulo}.{formato}")

            bitrate = None
            if calidad:
                nums = re.sub(r'[^0-9]', '', calidad)
                if nums:
                    bitrate = f"{nums}k"

            temp_ext = os.path.splitext(temp_file)[1].lstrip('.').lower()
            if formato in extra or temp_ext != formato:
                convertir(temp_file, out_file, bitrate=bitrate)
            else:
                os.replace(temp_file, out_file)

            try:
                status_label.configure(text="Descargando portada...")
                ttkwindow.update_idletasks()
                img_data = fetch_best_thumbnail(yt)
                status_label.configure(text="Insertando metadatos...")
                ttkwindow.update_idletasks()
                miniatura_msg = agregar_metadatos_y_miniatura(out_file, yt, img_data,
                                                            title_override=parsed_title, artist_override=parsed_artist)
            except Exception as e:
                miniatura_msg = f"No se pudo agregar la miniatura: {e}"
                status_label.configure(text="¡Descarga finalizada (sin miniatura)!")

            status_label.configure(text="¡Descarga finalizada!")
            mostrar_info(f"Descarga completada en:\n{out_file}\n{miniatura_msg}")

    except Exception as e:
        mostrar_error(f"Ocurrió un error:\n{e}")

# ---------------- cargar formatos (auto-fetch con debounce) ----------------
_last_fetch_ts = 0
def cargar_formatos(debounce_ms=600):
    global _last_fetch_ts
    now = time.time() * 1000
    if now - _last_fetch_ts < debounce_ms:
        return
    _last_fetch_ts = now

    if not tiene_conexion():
        mostrar_error("No hay conexión a Internet. Por favor verifica tu red Wi-Fi o datos móviles.")
        return

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

    try:
        img_data = fetch_best_thumbnail(yt_temp)
        if img_data:
            img = Image.open(BytesIO(img_data)).convert("RGBA")
            img.thumbnail((160, 90), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(160, 90))
            thumbnail_label.configure(image=ctk_img)
            thumbnail_label.image = ctk_img
        else:
            placeholder = Image.new("RGBA", (160, 90), (44, 16, 46, 255))
            ctk_img = ctk.CTkImage(light_image=placeholder, dark_image=placeholder, size=(160, 90))
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
    mostrar_info("Formatos, calidades y miniatura listos.")
    entry_url.configure(state='normal')
    tipo_combo.configure(state='normal')

def elegir_ubicacion():
    carpeta = filedialog.askdirectory()
    if carpeta:
        ubicacion_var.set(carpeta)
        guardar_ultima_carpeta(carpeta)

# ---------------- UI ----------------
ttkwindow = ctk.CTk()
ttkwindow.title("Descargador de YouTube - JOMB")
try:
    icon = PhotoImage(file="icono.png")
    ttkwindow.iconphoto(False, icon)
except:
    pass

ttkwindow.geometry("720x520")
ttkwindow.minsize(640, 480)

url_var = ctk.StringVar()
tipo_var = ctk.StringVar(value="Video")
formato_var = ctk.StringVar()
calidad_var = ctk.StringVar()
ubicacion_var = ctk.StringVar()
progress_var = ctk.DoubleVar(value=0.0)

frame = ctk.CTkFrame(ttkwindow, corner_radius=10)
frame.pack(fill="both", expand=True, padx=18, pady=18)
# header grid: use 5 columns so we can center title and put gear button at far right
for i in range(6):
    frame.columnconfigure(i, weight=1)
for i in range(14):
    frame.rowconfigure(i, weight=0)
frame.rowconfigure(7, weight=1)
frame.rowconfigure(13, weight=1)

# Title centered across many cols
title_label = ctk.CTkLabel(frame, text="Descargador de YouTube", font=ctk.CTkFont(size=20, weight="bold"))
# place centered: span columns 0..4
title_label.grid(row=0, column=1, columnspan=4, pady=(0,10), sticky="n")

# Gear/settings button on far right (column 5)
def open_settings():
    # modal settings window
    try:
        settings = ctk.CTkToplevel(ttkwindow)
    except:
        settings = Toplevel(ttkwindow)
    settings.title("Configuración")
    settings.geometry("420x300")
    settings.transient(ttkwindow)

    # Center window relative to main
    try:
        x = ttkwindow.winfo_rootx()
        y = ttkwindow.winfo_rooty()
        settings.geometry("+%d+%d" % (x+80, y+60))
    except:
        pass

    # Local version
    ctk.CTkLabel(settings, text=f"Versión local: {LOCAL_VERSION}", anchor="w").pack(fill="x", padx=12, pady=(12,6))

    # Auto-check updates toggle
    auto_check_var = ctk.BooleanVar(value=False)
    ctk.CTkLabel(settings, text="Comprobación automática de actualizaciones al iniciar:").pack(fill="x", padx=12, pady=(6,0))
    auto_check_switch = ctk.CTkSwitch(settings, text="", variable=auto_check_var)
    auto_check_switch.pack(anchor="w", padx=12, pady=(0,6))

    # Theme selector
    ctk.CTkLabel(settings, text="Tema:").pack(fill="x", padx=12, pady=(8,0))
    theme_var_local = ctk.StringVar(value="Oscuro")
    def apply_theme_local():
        v = theme_var_local.get()
        if v == "Oscuro":
            ctk.set_appearance_mode(APPEARANCE_DARK)
            if os.path.exists(THEME_DARK_JSON):
                ctk.set_default_color_theme(THEME_DARK_JSON)
        else:
            ctk.set_appearance_mode(APPEARANCE_LIGHT)
            ctk.set_default_color_theme(THEME_LIGHT)
    theme_box = ctk.CTkComboBox(settings, values=["Oscuro","Claro"], variable=theme_var_local)
    theme_box.pack(fill="x", padx=12, pady=(4,6))
    apply_theme_btn = ctk.CTkButton(settings, text="Aplicar tema", command=apply_theme_local)
    apply_theme_btn.pack(padx=12, pady=(6,10))

    # Check updates button + label
    rv_label = ctk.CTkLabel(settings, text="Última versión remota: -", anchor="w")
    rv_label.pack(fill="x", padx=12, pady=(6,2))

    def settings_check_updates():
        def _job():
            try:
                status_lbl = rv_label
                token = os.environ.get("GITHUB_TOKEN")
                rel = get_github_latest_release(GITHUB_REPO, token=token)
                if not rel:
                    status_lbl.configure(text="No se pudo consultar GitHub.")
                    return
                tag = rel.get('tag_name','') or rel.get('name','')
                remote_version = tag.lstrip('vV') if tag else '0.0.0'
                status_lbl.configure(text=f"Última versión remota: {remote_version}")
                if is_newer_version(remote_version, LOCAL_VERSION):
                    if messagebox.askyesno("Actualización", f"Versión {remote_version} disponible. ¿Descargar e instalar?"):
                        # lanzar la comprobación (usa la lógica general)
                        check_for_updates_threaded(show_ui=True)
                else:
                    messagebox.showinfo("Actualizaciones", f"Estás en la última versión ({LOCAL_VERSION}).")
            except Exception as e:
                status_lbl.configure(text=f"Error: {e}")
        threading.Thread(target=_job, daemon=True).start()

    ctk.CTkButton(settings, text="Buscar actualizaciones ahora", command=settings_check_updates).pack(padx=12, pady=(6,10))

    # Close button
    ctk.CTkButton(settings, text="Cerrar", command=settings.destroy).pack(padx=12, pady=(8,12))

    # If user enabled auto-check in future runs you may persist auto_check_var.get() to a small config file.
    # For now we just respect the toggle while the settings window is open.

gear_btn = ctk.CTkButton(frame, text="⚙", width=36, height=36, corner_radius=18, command=open_settings)
gear_btn.grid(row=0, column=5, sticky="ne", padx=(6,6))

# Header / controls
ctk.CTkLabel(frame, text="URL del video:").grid(row=1, column=0, sticky="w", pady=6, padx=6)
entry_url = ctk.CTkEntry(frame, textvariable=url_var, placeholder_text="Pega la URL del video", corner_radius=8)
entry_url.grid(row=1, column=1, columnspan=3, pady=6, padx=6, sticky="ew")
bt_search = ctk.CTkButton(frame, text="Buscar formatos", command=cargar_formatos, corner_radius=8)
bt_search.grid(row=1, column=4, padx=6, pady=6, sticky="ew")

# auto-fetch cuando cambie URL
def on_url_change(*args):
    url = url_var.get().strip()
    if url.startswith("http") and ("youtube.com" in url or "youtu.be" in url):
        cargar_formatos()
url_var.trace_add("write", on_url_change)

ctk.CTkLabel(frame, text="Tipo:").grid(row=2, column=0, sticky="w", pady=6, padx=6)
tipo_combo = ctk.CTkComboBox(frame, values=["Video","Audio"], variable=tipo_var)
tipo_combo.grid(row=2, column=1, sticky="ew", pady=6, padx=6)
def on_tipo_change_cb(event=None):
    cargar_formatos()
tipo_combo.bind("<<ComboboxSelected>>", on_tipo_change_cb)

ctk.CTkLabel(frame, text="Formato:").grid(row=3, column=0, sticky="w", pady=6, padx=6)
formato_combo = ctk.CTkComboBox(frame, values=[], variable=formato_var)
formato_combo.grid(row=3, column=1, sticky="ew", pady=6, padx=6)

ctk.CTkLabel(frame, text="Calidad:").grid(row=4, column=0, sticky="w", pady=6, padx=6)
calidad_combo = ctk.CTkComboBox(frame, values=[], variable=calidad_var)
calidad_combo.grid(row=4, column=1, sticky="ew", pady=6, padx=6)

thumbnail_label = ctk.CTkLabel(frame, text="", width=160, height=90, corner_radius=8)
thumbnail_label.grid(row=2, column=4, rowspan=3, padx=6, sticky="nsew")

ctk.CTkLabel(frame, text="Ubicación:").grid(row=5, column=0, sticky="w", pady=6, padx=6)
entry_loc = ctk.CTkEntry(frame, textvariable=ubicacion_var, placeholder_text="Carpeta de descarga", corner_radius=8)
entry_loc.grid(row=5, column=1, pady=6, padx=6, sticky="ew")
bt_elegir = ctk.CTkButton(frame, text="Elegir carpeta", command=elegir_ubicacion, corner_radius=8)
bt_elegir.grid(row=5, column=4, padx=6, pady=6, sticky="ew")

progress_bar = ctk.CTkProgressBar(frame, width=640, height=14)
progress_bar.grid(row=6, column=0, columnspan=6, pady=(10,0), sticky="ew")
progress_bar.set(0.0)

status_label = ctk.CTkLabel(frame, text="Esperando...", font=ctk.CTkFont(size=11, slant="italic"))
status_label.grid(row=7, column=0, columnspan=6, pady=(6,0), sticky="ew")

btn = ctk.CTkButton(frame, text="Descargar", command=descargar_video, corner_radius=8, fg_color="#6C4AB6", hover_color="#7E57C2")
btn.grid(row=8, column=2, pady=18, padx=6, sticky="ew")

ultima = cargar_ultima_carpeta()
if ultima:
    ubicacion_var.set(ultima)

# Footer
footer_frame = ctk.CTkFrame(frame, fg_color=("#281226"))
footer_frame.grid(row=13, column=0, columnspan=6, pady=(8, 4), sticky="ew")
footer_frame.columnconfigure(0, weight=1)
footer_label = ctk.CTkLabel(footer_frame, text="Hecho por JOMB S.A.S  •  Visita nuestro sitio web", text_color="#E8DAFF", font=ctk.CTkFont(size=11, slant="italic"))
footer_label.grid(sticky="ew", padx=8, pady=6)
footer_label.bind("<Button-1>", lambda e: webbrowser.open_new("https://jhojanomb.github.io/JOMB/"))

# Comprobar actualizaciones en background al iniciar, no mostrar diálogos por defecto
check_for_updates_threaded(show_ui=False)

ttkwindow.mainloop()
