# youtube_core.py
import io
import os
import re
import subprocess
import tempfile
import urllib.request

import imageio_ffmpeg as ffmpeg
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TDRC, TIT2, TPE1, ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image
from pytubefix import YouTube

# Referencia global al estado de la aplicación
_app_state_ref = {}

FFMPEG_PATH = ffmpeg.get_ffmpeg_exe()


def set_app_state_ref(ref):
    """Guarda la referencia al diccionario de estado global de la aplicación."""
    global _app_state_ref
    if isinstance(ref, dict):
        _app_state_ref = ref


def parse_artist_title(title, author=None):
    """Extrae y limpia de forma precisa el título de la canción y el artista."""
    if not title:
        return (None, author)

    # 1. Limpieza de etiquetas irrelevantes del video
    clean_title = re.sub(
        r"(?i)\s*[\(\[\{]\s*(official\s*(music\s*)?video|lyric\s*video|audio|hd|4k|remastered|out\s*now)\s*[\)\]\}]",
        "",
        title,
    )
    clean_title = clean_title.strip()

    # Limpiar el nombre del canal (remover 'VEVO', '- Topic', etc.)
    clean_author = author
    if clean_author:
        clean_author = re.sub(r"(?i)\s*-\s*topic|\s*vevo$", "", clean_author).strip()

    # 2. Separadores comunes entre Artista - Título
    seps = [" - ", " — ", " – ", " | "]
    for sep in seps:
        if sep in clean_title:
            left, right = clean_title.split(sep, 1)
            # Si la parte izquierda tiene pocas palabras, suele ser el artista
            if len(left.split()) <= 5:
                return (right.strip(), left.strip())
            return (left.strip(), right.strip())

    # 3. Formato "Título by Artista"
    m = re.search(r"^(?P<title>.+)\s+[bB]y\s+(?P<artist>.+)$", clean_title)
    if m:
        return (m.group("title").strip(), m.group("artist").strip())

    return (clean_title, clean_author)


