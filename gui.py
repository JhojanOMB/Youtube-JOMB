import os
import sys
import threading
import subprocess

from PIL import Image

import customtkinter as ctk
from tkinter import filedialog


# ============================================================
# IMPORTS SECUNDARIOS CON FALLBACKS ROBUSTOS
# ============================================================

try:
    import storage
except ImportError:
    class storage:
        @staticmethod
        def load_app_state():
            return {}

        @staticmethod
        def save_app_state(state):
            pass


try:
    import youtube_core

    if not hasattr(youtube_core, "set_app_state_ref"):
        youtube_core.set_app_state_ref = lambda ref: None

except ImportError:
    class youtube_core:
        FFMPEG_PATH = "ffmpeg"

        @staticmethod
        def set_app_state_ref(ref):
            pass

        @staticmethod
        def fetch_best_thumbnail(yt_obj, timeout=5):
            return None

        @staticmethod
        def parse_artist_title(title, author=None):
            return title, author

        @staticmethod
        def agregar_metadatos_y_miniatura(
            out_file,
            yt_obj,
            img_data=None,
            title_override=None,
            artist_override=None,
        ):
            return "Módulo youtube_core no disponible."


try:
    import updater

    if not hasattr(updater, "check_for_updates_async"):
        updater.check_for_updates_async = lambda callback: None

except ImportError:
    class updater:
        @staticmethod
        def check_for_updates_async(callback):
            pass


try:
    import utils

    if not hasattr(utils, "download_image_pil"):
        utils.download_image_pil = lambda url: None

    if not hasattr(utils, "sanitize_filename"):
        utils.sanitize_filename = lambda name: name

except ImportError:
    class utils:
        @staticmethod
        def download_image_pil(url):
            return None

        @staticmethod
        def sanitize_filename(name):
            return name


try:
    import consts
except ImportError:
    class consts:
        APP_NAME = "Downloader Pro"
        APP_VERSION = "2.1.0"


# ============================================================
# PYTUBEFIX
# ============================================================

try:
    from pytubefix import YouTube
except ImportError:
    YouTube = None


# ============================================================
# HELPER WRAPPER DE CREACIÓN
# ============================================================

def ctk_create(widget_class, parent, **kwargs):
    """
    Crea widgets CustomTkinter y elimina argumentos que algunas
    versiones podrían no soportar.
    """
    try:
        return widget_class(parent, **kwargs)

    except TypeError:
        safe_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in [
                "corner_radius",
                "hover_color",
                "fg_color",
                "border_width",
                "border_color",
            ]
        }

        return widget_class(parent, **safe_kwargs)


# ============================================================
# CONFIGURACIÓN DE APARIENCIA
# ============================================================

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


root = ctk.CTk()

root.title(
    f"{getattr(consts, 'APP_NAME', 'Downloader')} "
    f"v{getattr(consts, 'APP_VERSION', '2.1.0')}"
)

root.geometry("820x680")
root.minsize(750, 600)


# ============================================================
# ESTADO GLOBAL
# ============================================================

state = storage.load_app_state() or {}

programmatic_set = False
debounce_timer = None

# Caché de streams
raw_video_streams = []
raw_audio_streams = []

# Objeto YouTube actual
yt_instance = None

# Diccionario de streams para la interfaz
streams_dict = {}


# ============================================================
# VARIABLES TKINTER
# ============================================================

url_var = ctk.StringVar(
    value=state.get("last_url", "")
)

tipo_var = ctk.StringVar(
    value=state.get("last_tipo", "Audio (MP3)")
)

calidad_var = ctk.StringVar(
    value="Ingresa un enlace..."
)

save_as_var = ctk.StringVar(
    value=""
)

status_var = ctk.StringVar(
    value="Listo para ingresar un enlace."
)

progress_var = ctk.DoubleVar(
    value=0.0
)


# ============================================================
# COLORES
# ============================================================

COLOR_ACCENT = "#1f538d"
COLOR_ACCENT_HOVER = "#14375e"

COLOR_BG_CARD = (
    "#f9f9f9",
    "#1b1b1c"
)


# ============================================================
# CONTROL DEL ESTADO DE LA UI
# ============================================================

def set_ui_state(mode: str):
    """
    Controla qué controles están disponibles.
    """

    if mode == "loading":

        entry_url.configure(state="disabled")
        bt_search.configure(state="disabled")

        tipo_combo.configure(state="disabled")
        calidad_combo.configure(state="disabled")

        entry_filename.configure(state="disabled")
        bt_elegir.configure(state="disabled")
        bt_download.configure(state="disabled")


    elif mode == "ready":

        entry_url.configure(state="normal")
        bt_search.configure(state="normal")

        tipo_combo.configure(state="normal")
        calidad_combo.configure(state="normal")

        entry_filename.configure(state="normal")
        bt_elegir.configure(state="normal")

        current_quality = calidad_var.get()

        is_valid = (
            current_quality in streams_dict
            and streams_dict[current_quality] is not None
        )

        bt_download.configure(
            state="normal" if is_valid else "disabled"
        )


    elif mode == "disabled":

        entry_url.configure(state="disabled")
        bt_search.configure(state="disabled")

        tipo_combo.configure(state="disabled")
        calidad_combo.configure(state="disabled")

        entry_filename.configure(state="disabled")
        bt_elegir.configure(state="disabled")
        bt_download.configure(state="disabled")


