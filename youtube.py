# -*- coding: utf-8 -*-
# youtube_app.py
# Descargador YouTube - CustomTkinter, portada robusta, toggle tema claro/oscuro
import os
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

# CustomTkinter + tkinter
import customtkinter as ctk
from tkinter import filedialog, messagebox, PhotoImage, Toplevel

# mutagen
from mutagen import File
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TDRC, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

# ---------------- Theme inicial ----------------
# Queremos tema oscuro morado por defecto; si no existe JSON se usa 'dark-blue'
APPEARANCE_DARK = "dark"
APPEARANCE_LIGHT = "light"
THEME_DARK_JSON = "temas/tema_morado.json"  # crea este archivo con el JSON sugerido
THEME_LIGHT = "blue"  # tema por defecto para modo claro

# Aplicar tema inicial (intentar tema morado; si falla usar dark-blue)
try:
    ctk.set_appearance_mode(APPEARANCE_DARK)
    if os.path.exists(THEME_DARK_JSON):
        ctk.set_default_color_theme(THEME_DARK_JSON)
    else:
        ctk.set_default_color_theme("dark-blue")
except Exception:
    ctk.set_appearance_mode(APPEARANCE_DARK)
    ctk.set_default_color_theme("dark-blue")

# ---------------------------------------
ffmpeg_path = ffmpeg.get_ffmpeg_exe()

formato_audio_preferido = 'mp3'
formato_video_preferido = 'mp4'

def tiene_conexion():
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        return True
    except:
        return False

# progreso para pytube
def on_progress(stream, chunk, bytes_remaining):
    try:
        total = stream.filesize
        downloaded = total - bytes_remaining
        percent = downloaded / total * 100
        progress_bar.set(percent/100.0)
        status_label.configure(text=f"Descargando... {percent:.1f}%")
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

# Debounce helper simple
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

    # Miniatura - usar fetch_best_thumbnail
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

# --------------------- UI --------------------
ttkwindow = ctk.CTk()
ttkwindow.title("Descargador de YouTube - JOMB")
try:
    icon = PhotoImage(file="icono.png")
    ttkwindow.iconphoto(False, icon)
except:
    pass

ttkwindow.geometry("640x520")
ttkwindow.minsize(560, 440)

url_var = ctk.StringVar()
tipo_var = ctk.StringVar(value="Video")
formato_var = ctk.StringVar()
calidad_var = ctk.StringVar()
ubicacion_var = ctk.StringVar()
progress_var = ctk.DoubleVar(value=0.0)

frame = ctk.CTkFrame(ttkwindow, corner_radius=10)
frame.pack(fill="both", expand=True, padx=20, pady=20)
for i in range(3): frame.columnconfigure(i, weight=1)
for i in range(12): frame.rowconfigure(i, weight=0)
frame.rowconfigure(6, weight=1)
frame.rowconfigure(11, weight=1)

# Header row: título + tema toggle
ctk.CTkLabel(frame, text="Descargador de YouTube", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(0,15), sticky="w")

# Toggle tema: Switch + botón de texto
def toggle_theme_switch():
    # switch variable inversa
    val = theme_switch_var.get()
    if val:
        # switch ON -> oscuro (modo morado)
        try:
            ctk.set_appearance_mode(APPEARANCE_DARK)
            if os.path.exists(THEME_DARK_JSON):
                ctk.set_default_color_theme(THEME_DARK_JSON)
        except:
            ctk.set_appearance_mode(APPEARANCE_DARK)
    else:
        # switch OFF -> claro (tema light)
        try:
            ctk.set_appearance_mode(APPEARANCE_LIGHT)
            ctk.set_default_color_theme(THEME_LIGHT)
        except:
            ctk.set_appearance_mode(APPEARANCE_LIGHT)

theme_switch_var = ctk.BooleanVar(value=True)  # por defecto ON -> oscuro
theme_switch = ctk.CTkSwitch(frame, text="Modo oscuro", command=toggle_theme_switch, variable=theme_switch_var)
theme_switch.grid(row=0, column=2, sticky="e", padx=(0,5))

