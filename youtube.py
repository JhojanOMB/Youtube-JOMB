# --- arreglos/añadidos al inicio del archivo ---
import os
import tempfile
import imageio_ffmpeg as ffmpeg
import subprocess
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from pytubefix import YouTube
from tkinter import filedialog, messagebox, PhotoImage, Label, Toplevel
import webbrowser
import re
import urllib.request
from io import BytesIO
from PIL import Image, ImageTk
import socket
from mutagen import File
from mutagen.id3 import APIC, error as ID3Error
from mutagen.flac import Picture
from mutagen.mp4 import MP4Cover

# ------------------------------------------------------------------
ffmpeg_path = ffmpeg.get_ffmpeg_exe()

# ------------------------------------------------------------------

formato_audio_preferido = 'mp3'  # Formato preferido para audio
formato_video_preferido = 'mp4'  # Formato preferido para video

def tiene_conexion():
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        return True
    except:
        return False

# Callback de progreso
def on_progress(stream, chunk, bytes_remaining):
    total = stream.filesize
    downloaded = total - bytes_remaining
    percent = downloaded / total * 100
    progress_var.set(percent)
    progress_bar.update()
    status_label.config(text=f"Descargando audio... {percent:.1f}%")

# Limpia nombre de archivo
def limpiar_nombre(nombre):
    return re.sub(r'[<>:"/\\|?*]', '', nombre)

# Función para conversión con ffmpeg
# ------------------------------------------------------------------
def convertir(input_path, output_path):
    try:
        subprocess.run([ffmpeg_path, '-y', '-i', input_path, output_path], check=True)
        os.remove(input_path)
    except subprocess.CalledProcessError as e:
        mostrar_error(f"Fallo en conversión:\n{e}")  # <-- f-string corregida
        raise
# ------------------------------------------------------------------

# Nuevo handler: cuando cambie el tipo, limpia y (si hay URL) busca formatos
def on_tipo_change(event=None):
    formato_combo.config(values=[])
    calidad_combo.config(values=[])
    formato_var.set('')
    calidad_var.set('')
    # Si ya hay URL, lanzamos la carga automática
    if url_var.get().strip():
        cargar_formatos()

# Función para mostrar errores con ícono personalizado
def mostrar_error(mensaje):
    try:
        custom_icon = PhotoImage(file="icono.png")
        top = Toplevel()
        top.withdraw()
        top.iconphoto(False, custom_icon)
        messagebox.showerror("Error", mensaje, parent=top)
        top.destroy()
    except:
        messagebox.showerror("Error", mensaje)

# Función para mostrar éxito con ícono personalizado
def mostrar_info(mensaje):
    try:
        custom_icon = PhotoImage(file="icono.png")
        top = Toplevel()
        top.withdraw()
        top.iconphoto(False, custom_icon)
        messagebox.showinfo("Éxito", mensaje, parent=top)
        top.destroy()
    except:
        messagebox.showinfo("Éxito", mensaje)

# --- NUEVO: recordar última carpeta ---
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