# ============================================================
# ESTADO
# ============================================================

def actualizar_estado(mensaje: str):
    """
    Actualiza el texto de estado desde cualquier hilo.
    """
    root.after(
        0,
        lambda: status_var.set(mensaje)
    )


# ============================================================
# SELECCIÓN DE CARPETA
# ============================================================

def seleccionar_ubicacion():

    current_folder = state.get(
        "download_folder",
        os.path.expanduser("~/Downloads")
    )

    folder = filedialog.askdirectory(
        initialdir=current_folder,
        title="Seleccionar Carpeta de Descarga"
    )

    if folder:

        state["download_folder"] = folder

        storage.save_app_state(state)

        actualizar_estado(
            f"Carpeta guardada: {folder}"
        )


# ============================================================
# ACTUALIZAR CALIDADES
# ============================================================

def actualizar_opciones_calidad(*args):

    global streams_dict

    streams_dict.clear()

    opciones_calidad = []

    tipo_opcion = tipo_var.get()


    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    if "Audio" in tipo_opcion:

        for stream in raw_audio_streams:

            abr = getattr(
                stream,
                "abr",
                "128kbps"
            )

            label = (
                f"Audio {('MP3' if 'MP3' in tipo_opcion else 'M4A')} "
                f"({abr})"
            )

            streams_dict[label] = stream

            opciones_calidad.append(label)


    # --------------------------------------------------------
    # VIDEO
    # --------------------------------------------------------

    else:

        for stream in raw_video_streams:

            res = getattr(
                stream,
                "resolution",
                "720p"
            )

            fps_value = getattr(
                stream,
                "fps",
                None
            )

            fps = (
                f" {fps_value}fps"
                if fps_value
                else ""
            )

            is_progressive = getattr(
                stream,
                "is_progressive",
                False
            )

            tag_type = (
                "Vídeo + Audio"
                if is_progressive
                else "Vídeo HD"
            )

            label = (
                f"Vídeo MP4 {res}{fps} "
                f"({tag_type})"
            )

            streams_dict[label] = stream

            opciones_calidad.append(label)


    # --------------------------------------------------------
    # SIN FORMATOS
    # --------------------------------------------------------

    if not opciones_calidad:

        label_error = "No disponible para este tipo"

        streams_dict[label_error] = None

        opciones_calidad = [
            label_error
        ]


    calidad_combo.configure(
        values=opciones_calidad
    )

    calidad_var.set(
        opciones_calidad[0]
    )


    is_valid = (
        opciones_calidad[0] in streams_dict
        and streams_dict[opciones_calidad[0]] is not None
    )

    bt_download.configure(
        state="normal" if is_valid else "disabled"
    )


# ============================================================
# CARGAR FORMATOS DESDE YOUTUBE
# ============================================================