# URL row
ctk.CTkLabel(frame, text="URL del video:").grid(row=1, column=0, sticky="w", pady=5, padx=5)
entry_url = ctk.CTkEntry(frame, textvariable=url_var, placeholder_text="Pega la URL del video", corner_radius=8)
entry_url.grid(row=1, column=1, pady=5, padx=5, sticky="ew")
bt_search = ctk.CTkButton(frame, text="Buscar formatos", command=cargar_formatos, corner_radius=8)
bt_search.grid(row=1, column=2, padx=5, pady=5, sticky="ew")

# auto-fetch cuando cambie URL
def on_url_change(*args):
    url = url_var.get().strip()
    if url.startswith("http") and ("youtube.com" in url or "youtu.be" in url):
        cargar_formatos()
url_var.trace_add("write", on_url_change)

ctk.CTkLabel(frame, text="Tipo:").grid(row=2, column=0, sticky="w", pady=5, padx=5)
tipo_combo = ctk.CTkComboBox(frame, values=["Video","Audio"], variable=tipo_var)
tipo_combo.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
def on_tipo_change_cb(event=None):
    cargar_formatos()
tipo_combo.bind("<<ComboboxSelected>>", on_tipo_change_cb)

ctk.CTkLabel(frame, text="Formato:").grid(row=3, column=0, sticky="w", pady=5, padx=5)
formato_combo = ctk.CTkComboBox(frame, values=[], variable=formato_var)
formato_combo.grid(row=3, column=1, sticky="ew", pady=5, padx=5)

ctk.CTkLabel(frame, text="Calidad:").grid(row=4, column=0, sticky="w", pady=5, padx=5)
calidad_combo = ctk.CTkComboBox(frame, values=[], variable=calidad_var)
calidad_combo.grid(row=4, column=1, sticky="ew", pady=5, padx=5)

thumbnail_label = ctk.CTkLabel(frame, text="", width=160, height=90, corner_radius=8)
thumbnail_label.grid(row=2, column=2, rowspan=3, padx=10, sticky="nsew")

ctk.CTkLabel(frame, text="Ubicación:").grid(row=5, column=0, sticky="w", pady=5, padx=5)
entry_loc = ctk.CTkEntry(frame, textvariable=ubicacion_var, placeholder_text="Carpeta de descarga", corner_radius=8)
entry_loc.grid(row=5, column=1, pady=5, padx=5, sticky="ew")
bt_elegir = ctk.CTkButton(frame, text="Elegir carpeta", command=elegir_ubicacion, corner_radius=8)
bt_elegir.grid(row=5, column=2, padx=5, pady=5, sticky="ew")

progress_bar = ctk.CTkProgressBar(frame, width=520, height=14)
progress_bar.grid(row=6, column=0, columnspan=3, pady=(10,0), sticky="ew")
progress_bar.set(0.0)

status_label = ctk.CTkLabel(frame, text="Esperando...", font=ctk.CTkFont(size=11, slant="italic"))
status_label.grid(row=7, column=0, columnspan=3, pady=(6,0), sticky="ew")

btn = ctk.CTkButton(frame, text="Descargar", command=descargar_video, corner_radius=8, fg_color="#6C4AB6", hover_color="#7E57C2")
btn.grid(row=8, column=1, pady=20, sticky="ew")

ultima = cargar_ultima_carpeta()
if ultima:
    ubicacion_var.set(ultima)

# Footer oscuro morado
footer_frame = ctk.CTkFrame(frame, fg_color=("#281226"))
footer_frame.grid(row=11, column=0, columnspan=3, pady=(10, 2), sticky="ew")
footer_frame.columnconfigure(0, weight=1)
footer_label = ctk.CTkLabel(footer_frame, text="Hecho por JOMB S.A.S  •  Visita nuestro sitio web", text_color="#E8DAFF", font=ctk.CTkFont(size=11, slant="italic"))
footer_label.grid(sticky="ew", padx=8, pady=6)
footer_label.bind("<Button-1>", lambda e: webbrowser.open_new("https://jhojanomb.github.io/JOMB/"))

ttkwindow.mainloop()