# Función para descargar
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

    # Guardar la última carpeta usada
    guardar_ultima_carpeta(ubicacion)

    try:
        yt = YouTube(url, on_progress_callback=on_progress)
    except Exception as e:
        mostrar_error(f"No se pudo procesar la URL:\n{e}")
        return

    titulo = limpiar_nombre(yt.title)
    os.makedirs(ubicacion, exist_ok=True)
    tmp = tempfile.gettempdir()

    extra = ['wav', 'aiff', 'flac', 'alac', 'wma']

    if tipo == 'video':
        stream = next((s for s in yt.streams.filter(progressive=True) if s.resolution == calidad), None)
        if not stream:
            stream = next((s for s in yt.streams.filter(adaptive=True, only_video=True) if s.resolution == calidad), None)
        if not stream:
            mostrar_error("No se encontró video en la calidad seleccionada.")
            return
        status_label.config(text="Descargando video...", foreground="blue")
        progress_var.set(0)
        progress_bar.update()
        ttkwindow.update_idletasks()
        temp_file = stream.download(output_path=tmp, filename_prefix="tmp_")
        out_file = os.path.join(ubicacion, f"{titulo}.{formato}")
        if formato in extra or os.path.splitext(temp_file)[1].lstrip('.') != formato:
            convertir(temp_file, out_file)
        else:
            os.replace(temp_file, out_file)
        status_label.config(text="Video descargado.", foreground="green")
    else:
        status_label.config(text="Descargando audio...", foreground="blue")
        progress_var.set(0)
        progress_bar.update()
        ttkwindow.update_idletasks()
        stream = next((a for a in yt.streams.filter(only_audio=True).order_by('abr').desc()), None)
        if not stream:
            mostrar_error("No se encontró stream de audio.")
            status_label.config(text="Error: No se encontró stream de audio.", foreground="red")
            return
        temp_file = stream.download(output_path=tmp, filename_prefix="tmp_")
        status_label.config(text="Audio descargado.", foreground="green")
        progress_var.set(100)
        progress_bar.update()
        ttkwindow.update_idletasks()

        out_file = os.path.join(ubicacion, f"{titulo}.{formato}")
        if formato in extra or os.path.splitext(temp_file)[1].lstrip('.') != formato:
            convertir(temp_file, out_file)
        else:
            os.replace(temp_file, out_file)

        # --- AGREGAR MINIATURA A CUALQUIER FORMATO DE AUDIO ---
        try:
            status_label.config(text="Descargando miniatura...", foreground="blue")
            ttkwindow.update_idletasks()
            thumb_url = getattr(yt, "thumbnail_url", None) or getattr(yt, "thumbnail", None)
            if thumb_url:
                with urllib.request.urlopen(thumb_url, timeout=6) as u:
                    img_data = u.read()
                status_label.config(text="Insertando miniatura...", foreground="blue")
                ttkwindow.update_idletasks()
                audio = File(out_file)
                if audio is not None:
                    if out_file.lower().endswith('.mp3'):
                        try:
                            audio.tags.add(
                                APIC(
                                    encoding=3,
                                    mime='image/jpeg',
                                    type=3,
                                    desc='Cover',
                                    data=img_data
                                )
                            )
                            audio.save()
                            miniatura_msg = "Miniatura agregada correctamente."
                        except ID3Error:
                            miniatura_msg = "No se pudo agregar la miniatura (ID3)."
                    elif out_file.lower().endswith('.flac'):
                        pic = Picture()
                        pic.data = img_data
                        pic.type = 3
                        pic.mime = "image/jpeg"
                        audio.add_picture(pic)
                        audio.save()
                        miniatura_msg = "Miniatura agregada correctamente."
                    elif out_file.lower().endswith(('.m4a', '.mp4', '.aac', '.alac')):
                        audio.tags["covr"] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
                        audio.save()
                        miniatura_msg = "Miniatura agregada correctamente."
                    else:
                        miniatura_msg = "Formato de audio no soporta miniatura automática."
                else:
                    miniatura_msg = "No se pudo abrir el archivo de audio para agregar miniatura."
            else:
                miniatura_msg = "No se encontró miniatura."
            status_label.config(text=miniatura_msg, foreground="green")
        except Exception as e:
            miniatura_msg = f"No se pudo agregar la miniatura: {e}"
            status_label.config(text="¡Descarga finalizada (sin miniatura)!", foreground="orange")
        status_label.config(text="¡Descarga finalizada!", foreground="green")
        mostrar_info(f"Descarga completada en:\n{out_file}\n{miniatura_msg}")