def _async_cargar_formatos(url: str):

    global raw_video_streams
    global raw_audio_streams
    global yt_instance
    global programmatic_set

    actualizar_estado(
        "Conectando con YouTube y analizando formatos..."
    )

    # --------------------------------------------------------
    # LIMPIAR PREVISUALIZACIÓN ANTERIOR
    # --------------------------------------------------------

    root.after(
        0,
        lambda:
        lbl_thumb.configure(
            image=None,
            text="Cargando miniatura..."
        )
    )

    # --------------------------------------------------------
    # VERIFICAR PYTUBEFIX
    # --------------------------------------------------------

    if not YouTube:

        actualizar_estado(
            "Error: 'pytubefix' no está instalado."
        )

        root.after(
            0,
            lambda: set_ui_state("ready")
        )

        return

    try:

        # ====================================================
        # CREAR OBJETO YOUTUBE
        # ====================================================

        yt_instance = YouTube(
            url,
            client="WEB"
        )

        title = (
            yt_instance.title
            or "Sin título"
        )

        # ====================================================
        # MINIATURA PARA PREVISUALIZACIÓN
        # ====================================================

        try:

            thumb_data = (
                youtube_core.fetch_best_thumbnail(
                    yt_instance
                )
            )

            if thumb_data:

                from io import BytesIO

                pil_img = Image.open(
                    BytesIO(thumb_data)
                ).convert("RGB")

                ctk_img = ctk.CTkImage(
                    light_image=pil_img,
                    dark_image=pil_img,
                    size=(220, 124)
                )

                def actualizar_thumb(
                    imagen=ctk_img
                ):

                    lbl_thumb.configure(
                        image=imagen,
                        text=""
                    )

                    # Mantener referencia para evitar
                    # que Python elimine la imagen.
                    lbl_thumb.image = imagen

                    # Referencia adicional global de la ventana.
                    root._thumbnail_image = imagen

                root.after(
                    0,
                    actualizar_thumb
                )

            else:

                root.after(
                    0,
                    lambda:
                    lbl_thumb.configure(
                        image=None,
                        text="Sin miniatura"
                    )
                )

        except Exception as thumb_error:

            print(
                "Error cargando miniatura:",
                repr(thumb_error)
            )

            root.after(
                0,
                lambda:
                lbl_thumb.configure(
                    image=None,
                    text="Sin miniatura"
                )
            )

        # ====================================================
        # TÍTULO
        # ====================================================

        root.after(
            0,
            lambda:
            lbl_title.configure(
                text=title
            )
        )

        # ====================================================
        # STREAMS DE AUDIO
        # ====================================================

        raw_audio_streams = list(
            yt_instance.streams
            .filter(
                only_audio=True
            )
            .order_by(
                "abr"
            )
            .desc()
        )

        # ====================================================
        # STREAMS DE VIDEO MP4
        # ====================================================

        raw_video_streams = list(
            yt_instance.streams
            .filter(
                file_extension="mp4"
            )
            .order_by(
                "resolution"
            )
            .desc()
        )

        # ====================================================
        # ACTUALIZAR INTERFAZ
        # ====================================================

        def _update_ui():

            global programmatic_set

            programmatic_set = True

            save_as_var.set(
                utils.sanitize_filename(
                    title
                )
            )

            programmatic_set = False

            actualizar_opciones_calidad()

            actualizar_estado(
                "Formatos detectados correctamente."
            )

            set_ui_state(
                "ready"
            )

        root.after(
            0,
            _update_ui
        )

    except Exception as e:

        print(
            "ERROR AL ANALIZAR YOUTUBE:",
            repr(e)
        )

        actualizar_estado(
            f"Error al analizar la URL: {str(e)}"
        )

        root.after(
            0,
            lambda:
            set_ui_state("ready")
        )

# ============================================================
# CARGAR FORMATOS
# ============================================================

def cargar_formatos():

    url = url_var.get().strip()

    if not url:

        status_var.set(
            "Por favor ingresa una URL válida."
        )

        return


    state["last_url"] = url

    storage.save_app_state(state)

    set_ui_state("loading")

    threading.Thread(
        target=_async_cargar_formatos,
        args=(url,),
        daemon=True
    ).start()


# ============================================================
# DETECCIÓN AUTOMÁTICA DE URL
# ============================================================

def _on_url_change_auto(*args):

    global debounce_timer

    if programmatic_set:
        return


    if debounce_timer:

        try:
            root.after_cancel(
                debounce_timer
            )
        except Exception:
            pass


    url = url_var.get().strip()


    if (
        url.startswith("http://")
        or url.startswith("https://")
    ):

        debounce_timer = root.after(
            600,
            cargar_formatos
        )


url_var.trace_add(
    "write",
    _on_url_change_auto
)


# ============================================================
# FFmpeg
# ============================================================

def obtener_ffmpeg_path():
    """
    Obtiene el FFmpeg incluido por imageio-ffmpeg.
    Si youtube_core no lo tiene disponible, usa 'ffmpeg'
    del PATH.
    """

    ffmpeg_path = getattr(
        youtube_core,
        "FFMPEG_PATH",
        None
    )

    if ffmpeg_path and os.path.exists(ffmpeg_path):

        return ffmpeg_path

    return "ffmpeg"


# ============================================================
# CONVERSIÓN DE AUDIO
# ============================================================

def convertir_audio_ffmpeg(
    input_path,
    output_path,
    formato
):
    """
    Convierte el audio usando el FFmpeg incluido
    por imageio-ffmpeg.
    """

    ffmpeg_path = obtener_ffmpeg_path()

    formato = formato.lower()

    if not os.path.exists(input_path):
        print(f"ERROR: El archivo de entrada no existe: {input_path}")
        return False

    if formato == "mp3":

        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-vn",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            output_path
        ]

    elif formato == "wav":

        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-vn",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            output_path
        ]

    else:
        print(f"Formato de conversión no soportado: {formato}")
        return False

    print("\n========== FFMPEG ==========")
    print("Entrada :", input_path)
    print("Salida  :", output_path)
    print("FFmpeg  :", ffmpeg_path)
    print("Comando :", cmd)
    print("============================\n")

    try:

        resultado = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if resultado.returncode != 0:

            print("\n========== ERROR FFMPEG ==========")
            print(resultado.stderr)
            print("==================================\n")

            return False

        if (
            os.path.exists(input_path)
            and input_path != output_path
        ):
            os.remove(input_path)

        return True

    except Exception as e:

        print(
            f"Excepción ejecutando FFmpeg: {e}"
        )

        return False


