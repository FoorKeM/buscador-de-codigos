#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lanzador delgado de Buscador de Codigos.

Se instala UNA sola vez en la maquina de cada usuario (siempre con el mismo
nombre de archivo, sin numero de version, para que accesos directos y
anclados al taskbar sigan funcionando entre actualizaciones). En cada
apertura:

  1. Revisa cual es la ultima release en GitHub (busca un asset .zip).
  2. Si esa version no esta cacheada en
     %LOCALAPPDATA%\\BuscadorCodigos\\versions\\<tag>, la descarga y
     descomprime ahi (unica vez que tarda algo).
  3. Abre el .exe real desde esa carpeta cacheada y se cierra.

Si no hay internet pero ya existe una version cacheada, la abre directo sin
bloquear ni mostrar avisos. Si no hay internet y tampoco hay nada cacheado
todavia, muestra un error indicando que hace falta conexion la primera vez.

Este archivo se compila aparte del programa principal (ver
BuscadorCodigosLauncher.spec) para que el .exe que ve el usuario final quede
chico: no importa numpy/pandas/playwright, asi que PyInstaller no los
empaqueta aqui.
"""

import sys
import os
import json
import shutil
import zipfile
import tempfile
import subprocess
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

GITHUB_REPO = "FoorKeM/buscador-de-codigos"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
LAUNCHER_VERSION = "1.0"

APPDATA_DIR = Path(os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")) / "BuscadorCodigos"
VERSIONS_DIR = APPDATA_DIR / "versions"
STATE_PATH = APPDATA_DIR / "launcher_state.json"


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _find_installed_exe(tag: str):
    if not tag:
        return None
    folder = VERSIONS_DIR / tag
    if not folder.exists():
        return None
    candidates = sorted(folder.glob("*.exe"))
    return candidates[0] if candidates else None


def _get_latest_release_info():
    req = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"BuscadorCodigosLauncher/{LAUNCHER_VERSION}",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tag = str(data.get("tag_name", "")).strip()
    zip_asset = None
    for asset in data.get("assets", []):
        name = str(asset.get("name", ""))
        if name.lower().endswith(".zip"):
            zip_asset = asset
            break
    if not tag or zip_asset is None:
        return None
    return {
        "tag": tag,
        "url": zip_asset.get("browser_download_url"),
        "size": int(zip_asset.get("size") or 0),
    }


def _download_zip(url: str, expected_size: int = 0) -> Path:
    tmp_dir = Path(tempfile.gettempdir()) / "BuscadorCodigosLauncher"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / "update.zip"
    req = urllib.request.Request(url, headers={"User-Agent": f"BuscadorCodigosLauncher/{LAUNCHER_VERSION}"})
    written = 0
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            written += len(chunk)
    if expected_size and written != expected_size:
        raise RuntimeError(f"Descarga incompleta ({written:,} de {expected_size:,} bytes).")
    if not zipfile.is_zipfile(dest):
        raise RuntimeError("El archivo descargado no es un paquete ZIP valido.")
    return dest


def _install_version(zip_path: Path, tag: str) -> Path:
    scratch = Path(tempfile.gettempdir()) / "BuscadorCodigosLauncher" / f"extract-{tag}"
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(scratch)

    # El ZIP puede traer la carpeta de la version como unico elemento raiz,
    # o el contenido (exe + _internal) directamente sin carpeta contenedora.
    entries = list(scratch.iterdir())
    package_root = entries[0] if len(entries) == 1 and entries[0].is_dir() else scratch

    exe_candidates = sorted(package_root.glob("*.exe"))
    if not exe_candidates:
        raise RuntimeError("El paquete descargado no contiene un ejecutable (.exe).")
    exe_name = exe_candidates[0].name

    dest_dir = VERSIONS_DIR / tag
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(package_root), str(dest_dir))
    shutil.rmtree(scratch, ignore_errors=True)

    installed_exe = dest_dir / exe_name
    if not installed_exe.exists():
        raise RuntimeError("No se pudo instalar el paquete descargado.")
    with open(installed_exe, "rb") as fh:
        if fh.read(2) != b"MZ":
            raise RuntimeError("El ejecutable instalado no parece ser valido.")
    try:
        zip_path.unlink()
    except Exception:
        pass
    return installed_exe


def _cleanup_old_versions(keep_tag: str) -> None:
    if not VERSIONS_DIR.exists():
        return
    for folder in VERSIONS_DIR.iterdir():
        if folder.is_dir() and folder.name != keep_tag:
            shutil.rmtree(folder, ignore_errors=True)


def _launch(exe_path: Path) -> None:
    subprocess.Popen(
        [str(exe_path)],
        cwd=str(exe_path.parent),
        close_fds=True,
    )


def _show_progress_and_install(latest: dict, cached_exe):
    root = tk.Tk()
    root.withdraw()
    progress = tk.Toplevel(root)
    progress.title("Buscador de Códigos")
    progress.resizable(False, False)
    progress.protocol("WM_DELETE_WINDOW", lambda: None)
    frm = ttk.Frame(progress, padding=16)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=f"Preparando la versión {latest['tag']}…").pack(anchor="w")
    pb = ttk.Progressbar(frm, mode="indeterminate", length=320)
    pb.pack(fill="x", pady=(10, 0))
    pb.start(10)
    try:
        progress.update_idletasks()
        w, h = progress.winfo_width(), progress.winfo_height()
        sw, sh = progress.winfo_screenwidth(), progress.winfo_screenheight()
        progress.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
    except Exception:
        pass
    progress.update()

    try:
        zip_path = _download_zip(latest["url"], int(latest.get("size") or 0))
        progress.update()
        installed_exe = _install_version(zip_path, latest["tag"])
        _cleanup_old_versions(latest["tag"])
        _save_state({"tag": latest["tag"]})
        progress.destroy()
        root.destroy()
        _launch(installed_exe)
    except Exception as exc:
        progress.destroy()
        if cached_exe is not None:
            # Si falla la descarga/instalacion pero ya hay una version
            # cacheada, seguimos con esa en vez de dejar al usuario sin nada.
            root.destroy()
            _launch(cached_exe)
            return
        messagebox.showerror(
            "No se pudo actualizar",
            "No se pudo descargar la última versión y no hay ninguna "
            f"instalada todavía.\n\nDetalle: {exc}",
        )
        root.destroy()


def main() -> None:
    state = _load_state()
    cached_tag = state.get("tag", "")
    cached_exe = _find_installed_exe(cached_tag)

    latest = None
    network_error = None
    try:
        latest = _get_latest_release_info()
    except Exception as exc:
        network_error = exc

    if latest and latest.get("url") and latest["tag"] != cached_tag:
        _show_progress_and_install(latest, cached_exe)
        return

    if cached_exe is not None:
        _launch(cached_exe)
        return

    root = tk.Tk()
    root.withdraw()
    if network_error is not None:
        messagebox.showerror(
            "Sin conexión",
            "No se pudo conectar a internet para descargar el programa y no "
            "hay ninguna versión instalada todavía.\n\n"
            "Conectate a internet e intentá de nuevo.",
        )
    else:
        messagebox.showerror(
            "Sin versión disponible",
            "Todavía no hay ninguna versión publicada para descargar, y no "
            "hay ninguna instalada en esta máquina.\n\n"
            "Avisale al administrador del programa.",
        )
    root.destroy()


if __name__ == "__main__":
    main()