# Función modificada para filtrar según tipo (video/audio) y ordenar calidades robustamente
def cargar_formatos():
    if not tiene_conexion():
        mostrar_error("No hay conexión a Internet. Por favor verifica tu red Wi-Fi o datos móviles.")
        return

    # Deshabilitar UI mientras se procesa
    entry_url.config(state='disabled')
    tipo_combo.config(state='disabled')
    formato_combo.config(state='disabled')
    calidad_combo.config(state='disabled')
    bt_elegir.config(state='disabled')
    btn.config(state='disabled')

    url = url_var.get().strip()
    tipo = tipo_var.get().strip().lower()  # 'video' o 'audio'
    if not url:
        mostrar_error("Ingresa una URL.")
        entry_url.config(state='normal')
        tipo_combo.config(state='readonly')
        return

    try:
        yt_temp = YouTube(url)
    except Exception as e:
        mostrar_error(f"URL inválida:\n{e}")
        entry_url.config(state='normal')
        tipo_combo.config(state='readonly')
        return

    # --- Miniatura (igual que antes) ---
    try:
        thumb_url = getattr(yt_temp, "thumbnail_url", None) or getattr(yt_temp, "thumbnail", None)
        if thumb_url:
            with urllib.request.urlopen(thumb_url, timeout=6) as u:
                data = u.read()
            img = Image.open(BytesIO(data)).convert("RGBA")
            img.thumbnail((160, 90), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            thumbnail_label.config(image=photo)
            thumbnail_label.image = photo
            thumbnail_label.update()
        else:
            placeholder = Image.new("RGBA", (160, 90), (200, 200, 200, 255))
            photo = ImageTk.PhotoImage(placeholder)
            thumbnail_label.config(image=photo)
            thumbnail_label.image = photo
            thumbnail_label.update()
    except Exception as e:
        print("Error cargando miniatura:", e)
        try:
            placeholder = Image.new("RGBA", (160, 90), (200, 200, 200, 255))
            photo = ImageTk.PhotoImage(placeholder)
            thumbnail_label.config(image=photo)
            thumbnail_label.image = photo
            thumbnail_label.update()
        except:
            pass

    # Sets separados para video/audio
    formatos_video = set()
    formatos_audio = set()
    calis = set()

    for f in yt_temp.streams:
        mime = getattr(f, 'mime_type', '') or ''
        ext = mime.split('/')[-1] if mime else ''

        # Manejo video
        is_video = (hasattr(f, 'resolution') and getattr(f, 'resolution')) or mime.startswith('video')
        # Manejo audio
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
            if not is_audio:
                # Hay casos donde el container es 'video' pero es audio-only: intentar detectar por default_filename
                fname = getattr(f, 'default_filename', '') or ''
                if fname and fname.lower().endswith(('.m4a', '.mp3', '.aac', '.flac')):
                    # aceptarlo como audio
                    pass
                else:
                    continue
            if hasattr(f, 'abr') and getattr(f, 'abr'):
                calis.add(getattr(f, 'abr'))
            # mapear mp4 audio-only a m4a para mejor UX
            if ext:
                if ext == 'mp4':
                    formatos_audio.add('m4a')
                else:
                    formatos_audio.add(ext)
            else:
                fname = getattr(f, 'default_filename', '') or ''
                if fname and '.' in fname:
                    formatos_audio.add(fname.split('.')[-1])

    # Añadir formatos extra SOLO para audio (incluyendo mp3 solicitado)
    if tipo == 'audio':
        formatos_audio.update(['mp3', 'wav', 'aiff', 'flac', 'alac', 'wma'])

    formatos = formatos_video if tipo == 'video' else formatos_audio

    formato_list = sorted(formatos)
    formato_combo.config(values=formato_list, state='readonly' if formato_list else 'disabled')
    if formato_list:
        # elegir formato preferido si está disponible
        if tipo == 'audio' and formato_audio_preferido in formato_list:
            formato_var.set(formato_audio_preferido)
        elif tipo == 'video' and formato_video_preferido in formato_list:
            formato_var.set(formato_video_preferido)
        else:
            formato_var.set(formato_list[0])
    else:
        formato_var.set('')

    # Ordenar calidades de forma robusta
    def sort_key_cal(c):
        s = str(c)
        nums = re.sub(r'[^0-9]', '', s)
        try:
            return int(nums)
        except:
            return 0

    calidad_list = sorted([c for c in calis], key=sort_key_cal)
    if tipo == 'video':
        calidad_combo.config(values=calidad_list, state='readonly' if calidad_list else 'disabled')
        if calidad_list:
            calidad_var.set(calidad_list[-1])
    else:
        calidad_combo.config(values=calidad_list, state='readonly' if calidad_list else 'disabled')
        if calidad_list:
            calidad_var.set('320kbps' if '320kbps' in calidad_list else calidad_list[-1])

    # Reactivar UI
    bt_elegir.config(state='normal')
    btn.config(state='normal')
    mostrar_info("Formatos, calidades y miniatura listos.")
    entry_url.config(state='normal')
    tipo_combo.config(state='readonly')

# Función para elegir carpeta
def elegir_ubicacion():
    carpeta = filedialog.askdirectory()
    if carpeta:
        ubicacion_var.set(carpeta)

# Configuración de la ventana principal
ttkwindow = ttk.Window(themename="flatly")
ttkwindow.title("Descargador de YouTube")
try:
    icon = PhotoImage(file="icono.png")
    ttkwindow.iconphoto(False, icon)
except:
    pass

ttkwindow.geometry("600x450")
ttkwindow.minsize(500, 400)

# Variables
url_var = ttk.StringVar()
tipo_var = ttk.StringVar(value="Video")
formato_var = ttk.StringVar()
calidad_var = ttk.StringVar()
ubicacion_var = ttk.StringVar()
progress_var = ttk.DoubleVar(master=ttkwindow)

# Estilos
style = ttk.Style()
style.configure("TButton", font=("Segoe UI", 12))
style.configure("TLabel", font=("Segoe UI", 12))
style.configure("TEntry", font=("Segoe UI", 12))
style.configure("TCombobox", font=("Segoe UI", 12))

# --- Hacer la ventana y el frame responsive ---
ttkwindow.rowconfigure(0, weight=1)
ttkwindow.columnconfigure(0, weight=1)

# Frame principal
frame = ttk.Frame(ttkwindow, padding=20)
frame.pack(fill="both", expand=True)

# --- Hacer columnas y filas del frame expansibles ---
for i in range(3):
    frame.columnconfigure(i, weight=1)
for i in range(11):  # Ajusta según el número de filas que uses
    frame.rowconfigure(i, weight=0)
frame.rowconfigure(6, weight=1)  # La barra de progreso puede expandirse
frame.rowconfigure(10, weight=1) # El footer también

# Título
ttk.Label(frame, text="Descargador de YouTube", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, pady=(0,15))

# URL
ttk.Label(frame, text="URL del video:").grid(row=1, column=0, sticky="w", pady=5)
entry_url = ttk.Entry(frame, textvariable=url_var, width=40)
entry_url.grid(row=1, column=1, pady=5, padx=5, sticky="ew")
bt_search = ttk.Button(frame, text="Buscar formatos", command=cargar_formatos, bootstyle=INFO)
bt_search.grid(row=1, column=2, padx=5, pady=5, sticky="ew")

# Variable de control para búsqueda automática
busqueda_manual_realizada = [False]  # Usamos lista para modificar dentro de funciones

# --- Detectar cambios en la URL y buscar automáticamente ---
def on_url_change(*args):
    url = url_var.get().strip()
    # Solo buscar si ya se hizo una búsqueda manual y la URL parece válida
    if busqueda_manual_realizada[0]:
        if url.startswith("http") and ("youtube.com" in url or "youtu.be" in url):
            cargar_formatos()

# Vincular el evento de cambio
url_var.trace_add("write", on_url_change)

# También puedes buscar al presionar Enter en el campo URL
def buscar_manual(event=None):
    busqueda_manual_realizada[0] = True
    cargar_formatos()

entry_url.bind("<Return>", buscar_manual)
bt_search.config(command=buscar_manual)

# Tipo
ttk.Label(frame, text="Tipo:").grid(row=2, column=0, sticky="w", pady=5)
tipo_combo = ttk.Combobox(frame, textvariable=tipo_var, values=["Video","Audio"], width=18, state="readonly")
tipo_combo.grid(row=2, column=1, sticky="ew", pady=5)
tipo_combo.bind('<<ComboboxSelected>>', on_tipo_change)

# Formato
ttk.Label(frame, text="Formato:").grid(row=3, column=0, sticky="w", pady=5)
formato_combo = ttk.Combobox(frame, textvariable=formato_var, values=[], width=18, state="disabled")
formato_combo.grid(row=3, column=1, sticky="ew", pady=5)

# Calidad
ttk.Label(frame, text="Calidad:").grid(row=4, column=0, sticky="w", pady=5)
calidad_combo = ttk.Combobox(frame, textvariable=calidad_var, values=[], width=18, state="disabled")
calidad_combo.grid(row=4, column=1, sticky="ew", pady=5)

# Miniatura
thumbnail_label = Label(frame)
thumbnail_label.grid(row=2, column=2, rowspan=3, padx=10, sticky="nsew")

# Ubicación
ttk.Label(frame, text="Ubicación:").grid(row=5, column=0, sticky="w", pady=5)
entry_loc = ttk.Entry(frame, textvariable=ubicacion_var, width=40)
entry_loc.grid(row=5, column=1, pady=5, padx=5, sticky="ew")
bt_elegir = ttk.Button(frame, text="Elegir carpeta", command=elegir_ubicacion, bootstyle=PRIMARY, state='disabled')
bt_elegir.grid(row=5, column=2, padx=5, pady=5, sticky="ew")

# Barra de progreso
progress_bar = ttk.Progressbar(frame, variable=progress_var, length=500, maximum=100)
progress_bar.grid(row=6, column=0, columnspan=3, pady=(10,0), sticky="ew")

# NUEVO: Etiqueta de estado
status_label = ttk.Label(frame, text="Esperando...", font=("Segoe UI", 11, "italic"))
status_label.grid(row=7, column=0, columnspan=3, pady=(2,0), sticky="ew")

# Descargar
btn = ttk.Button(frame, text="Descargar", command=descargar_video, bootstyle=SUCCESS, state='disabled')
btn.grid(row=8, column=1, pady=20, sticky="ew")


# Ajustar el estilo del footer con fondo oscuro
style.configure("Dark.TLabel", background="#2E2E2E", foreground="white", font=("Segoe UI", 10, "italic underline"))

# --- Al iniciar la app, cargar la última carpeta si existe ---
ultima = cargar_ultima_carpeta()
if ultima:
    ubicacion_var.set(ultima)

# Footer bonito y profesional
def on_enter_footer(event):
    footer.config(font=("Segoe UI", 11, "italic underline"), foreground="#00BFFF")

def on_leave_footer(event):
    footer.config(font=("Segoe UI", 11, "italic"), foreground="#FFFFFF")

# Separador con espacio adicional para mejorar la estética
separator = ttk.Separator(frame, orient="horizontal")
separator.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(15, 0))

# Footer centrado y con fondo oscuro y color destacado
footer = ttk.Label(
    frame,
    text="Hecho por JOMB S.A.S | Visita nuestro sitio web",
    background="#2E0E4B",
    foreground="#FFFFFF",
    font=("Segoe UI", 11, "italic"),
    cursor="hand2",
    anchor="center",
    padding=8
)
footer.grid(row=10, column=0, columnspan=3, pady=(10, 10), sticky="ew")

footer.bind("<Button-1>", lambda e: webbrowser.open_new("https://jhojanomb.github.io/JOMB/"))
footer.bind("<Enter>", on_enter_footer)
footer.bind("<Leave>", on_leave_footer)

# Iniciar aplicación
ttkwindow.mainloop()