# ============================================================
# UNIR VIDEO + AUDIO
# ============================================================

def unir_video_audio(
    video_file,
    audio_file,
    output_file
):

    """
    Une un stream de vídeo adaptativo con audio.
    """

    ffmpeg_path = obtener_ffmpeg_path()


    cmd = [
        ffmpeg_path,
        "-y",

        "-i",
        video_file,

        "-i",
        audio_file,

        "-c:v",
        "copy",

        "-c:a",
        "aac",

        "-movflags",
        "+faststart",

        output_file
    ]


    try:

        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        return True


    except Exception as e:

        print(
            f"Error uniendo video/audio: {e}"
        )

        return False


# ============================================================
# AGREGAR METADATOS + CARÁTULA
# ============================================================

def aplicar_metadatos_y_caratula(
    final_output
):

    """
    Obtiene la miniatura y los datos de YouTube
    y los inserta en el archivo final.
    """

    if not yt_instance:

        return (
            "No hay información de YouTube "
            "para aplicar metadatos."
        )


    if not os.path.exists(final_output):

        return (
            "No se encontró el archivo final "
            "para aplicar metadatos."
        )


    try:

        actualizar_estado(
            "Obteniendo carátula de YouTube..."
        )


        # ----------------------------------------------------
        # OBTENER MINIATURA
        # ----------------------------------------------------

        img_data = (
            youtube_core.fetch_best_thumbnail(
                yt_instance
            )
        )


        if img_data:

            actualizar_estado(
                "Carátula obtenida. Aplicando metadatos..."
            )

        else:

            actualizar_estado(
                "No se pudo obtener la carátula. "
                "Aplicando metadatos..."
            )


        # ----------------------------------------------------
        # SEPARAR TÍTULO Y ARTISTA
        # ----------------------------------------------------

        parsed_title, parsed_artist = (
            youtube_core.parse_artist_title(
                getattr(
                    yt_instance,
                    "title",
                    None
                ),
                getattr(
                    yt_instance,
                    "author",
                    None
                )
            )
        )


        print(
            f"Título detectado: {parsed_title}"
        )

        print(
            f"Artista detectado: {parsed_artist}"
        )


        # ----------------------------------------------------
        # INYECTAR METADATOS
        # ----------------------------------------------------

        resultado = (
            youtube_core.agregar_metadatos_y_miniatura(
                final_output,
                yt_instance,
                img_data=img_data,
                title_override=parsed_title,
                artist_override=parsed_artist
            )
        )


        print(
            f"Resultado metadatos: {resultado}"
        )


        return resultado


    except Exception as e:

        print(
            f"Error aplicando metadatos/carátula: {e}"
        )

        return (
            f"Aviso sobre metadatos: {e}"
        )

def limpiar_nombre_archivo(nombre):
    """
    Limpia un nombre de archivo para que sea válido en Windows.
    """

    # Asegurar que sea texto
    nombre = str(nombre).strip()

    # Caracteres no permitidos por Windows
    caracteres_invalidos = '<>:"/\\|?*'

    for caracter in caracteres_invalidos:

        nombre = nombre.replace(
            caracter,
            "_"
        )

    # Reemplazar caracteres de control
    nombre = "".join(
        "_" if ord(caracter) < 32 else caracter
        for caracter in nombre
    )

    # Evitar espacios y puntos al final
    nombre = nombre.rstrip(
        " ."
    )

    # Evitar nombres demasiado largos
    nombre = nombre[:180].rstrip(
        " ."
    )

    # Nombres reservados de Windows
    nombres_reservados = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    if nombre.upper() in nombres_reservados:

        nombre = f"_{nombre}"

    # Evitar nombre vacío
    if not nombre:

        nombre = "archivo_descargado"

    return nombre

# ============================================================
# DESCARGA PRINCIPAL
# ============================================================