def fetch_best_thumbnail(yt_obj, timeout=5):
    """Obtiene los bytes de la miniatura de mayor calidad disponible y la convierte a JPEG puro."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    raw_data = None

    # 1. Intentar desde thumbnail_url
    try:
        thumb_url = getattr(yt_obj, "thumbnail_url", None)
        if thumb_url:
            req = urllib.request.Request(thumb_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as u:
                data = u.read()
                if len(data) > 1024:
                    raw_data = data
    except Exception:
        pass

    # 2. Intentar buscando en player_response
    if not raw_data:
        try:
            pr = getattr(yt_obj, "player_response", {})
            thumbs = (
                pr.get("videoDetails", {})
                .get("thumbnail", {})
                .get("thumbnails", [])
            )
            if thumbs:
                thumbs_sorted = sorted(
                    thumbs, key=lambda x: x.get("width", 0), reverse=True
                )
                for t in thumbs_sorted:
                    url = t.get("url")
                    if url:
                        try:
                            req = urllib.request.Request(url, headers=headers)
                            with urllib.request.urlopen(req, timeout=timeout) as u:
                                data = u.read()
                                if len(data) > 1024:
                                    raw_data = data
                                    break
                        except Exception:
                            continue
        except Exception:
            pass

    # 3. Intentar formateando la URL directa por ID
    if not raw_data:
        video_id = getattr(yt_obj, "video_id", None)
        if video_id:
            for suf in ("maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg"):
                url = f"https://img.youtube.com/vi/{video_id}/{suf}"
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=timeout) as u:
                        data = u.read()
                        if len(data) > 2048:
                            raw_data = data
                            break
                except Exception:
                    continue

    # Normalizar la imagen a formato JPEG estandarizado (evita errores con WebP/PNG en metadatos)
    if raw_data:
        try:
            img = Image.open(io.BytesIO(raw_data)).convert("RGB")
            out_buffer = io.BytesIO()
            img.save(out_buffer, format="JPEG", quality=95)
            return out_buffer.getvalue()
        except Exception as e:
            print(f"Error normalizando miniatura a JPEG: {e}")
            return raw_data

    return None


def convertir(input_path, output_path, bitrate=None, title=None, artist=None):
    """Convierte un archivo usando FFmpeg e inyecta metadatos básicos de contenedor."""
    try:
        target_ext = os.path.splitext(output_path)[1].lstrip(".").lower()
        cmd = [FFMPEG_PATH, "-y", "-i", input_path]

        if title:
            cmd += ["-metadata", f"title={title}"]
        if artist:
            cmd += ["-metadata", f"artist={artist}"]

        if target_ext == "mp3":
            cmd += ["-vn", "-c:a", "libmp3lame"]
        elif target_ext in ("m4a", "aac"):
            cmd += ["-vn", "-c:a", "aac"]
        elif target_ext == "flac":
            cmd += ["-vn", "-c:a", "flac"]
        elif target_ext == "wav":
            cmd += ["-vn", "-c:a", "pcm_s16le"]
        elif target_ext == "mp4":
            cmd += ["-c:v", "copy", "-c:a", "aac"]

        if bitrate and target_ext in ("mp3", "m4a", "aac", "wma"):
            cmd += ["-b:a", bitrate]

        cmd.append(output_path)
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        if os.path.exists(input_path):
            os.remove(input_path)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error durante la conversión con FFmpeg: {e}")


def agregar_metadatos_y_miniatura(
    out_file,
    yt_obj,
    img_data=None,
    title_override=None,
    artist_override=None,
):
    """Agrega metadatos ID3/Vorbis/MP4 y portada al archivo de salida."""
    try:
        lower = out_file.lower()
        title_val = title_override or getattr(yt_obj, "title", None)
        artist_val = artist_override or getattr(yt_obj, "author", None)
        publish = getattr(yt_obj, "publish_date", None)

        # 1. Archivos MP3 (ID3v2.3)
        if lower.endswith(".mp3"):
            try:
                tags = ID3(out_file)
            except ID3NoHeaderError:
                tags = ID3()

            if title_val:
                tags.delall("TIT2")
                tags.add(TIT2(encoding=3, text=title_val))
            if artist_val:
                tags.delall("TPE1")
                tags.add(TPE1(encoding=3, text=artist_val))
            if publish:
                tags.delall("TDRC")
                tags.add(TDRC(encoding=3, text=str(publish)))
            if img_data:
                tags.delall("APIC")
                tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Cover",
                        data=img_data,
                    )
                )
            tags.save(out_file, v2_version=3)
            return "Metadatos y carátula MP3 agregados."

        # 2. Archivos FLAC (Vorbis Comments + Picture)
        elif lower.endswith(".flac"):
            audio = FLAC(out_file)
            if title_val:
                audio["title"] = title_val
            if artist_val:
                audio["artist"] = artist_val
            if publish:
                audio["date"] = str(publish)
            if img_data:
                pic = Picture()
                pic.data = img_data
                pic.type = 3
                pic.mime = "image/jpeg"
                audio.add_picture(pic)
            audio.save()
            return "Metadatos y carátula FLAC agregados."

        # 3. Archivos MP4 / M4A / AAC
        elif lower.endswith((".m4a", ".mp4", ".aac", ".alac")):
            audio = MP4(out_file)
            if title_val:
                audio["\xa9nam"] = [title_val]
            if artist_val:
                audio["\xa9ART"] = [artist_val]
            if publish:
                audio["\xa9day"] = [str(publish)]
            if img_data:
                audio["covr"] = [
                    MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)
                ]
            audio.save()
            return "Metadatos y carátula M4A/MP4 agregados."

        return "Metadatos del contenedor aplicados correctamente."

    except Exception as e:
        return f"Aviso sobre metadatos: {e}"


def download(
    url,
    tipo,
    formato,
    calidad,
    ubicacion,
    save_name_base,
    progress_cb=None,
    status_cb=None,
    finished_cb=None,
    error_cb=None,
):
    """Descarga de medios con conversión e integración completa de metadatos."""
    try:
        if status_cb:
            status_cb("Conectando con YouTube...")

        def _on_progress(stream_obj, chunk, bytes_remaining):
            total = getattr(stream_obj, "filesize", 0) or 0
            if total and progress_cb:
                downloaded = total - bytes_remaining
                percent = (downloaded / total) * 100
                progress_cb(percent)

        yt = YouTube(url, client="ANDROID", on_progress_callback=_on_progress)

        parsed_title, parsed_artist = parse_artist_title(
            getattr(yt, "title", None), getattr(yt, "author", None)
        )
    except Exception as e:
        if error_cb:
            error_cb(f"No se pudo procesar la URL: {e}")
        return

    os.makedirs(ubicacion, exist_ok=True)
    tmp_dir = tempfile.gettempdir()

    extra_formats = ["mp3", "wav", "aiff", "flac", "alac", "wma"]
    chosen_format = formato if formato else ("mp3" if tipo == "audio" else "mp4")
    final_name = f"{save_name_base}.{chosen_format}"
    out_file = os.path.join(ubicacion, final_name)

    try:
        # Descargar miniatura al inicio para optimizar tiempos
        if status_cb:
            status_cb("Obteniendo miniatura de alta calidad...")
        img_data = fetch_best_thumbnail(yt)

        if tipo == "video":
            if status_cb:
                status_cb("Buscando stream de video...")

            stream = next(
                (
                    s
                    for s in yt.streams.filter(progressive=True)
                    if s.resolution == calidad
                ),
                None,
            )
            if not stream:
                stream = next(
                    (
                        s
                        for s in yt.streams.filter(adaptive=True, only_video=True)
                        if s.resolution == calidad
                    ),
                    None,
                )
            if not stream:
                stream = (
                    yt.streams.filter(progressive=True).get_highest_resolution()
                )

            if not stream:
                if error_cb:
                    error_cb("No se encontró un stream de video compatible.")
                return

            temp_file = stream.download(
                output_path=tmp_dir, filename_prefix="tmp_vid_"
            )
            temp_ext = os.path.splitext(temp_file)[1].lstrip(".").lower()

            if chosen_format in extra_formats or temp_ext != chosen_format:
                if status_cb:
                    status_cb("Convirtiendo video...")
                convertir(
                    temp_file,
                    out_file,
                    title=parsed_title,
                    artist=parsed_artist,
                )
            else:
                os.replace(temp_file, out_file)

        else:  # Modo Audio
            if status_cb:
                status_cb("Buscando stream de audio...")

            stream = (
                yt.streams.filter(only_audio=True).order_by("abr").desc().first()
            )
            if not stream:
                if error_cb:
                    error_cb("No se encontró un stream de audio.")
                return

            temp_file = stream.download(
                output_path=tmp_dir, filename_prefix="tmp_aud_"
            )
            temp_ext = os.path.splitext(temp_file)[1].lstrip(".").lower()

            bitrate = None
            if calidad:
                nums = re.sub(r"[^0-9]", "", calidad)
                if nums:
                    bitrate = f"{nums}k"

            if chosen_format in extra_formats or temp_ext != chosen_format:
                if status_cb:
                    status_cb("Convirtiendo audio...")
                convertir(
                    temp_file,
                    out_file,
                    bitrate=bitrate,
                    title=parsed_title,
                    artist=parsed_artist,
                )
            else:
                os.replace(temp_file, out_file)

        # Inyección de metadatos avanzada y carátula
        if status_cb:
            status_cb("Inyectando etiquetas y carátula...")
        meta_res = agregar_metadatos_y_miniatura(
            out_file,
            yt,
            img_data=img_data,
            title_override=parsed_title,
            artist_override=parsed_artist,
        )

        if status_cb:
            status_cb("Finalizado.")
        if finished_cb:
            finished_cb("Proceso completado con éxito.", f"{out_file}\n{meta_res}")

    except Exception as e:
        if error_cb:
            error_cb(f"Ocurrió un error en la descarga: {e}")