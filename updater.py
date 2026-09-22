# updater.py
import requests
import webbrowser
from consts import GITHUB_REPO
from utils import version_tuple, is_newer_version

def get_github_latest_release(repo=GITHUB_REPO, token=None, timeout=10):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f"token {token}"
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def check_for_updates_background(local_version, ui_status_cb=None, ui_show_dialog_cb=None):
    try:
        release = get_github_latest_release()
        if not release:
            if ui_status_cb: ui_status_cb("No se pudo consultar actualizaciones.")
            return
        tag_name = release.get('tag_name') or release.get('name') or ''
        remote_version = tag_name.lstrip('vV') if tag_name else release.get('name','0.0.0')
        if is_newer_version(remote_version, local_version):
            # ui_show_dialog_cb debe mostrar diálogo y devolver True/False
            if ui_show_dialog_cb and ui_show_dialog_cb(remote_version, local_version):
                url = release.get('html_url', f"https://github.com/{GITHUB_REPO}/releases")
                try: webbrowser.open(url)
                except: pass
            else:
                if ui_status_cb: ui_status_cb(f"Actualización disponible: {remote_version}")
        else:
            if ui_status_cb: ui_status_cb(f"Versión actual: {local_version}")
    except Exception as e:
        if ui_status_cb: ui_status_cb("Error comprobando actualizaciones")