def iniciar_descarga():

    global yt_instance

    selected_label = calidad_var.get()

    stream = streams_dict.get(
        selected_label
    )

    if not stream:

        status_var.set(
            "Selecciona un formato válido."
        )

        return

    if not yt_instance:

        status_var.set(
            "Primero analiza un enlace de YouTube."
        )

        return

    # --------------------------------------------------------
    # CARPETA
    # --------------------------------------------------------

    dest_folder = state.get(
        "download_folder",
        os.path.expanduser("~/Downloads")
    )

    os.makedirs(
        dest_folder,
        exist_ok=True
    )

    # --------------------------------------------------------
    # NOMBRE
    # --------------------------------------------------------

    filename = (
        save_as_var.get().strip()
        or "archivo_descargado"
    )

    filename = utils.sanitize_filename(
        filename
    )

    filename = limpiar_nombre_archivo(
        filename
    )

    tipo_seleccionado = tipo_var.get()

    # --------------------------------------------------------
    # LIMPIEZA EXTRA PARA WINDOWS
    # --------------------------------------------------------

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:

        filename = filename.replace(
            char,
            "_"
        )

    # Eliminar espacios/puntos al final
    filename = filename.rstrip(
        " ."
    )

    # Evitar nombres vacíos
    if not filename:

        filename = "archivo_descargado"

    tipo_seleccionado = tipo_var.get()

    # --------------------------------------------------------
    # GUARDAR PREFERENCIAS
    # --------------------------------------------------------

    state["last_url"] = url_var.get().strip()
    state["last_tipo"] = tipo_seleccionado

    storage.save_app_state(state)

    # --------------------------------------------------------
    # BLOQUEAR UI
    # --------------------------------------------------------

    set_ui_state("disabled")

    progress_bar.set(0.0)

    actualizar_estado(
        "Iniciando descarga..."
    )

    # ========================================================
    # HILO DE DESCARGA
    # ========================================================

    def _async_download():

        final_output = None
        temporary_files = []

        try:

            # ------------------------------------------------
            # CALLBACK DE PROGRESO
            # ------------------------------------------------

            def _progress_callback(
                stream_obj,
                chunk,
                bytes_remaining
            ):

                total_size = (
                    getattr(
                        stream_obj,
                        "filesize",
                        0
                    )
                    or 0
                )

                if total_size > 0:

                    bytes_downloaded = (
                        total_size
                        - bytes_remaining
                    )

                    percentage = (
                        bytes_downloaded
                        / total_size
                    )

                    # Descarga = 0-80%
                    root.after(
                        0,
                        lambda p=percentage:
                        progress_bar.set(
                            p * 0.80
                        )
                    )

                    root.after(
                        0,
                        lambda p=percentage:
                        status_var.set(
                            f"Descargando: "
                            f"{int(p * 100)}%"
                        )
                    )

            # Registrar callback
            yt_instance.register_on_progress_callback(
                _progress_callback
            )

            # =================================================
            # AUDIO
            # =================================================

            if (
                "Audio" in tipo_seleccionado
                or "MP3" in tipo_seleccionado
                or "WAV" in tipo_seleccionado
            ):

                actualizar_estado(
                    "Descargando pista de audio..."
                )

                # ---------------------------------------------
                # Determinar extensión
                # ---------------------------------------------

                if "MP3" in tipo_seleccionado:

                    target_ext = "mp3"

                elif "WAV" in tipo_seleccionado:

                    target_ext = "wav"

                else:

                    target_ext = "m4a"

                # ---------------------------------------------
                # Determinar extensión REAL del stream
                # ---------------------------------------------

                stream_ext = getattr(
                    stream,
                    "subtype",
                    None
                )

                if not stream_ext:

                    mime_type = getattr(
                        stream,
                        "mime_type",
                        ""
                    )

                    if "webm" in mime_type.lower():

                        stream_ext = "webm"

                    elif "mp4" in mime_type.lower():

                        stream_ext = "mp4"

                    else:

                        stream_ext = "webm"

                stream_ext = stream_ext.lower()

                # ---------------------------------------------
                # Archivo temporal
                #
                # IMPORTANTE:
                # El archivo temporal ahora conserva la
                # extensión real del stream para que FFmpeg
                # pueda detectar correctamente el formato.
                # ---------------------------------------------

                temp_filename = (
                    f"__temp_audio_"
                    f"{threading.get_ident()}."
                    f"{stream_ext}"
                )

                temp_file = stream.download(
                    output_path=dest_folder,
                    filename=temp_filename
                )

                temporary_files.append(
                    temp_file
                )

                final_output = os.path.join(
                    dest_folder,
                    f"{filename}.{target_ext}"
                )

                # ---------------------------------------------
                # MP3 / WAV
                # ---------------------------------------------

                if target_ext in (
                    "mp3",
                    "wav"
                ):

                    actualizar_estado(
                        f"Convirtiendo audio a "
                        f"{target_ext.upper()}..."
                    )

                    # Si existe, eliminarlo
                    if os.path.exists(
                        final_output
                    ):

                        os.remove(
                            final_output
                        )

                    exito = convertir_audio_ffmpeg(
                        temp_file,
                        final_output,
                        target_ext
                    )

                    if exito:

                        if temp_file in temporary_files:

                            temporary_files.remove(
                                temp_file
                            )

                    else:

                        raise RuntimeError(
                            "No fue posible convertir "
                            f"el audio a {target_ext.upper()}."
                        )

                # ---------------------------------------------
                # M4A
                #
                # Si el stream ya es M4A/MP4, se puede mover
                # directamente.
                #
                # Si viene en WEBM, se convierte a M4A.
                # ---------------------------------------------

                else:

                    if os.path.exists(
                        final_output
                    ):

                        os.remove(
                            final_output
                        )

                    if stream_ext in (
                        "m4a",
                        "mp4"
                    ):

                        os.replace(
                            temp_file,
                            final_output
                        )

                        if temp_file in temporary_files:

                            temporary_files.remove(
                                temp_file
                            )

                    else:

                        actualizar_estado(
                            "Convirtiendo audio a M4A..."
                        )

                        exito = convertir_audio_ffmpeg(
                            temp_file,
                            final_output,
                            "m4a"
                        )

                        if exito:

                            if temp_file in temporary_files:

                                temporary_files.remove(
                                    temp_file
                                )

                        else:

                            raise RuntimeError(
                                "No fue posible convertir "
                                "el audio a M4A."
                            )

            # =================================================
            # VIDEO
            # =================================================

            else:

                actualizar_estado(
                    "Preparando descarga de vídeo..."
                )

                is_progressive = getattr(
                    stream,
                    "is_progressive",
                    True
                )

                final_output = os.path.join(
                    dest_folder,
                    f"{filename}.mp4"
                )

                # ---------------------------------------------
                # VIDEO PROGRESSIVE
                # ---------------------------------------------

                if is_progressive:

                    actualizar_estado(
                        "Descargando vídeo MP4..."
                    )

                    if os.path.exists(
                        final_output
                    ):

                        os.remove(
                            final_output
                        )

                    stream.download(
                        output_path=dest_folder,
                        filename=f"{filename}.mp4"
                    )

                # ---------------------------------------------
                # VIDEO ADAPTATIVO
                # ---------------------------------------------

                else:

                    actualizar_estado(
                        "Descargando vídeo HD..."
                    )

                    # -----------------------------------------
                    # Extensión del vídeo
                    # -----------------------------------------

                    video_ext = getattr(
                        stream,
                        "subtype",
                        None
                    )

                    if not video_ext:

                        mime_type = getattr(
                            stream,
                            "mime_type",
                            ""
                        )

                        if "webm" in mime_type.lower():

                            video_ext = "webm"

                        else:

                            video_ext = "mp4"

                    video_ext = video_ext.lower()

                    # -----------------------------------------
                    # Archivo temporal de vídeo
                    # -----------------------------------------

                    video_temp_name = (
                        f"__temp_video_"
                        f"{threading.get_ident()}."
                        f"{video_ext}"
                    )

                    video_file = stream.download(
                        output_path=dest_folder,
                        filename=video_temp_name
                    )

                    temporary_files.append(
                        video_file
                    )

                    # -----------------------------------------
                    # Buscar mejor audio
                    # -----------------------------------------

                    audio_stream = None

                    if raw_audio_streams:

                        audio_stream = (
                            raw_audio_streams[0]
                        )

                    if not audio_stream:

                        raise RuntimeError(
                            "No se encontró una pista "
                            "de audio para combinar "
                            "con el vídeo."
                        )

                    actualizar_estado(
                        "Descargando pista de audio..."
                    )

                    # -----------------------------------------
                    # Extensión del audio
                    # -----------------------------------------

                    audio_ext = getattr(
                        audio_stream,
                        "subtype",
                        None
                    )

                    if not audio_ext:

                        audio_mime = getattr(
                            audio_stream,
                            "mime_type",
                            ""
                        )

                        if "webm" in audio_mime.lower():

                            audio_ext = "webm"

                        else:

                            audio_ext = "mp4"

                    audio_ext = audio_ext.lower()

                    # -----------------------------------------
                    # Archivo temporal de audio
                    # -----------------------------------------

                    audio_temp_name = (
                        f"__temp_audio_video_"
                        f"{threading.get_ident()}."
                        f"{audio_ext}"
                    )

                    audio_file = (
                        audio_stream.download(
                            output_path=dest_folder,
                            filename=audio_temp_name
                        )
                    )

                    temporary_files.append(
                        audio_file
                    )

                    # -----------------------------------------
                    # Unir
                    # -----------------------------------------

                    actualizar_estado(
                        "Uniendo vídeo HD y audio..."
                    )

                    if os.path.exists(
                        final_output
                    ):

                        os.remove(
                            final_output
                        )

                    merged = unir_video_audio(
                        video_file,
                        audio_file,
                        final_output
                    )

                    if not merged:

                        raise RuntimeError(
                            "FFmpeg no pudo unir "
                            "el vídeo y el audio."
                        )

            # =================================================
            # VERIFICAR ARCHIVO FINAL
            # =================================================

            if not final_output:

                raise RuntimeError(
                    "No se generó el archivo final."
                )

            if not os.path.exists(
                final_output
            ):

                raise RuntimeError(
                    "El archivo final no existe."
                )

            # =================================================
            # METADATOS + CARÁTULA
            # =================================================

            actualizar_estado(
                "Aplicando metadatos y carátula..."
            )

            root.after(
                0,
                lambda: progress_bar.set(0.90)
            )

            resultado_meta = (
                aplicar_metadatos_y_caratula(
                    final_output
                )
            )

            # =================================================
            # FINALIZAR
            # =================================================

            root.after(
                0,
                lambda: progress_bar.set(1.0)
            )

            actualizar_estado(
                "¡Descarga completada! "
                f"{resultado_meta}"
            )

        except Exception as e:

            print(
                "\n========================================"
            )

            print(
                "ERROR DURANTE DESCARGA:"
            )

            print(
                repr(e)
            )

            print(
                "========================================\n"
            )

            root.after(
                0,
                lambda error=e:
                actualizar_estado(
                    f"Error durante la "
                    f"descarga/conversión: {error}"
                )
            )

        finally:

            # -----------------------------------------------
            # LIMPIAR ARCHIVOS TEMPORALES
            # -----------------------------------------------

            for temp_file in temporary_files:

                try:

                    if (
                        temp_file
                        and os.path.exists(temp_file)
                    ):

                        os.remove(
                            temp_file
                        )

                except Exception as cleanup_error:

                    print(
                        "No se pudo eliminar "
                        f"{temp_file}: "
                        f"{cleanup_error}"
                    )

            # -----------------------------------------------
            # QUITAR CALLBACK
            # -----------------------------------------------

            try:

                yt_instance.register_on_progress_callback(
                    lambda *args: None
                )

            except Exception:

                pass

            # -----------------------------------------------
            # DESBLOQUEAR UI
            # -----------------------------------------------

            root.after(
                0,
                lambda: set_ui_state("ready")
            )

    # ========================================================
    # INICIAR HILO
    # ========================================================

    threading.Thread(
        target=_async_download,
        daemon=True
    ).start()

# ============================================================
# CONSTRUCCIÓN DE LA INTERFAZ
# ============================================================

root.grid_columnconfigure(
    0,
    weight=1
)

root.grid_rowconfigure(
    2,
    weight=1
)


# ============================================================
# 1. ENCABEZADO
# ============================================================

header_frame = ctk_create(
    ctk.CTkFrame,
    root,
    corner_radius=10,
    fg_color=COLOR_BG_CARD
)

header_frame.grid(
    row=0,
    column=0,
    padx=16,
    pady=(16, 8),
    sticky="ew"
)

header_frame.grid_columnconfigure(
    1,
    weight=1
)


lbl_url = ctk_create(
    ctk.CTkLabel,
    header_frame,
    text="URL del Vídeo:",
    font=("Segoe UI", 12, "bold")
)

lbl_url.grid(
    row=0,
    column=0,
    padx=(12, 8),
    pady=12,
    sticky="w"
)


entry_url = ctk_create(
    ctk.CTkEntry,
    header_frame,
    textvariable=url_var,
    placeholder_text=(
        "https://www.youtube.com/watch?v=..."
    ),
    height=36
)

entry_url.grid(
    row=0,
    column=1,
    padx=8,
    pady=12,
    sticky="ew"
)


bt_search = ctk_create(
    ctk.CTkButton,
    header_frame,
    text="Buscar",
    width=90,
    height=36,
    command=cargar_formatos
)

bt_search.grid(
    row=0,
    column=2,
    padx=(8, 12),
    pady=12
)


# ============================================================
# 2. PREVISUALIZACIÓN
# ============================================================

preview_frame = ctk_create(
    ctk.CTkFrame,
    root,
    corner_radius=10,
    fg_color=COLOR_BG_CARD
)

preview_frame.grid(
    row=1,
    column=0,
    padx=16,
    pady=8,
    sticky="ew"
)

preview_frame.grid_columnconfigure(
    1,
    weight=1
)


lbl_thumb = ctk_create(
    ctk.CTkLabel,
    preview_frame,
    text="Sin Previsualización",
    width=220,
    height=124,
    corner_radius=6,
    fg_color=(
        "gray85",
        "gray20"
    )
)

lbl_thumb.grid(
    row=0,
    column=0,
    padx=12,
    pady=12
)


info_subframe = ctk_create(
    ctk.CTkFrame,
    preview_frame,
    fg_color="transparent"
)

info_subframe.grid(
    row=0,
    column=1,
    padx=12,
    pady=12,
    sticky="nsew"
)

info_subframe.grid_columnconfigure(
    1,
    weight=1
)


lbl_title = ctk_create(
    ctk.CTkLabel,
    info_subframe,
    text="Pega un enlace para comenzar",
    font=("Segoe UI", 14, "bold"),
    anchor="w",
    wraplength=450
)

lbl_title.grid(
    row=0,
    column=0,
    columnspan=2,
    padx=4,
    pady=(0, 8),
    sticky="w"
)


# ============================================================
# TIPO DE FORMATO
# ============================================================

lbl_tipo = ctk_create(
    ctk.CTkLabel,
    info_subframe,
    text="Formato de Salida:",
    font=("Segoe UI", 11)
)

lbl_tipo.grid(
    row=1,
    column=0,
    padx=4,
    pady=4,
    sticky="w"
)


tipo_combo = ctk_create(
    ctk.CTkOptionMenu,
    info_subframe,
    values=[
        "Audio (MP3)",
        "Audio (WAV)",
        "Audio (M4A)",
        "Vídeo (MP4)"
    ],
    variable=tipo_var,
    command=actualizar_opciones_calidad,
    state="disabled"
)

tipo_combo.grid(
    row=1,
    column=1,
    padx=4,
    pady=4,
    sticky="w"
)


# ============================================================
# CALIDAD
# ============================================================

lbl_calidad = ctk_create(
    ctk.CTkLabel,
    info_subframe,
    text="Calidad / Bitrate:",
    font=("Segoe UI", 11)
)

lbl_calidad.grid(
    row=2,
    column=0,
    padx=4,
    pady=4,
    sticky="w"
)


calidad_combo = ctk_create(
    ctk.CTkOptionMenu,
    info_subframe,
    values=[
        "Esperando enlace..."
    ],
    variable=calidad_var,
    state="disabled"
)

calidad_combo.grid(
    row=2,
    column=1,
    padx=4,
    pady=4,
    sticky="ew"
)


# ============================================================
# 3. OPCIONES DE GUARDADO
# ============================================================

action_frame = ctk_create(
    ctk.CTkFrame,
    root,
    corner_radius=10,
    fg_color=COLOR_BG_CARD
)

action_frame.grid(
    row=2,
    column=0,
    padx=16,
    pady=8,
    sticky="nsew"
)

action_frame.grid_columnconfigure(
    1,
    weight=1
)


lbl_filename = ctk_create(
    ctk.CTkLabel,
    action_frame,
    text="Guardar como:",
    font=("Segoe UI", 11)
)

lbl_filename.grid(
    row=0,
    column=0,
    padx=12,
    pady=(16, 8),
    sticky="w"
)


entry_filename = ctk_create(
    ctk.CTkEntry,
    action_frame,
    textvariable=save_as_var,
    height=34,
    state="disabled"
)

entry_filename.grid(
    row=0,
    column=1,
    padx=8,
    pady=(16, 8),
    sticky="ew"
)


bt_elegir = ctk_create(
    ctk.CTkButton,
    action_frame,
    text="Ubicación",
    width=100,
    height=34,
    command=seleccionar_ubicacion,
    state="disabled"
)

bt_elegir.grid(
    row=0,
    column=2,
    padx=(8, 12),
    pady=(16, 8)
)


# ============================================================
# BOTÓN DESCARGAR
# ============================================================

bt_download = ctk_create(
    ctk.CTkButton,
    action_frame,
    text="DESCARGAR AHORA",
    font=("Segoe UI", 13, "bold"),
    height=42,
    fg_color=COLOR_ACCENT,
    hover_color=COLOR_ACCENT_HOVER,
    command=iniciar_descarga,
    state="disabled"
)

bt_download.grid(
    row=1,
    column=0,
    columnspan=3,
    padx=12,
    pady=16,
    sticky="ew"
)


# ============================================================
# 4. ESTADO Y PROGRESO
# ============================================================

status_frame = ctk_create(
    ctk.CTkFrame,
    root,
    fg_color="transparent"
)

status_frame.grid(
    row=3,
    column=0,
    padx=16,
    pady=(0, 16),
    sticky="ew"
)

status_frame.grid_columnconfigure(
    0,
    weight=1
)


progress_bar = ctk_create(
    ctk.CTkProgressBar,
    status_frame,
    variable=progress_var,
    height=10
)

progress_bar.grid(
    row=0,
    column=0,
    padx=4,
    pady=(0, 6),
    sticky="ew"
)

progress_bar.set(0.0)


lbl_status = ctk_create(
    ctk.CTkLabel,
    status_frame,
    textvariable=status_var,
    font=("Segoe UI", 10),
    anchor="w"
)

lbl_status.grid(
    row=1,
    column=0,
    padx=4,
    pady=0,
    sticky="w"
)


# ============================================================
# INICIALIZACIÓN
# ============================================================

def _post_init():

    # --------------------------------------------------------
    # Pasar el estado a youtube_core
    # --------------------------------------------------------

    youtube_core.set_app_state_ref(
        state
    )


    # --------------------------------------------------------
    # Comprobar actualizaciones
    # --------------------------------------------------------

    try:

        updater.check_for_updates_async(
            callback=lambda msg:
            root.after(
                0,
                lambda: status_var.set(msg)
            )
        )

    except Exception as e:

        print(
            f"Error comprobando actualizaciones: {e}"
        )


    # --------------------------------------------------------
    # Cargar URL anterior
    # --------------------------------------------------------

    if url_var.get().strip():

        cargar_formatos()


# ============================================================
# MAIN
# ============================================================

def main():

    root.after(
        200,
        _post_init
    )

    root.mainloop()


# Alias usado posiblemente por otras partes
ttkwindow = root


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()