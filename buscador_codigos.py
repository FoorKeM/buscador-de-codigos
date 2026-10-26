#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Buscador + Convertidor con gestión de Proveedores integrada (v102)
- v102: revisión automática cada 1 hora y apertura automática post-actualización.
    * Revisa actualizaciones cada 1 hora mientras el programa está abierto.
    * Al actualizar, cierra la versión actual y abre automáticamente la nueva.
    * Mantiene el flujo de instalación como ejecutable separado para evitar sobrescrituras.

- v101: version visible y revisión manual de actualización.
    * Muestra "Versión actual" abajo a la derecha en el menú principal.
    * Agrega botón "Revisar actualización" para consultar GitHub Releases.
    * Avisa si ya está al día o si existe una nueva versión.

- v100: búsqueda por código Tivendo.
    * Nueva casilla "Buscar por código Tivendo" en el buscador.
    * Permite buscar por Identificador/columna A del LISTADO DE ARTÍCULOS
      (ej.: A001650, A001651).
    * Mantiene la salida normal con códigos, barras, empresa, packs y rangos.
    * No guarda preferencia: la casilla inicia desmarcada.

- v99: actualizador sin reinicio automático para evitar fallos de extracción PyInstaller.

- v98: instala la nueva versión como archivo aparte y borra la anterior solo al iniciar bien.

- v97: guarda backups del actualizador en carpeta temporal para no confundirlos con la app.

- v96: limpia backups antiguos tras una actualización exitosa.

- v95: actualizador protegido contra descargas incompletas.
    * Valida tamaño y cabecera del ejecutable antes de reemplazar.
    * Conserva backup del ejecutable anterior durante la actualización.

- v94: mejoras de uso en buscador y menú contextual.
    * Columnas de resultados con ancho automático.
    * Menú contextual inteligente para copiar la columna seleccionada.
    * Limpieza de selección al hacer click en espacio blanco.

- v93: vista de rangos desde Lista de Precios y auto-actualización.
    * Carga de Lista de Precios desde el menú principal.
    * Columnas Rango 1 y Rango 2 en el buscador.
    * Aviso de nueva versión desde GitHub Releases para el ejecutable.

- v92: integración inicial de Maestro de Packs.
    * Carga del Maestro de Packs desde el menú principal.
    * Cruce de artículos contra la columna "Código producto en pack".
    * Columna "Packs" en el buscador y ventana de packs vinculados.

- v91: motor de búsqueda mejorado — 5 mejoras.
    * Ranking de relevancia: resultados ordenados por score (exacto > empieza-con
      > token exacto > contiene en código > contiene en nombre > barcode).
    * Tolerancia a errores tipográficos: cuando no hay resultados, se sugieren
      códigos similares usando difflib (stdlib, sin dependencias nuevas).
    * Índice invertido en memoria: precalculado al cargar la base, acelera
      búsquedas de tokens exactos de O(n) a O(1).
    * Botón único "Copiar..." para agrupar opciones de copiado.
    * Títulos de ventana actualizados a v91.
"""

# ── Historial anterior ────────────────────────────────────────────────────────
# v84: import glob eliminado, guard columnas _parse_catalogo_for_sets,
#      on_change_db conectado a label BD, self.start_view=None en _clear,
#      MAX_RESULTS=500, _strip_accents/_normalize_text movidas al bloque util,
#      found_idx en _apply_striped_rows, ConvertView marcada LEGADO,
#      asimetría cache memoria/disco unificada con _clean_emp.

import sys
import json
import re
import os
import shutil
import threading
import asyncio
import tempfile
import csv
import io
import unicodedata
import difflib
import numpy as np
from html.parser import HTMLParser
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog

import pandas as pd

# Regex de uso global — compilados una vez al importar
_ws_re        = re.compile(r"\s+")           # colapsa whitespace múltiple
_RE_DIGITS    = re.compile(r"(\d+)")         # primer grupo de dígitos
_RE_NO_DIGITS = re.compile(r"\D")            # elimina no-dígitos de precios
_RE_PRICE_DEC = re.compile(r"[.,]\d{2}$")   # detecta decimales en precios
_RE_PRICE_SEP = re.compile(r"[.,]")          # separadores de precio
_RE_COD_IDENT = re.compile(r"^([A-Za-z]+)(\d+)$")  # códigos tipo A020267
_RE_NON_ALNUM = re.compile(r"[^A-Z0-9]")    # elimina no-alfanuméricos (normalizar código)
_RE_LAST_SPACED_DASH = re.compile(r"^.*\s-\s+(\S.*)$")  # separador real: "-" con espacio a ambos lados
_RE_CODE_TOKEN = re.compile(r"[a-z0-9-]{3,}")  # valida cada trozo de codigo (letras/digitos/guiones internos)

STRIPE_COLOR = "#F3F6FA"
MAX_RESULTS  = 500        # máximo de filas mostradas en el buscador
APP_VERSION  = "v151"
DEFAULT_WINDOW_SIZE = (1120, 720)
MIN_WINDOW_SIZE = (960, 620)

UI = {
    "background": "#F4F7FB", "surface": "#FFFFFF", "ink": "#17253C",
    "muted": "#52647C", "border": "#D9E2ED", "primary": "#1557A0",
    "primary_hover": "#0D467F", "success": "#176647", "warning": "#9A5B0C",
    "danger": "#A6353E", "selected": "#DCEBFA",
}


def _configure_ui(root):
    """Una sola configuración visual para todas las vistas ttk."""
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.configure(background=UI["background"])
    style.configure(".", font=("Segoe UI", 10), background=UI["background"], foreground=UI["ink"])
    style.configure("TFrame", background=UI["background"])
    style.configure("Card.TFrame", background=UI["surface"], borderwidth=1, relief="solid")
    style.configure("TLabel", background=UI["background"], foreground=UI["ink"])
    for name, color in (("Title", UI["ink"]), ("Section", UI["ink"]),
                        ("Muted", UI["muted"]), ("Success", UI["success"]),
                        ("Warning", UI["warning"]), ("Danger", UI["danger"])):
        size = 19 if name == "Title" else 12 if name == "Section" else 10
        weight = "bold" if name in {"Title", "Section"} else "normal"
        style.configure(f"{name}.TLabel", font=("Segoe UI", size, weight), foreground=color)
        style.configure(f"Card.{name}.TLabel", background=UI["surface"], foreground=color)
    style.configure("Card.TLabel", background=UI["surface"])
    style.configure("TButton", padding=(12, 7), background=UI["surface"],
                    foreground=UI["ink"], bordercolor=UI["border"])
    style.map("TButton", background=[("active", "#E9F1FA"), ("disabled", "#EFF2F6")],
              foreground=[("disabled", "#8794A4")])
    style.configure("Primary.TButton", background=UI["primary"], foreground="#FFFFFF",
                    bordercolor=UI["primary"], padding=(14, 8))
    style.map("Primary.TButton", background=[("active", UI["primary_hover"]),
                                              ("disabled", "#AAB9CA")],
              foreground=[("disabled", "#F7F9FC")])
    style.configure("TEntry", fieldbackground=UI["surface"], padding=5)
    style.configure("TCombobox", fieldbackground=UI["surface"], padding=5)
    style.configure("TLabelframe", background=UI["background"], bordercolor=UI["border"], padding=10)
    style.configure("TLabelframe.Label", background=UI["background"],
                    foreground=UI["ink"], font=("Segoe UI", 10, "bold"))
    style.configure("Treeview", background=UI["surface"], fieldbackground=UI["surface"],
                    foreground=UI["ink"], rowheight=29, bordercolor=UI["border"], font=("Segoe UI", 10))
    style.map("Treeview", background=[("selected", UI["selected"])],
              foreground=[("selected", UI["ink"])])
    style.configure("Treeview.Heading", background="#EAF0F7", foreground=UI["ink"],
                    padding=(6, 7), font=("Segoe UI", 10, "bold"))
    style.map("Treeview.Heading", background=[("active", "#DAE6F3")])
    style.configure("TProgressbar", background=UI["primary"], troughcolor="#E3EBF4")
    _configure_home_ui(style)


def _configure_home_ui(style):
    """Colores del menú principal, sin cambiar las otras pantallas."""
    background = "#F8F6FC"
    hero = "#241747"
    style.configure("Home.TFrame", background=background)
    style.configure("HomeHero.TFrame", background=background, borderwidth=0, relief="flat")
    style.configure("HomeHeroTitle.TLabel", background=background, foreground=UI["ink"],
                    font=("Segoe UI", 20, "bold"))
    style.configure("HomeHeroEyebrow.TLabel", background=background, foreground=UI["primary"],
                    font=("Segoe UI", 9, "bold"))
    style.configure("HomeHeroSubtitle.TLabel", background=background, foreground=UI["muted"])
    style.configure("HomeSection.TLabel", background=background, foreground=UI["ink"],
                    font=("Segoe UI", 11, "bold"))
    style.configure("HomeMuted.TLabel", background=background, foreground=UI["muted"])
    style.configure("HomeData.TFrame", background="#FFFFFF", borderwidth=1,
                    bordercolor="#E5DFF0", relief="solid")
    style.configure("HomeDataInner.TFrame", background="#FFFFFF")
    style.configure("HomeDataTitle.TLabel", background="#FFFFFF", foreground=UI["ink"],
                    font=("Segoe UI", 12, "bold"))
    for name, color in (("Success", UI["success"]), ("Warning", UI["warning"]),
                        ("Muted", UI["muted"])):
        style.configure(f"HomeData{name}.TLabel", background="#FFFFFF", foreground=color)
    tones = {
        "Blue": ("#E9F5FF", "#146FB6"),
        "Purple": ("#F0E9FF", "#6937D3"),
        "Coral": ("#FFF0EC", "#D45E48"),
        "Teal": ("#E6F8F3", "#0A9475"),
    }
    for tone, (tint, color) in tones.items():
        style.configure(f"Home{tone}.TFrame", background=tint)
        style.configure(f"Home{tone}.TButton", background=color, foreground="#FFFFFF",
                        bordercolor=color, padding=(14, 9), font=("Segoe UI", 11, "bold"))
        style.map(f"Home{tone}.TButton", background=[("active", hero), ("disabled", "#AFA7BD")],
                  foreground=[("disabled", "#E8E4EF")])


def _style_text(widget):
    widget.configure(font=("Segoe UI", 10), background=UI["surface"],
                     foreground=UI["ink"], insertbackground=UI["ink"],
                     selectbackground=UI["selected"], relief="solid", borderwidth=1,
                     highlightthickness=1, highlightbackground=UI["border"],
                     highlightcolor=UI["primary"], padx=8, pady=6)
    return widget


def _paste_text_column(parent, title, label_style="TLabel"):
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, minsize=34)
    parent.rowconfigure(1, weight=1)
    label = ttk.Label(parent, text=title, anchor="w", style=label_style)
    label.grid(row=0, column=0, columnspan=2, sticky="ew")
    parent.bind("<Configure>", lambda event: label.configure(wraplength=max(80, event.width - 8)))
    text = _style_text(tk.Text(parent, wrap="none", height=8, width=1))
    text.grid(row=1, column=0, sticky="nsew")
    vertical = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
    vertical.grid(row=1, column=1, sticky="ns")
    horizontal = ttk.Scrollbar(parent, orient="horizontal", command=text.xview)
    horizontal.grid(row=2, column=0, sticky="ew")
    text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    return text


def _page_heading(parent, title, subtitle=""):
    head = ttk.Frame(parent)
    head.pack(fill="x", pady=(0, 12))
    ttk.Label(head, text=title, style="Title.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(head, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
    return head


def _wizard_steps(parent, current, titles):
    bar = ttk.Frame(parent)
    bar.pack(fill="x", pady=(0, 12))
    for index, title in enumerate(titles, 1):
        style = "Section.TLabel" if index == current else "Muted.TLabel"
        ttk.Label(bar, text=f"{index}. {title}", style=style).pack(side="left", padx=(0, 20))
    return bar

# Cache simple para evitar recargar la BASE DE DATOS desde disco en la misma sesión
_LOAD_DATA_CACHE = {
    'path': None,   # type: Optional[Path]
    'df': None,     # type: Optional[pd.DataFrame]
    'index': None,  # type: Optional[Dict[str, List[int]]]  índice invertido de tokens
}


# =====================================================
#  Semilla de proveedores (incluida en el programa)
# =====================================================
SEED_EMPRESAS: Dict[int, str] = {
    1: "CODIGOS DESACTIVADOS",
    2: "MENAJE",
    3: "PRODUCTOS EN OFERTA DICIEMBRE LC1",
    4: "PRODUCTOS EN OFERTA DICIEMBRE LCO",
    5: "PRODUCTOS EN OFERTA DICIEMBRE BA1",
    6: "CENCOCAL",
    7: "CCU",
    8: "PARTYEXPRESS",
    9: "ICB",
    10: "JOSE ALFREDO CERDA PACHECO",
    11: "MINUTO VERDE",
    12: "ARCOR",
    13: "TECNOPAPEL",
    14: "TRENDY",
    15: "ALIMENTOS ALSAN",
    16: "LEMARC",
    17: "IDEAL",
    18: "TRES MONTES",
    19: "ANDINA",
    20: "AGROSUPER",
    21: "SALTO",
    22: "NESTLE",
    23: "CARMEN GLORIA ORDENES LILLO",
    24: "WELSH",
    25: "FRIGOSORNO",
    26: "SCORE",
    27: "SANTA ELENA",
    28: "JAVCON",
    29: "DISTRIBUIDORA DEL OLMO",
    30: "ARIZTIA",
    31: "EVERCRISP",
    32: "PF",
    33: "COLOMBINA",
    34: "ROCHA GATICA",
    35: "ALFA",
    36: "GHOSH",
    37: "PRONOBEL",
    38: "GREENWORLD",
    39: "LIQUIMAX",
    40: "CIAL",
    41: "DISVET",
    42: "SAN PABLO",
    43: "MONTE CASTELO",
    44: "SURTI VENTAS",
    45: "COLUN",
    46: "SERON",
    47: "MANLAC",
    48: "CAROZZI",
    49: "IGLU",
    50: "VANNI",
    51: "INTERAGRO",
    52: "AVICOLA LA HERRADURA",
    53: "LACSUR",
    54: "DON JORGE SPA",
    55: "LUG PROMARKET",
    56: "DETERGENTES LA SERENA",
    57: "BIOCAV",
    58: "VASTUS",
    59: "INTERNATIONAL FOODS",
    60: "TAMY SPA",
    61: "SOLNORT",
    62: "CV TRADING",
    63: "PORVENIR SPA",
    64: "FINI COMPANY",
    65: "CASO Y CIA",
    66: "ILAN SPA",
    67: "PRODESA",
    68: "SPAK",
    69: "ECOVIDA",
    70: "QUILLAYES SURLAT",
    71: "LIBESA",
    72: "HEAD",
    73: "INTEK",
    74: "CALIGRAFIX",
    75: "EDIPAC",
    76: "ADIOFFICE",
    77: "GLOBAL IMPORT",
    78: "DIAZOL",
    79: "OMAS",
    80: "LIBERTAD SA",
    81: "NAZER Y SILVA",
    82: "TANAX",
    83: "PESQUERA TRANS ANTARTIC",
    84: "MUNDO DELICIAS SPA",
    85: "MELT",
    86: "NAZAR NASSER",
    87: "SOPRODI",
    88: "STARFOOD",
    89: "TRAVERSO",
    90: "CONSERVAS CASTILLO",
    91: "IANSA",
    92: "DEMARIA",
    93: "DINUT",
    94: "DORAL",
    95: "GLAM",
    96: "AMBISA",
    97: "JINPENG",
    98: "YXY",
    99: "GRAN LUZ",
    100: "HUA WEI",
    101: "ELLE",
    102: "LAGOS",
    103: "SAN ANTONIO",
    104: "AGROCOMMERCE",
    105: "SOCOAL",
    106: "LABOCOCH",
    107: "DIACSA",
    108: "INVERSIERRA",
    109: "INNOVA",
    110: "LOS ANGELES",
    111: "FRUTAS Y VERDURAS",
    112: "MUEBLES",
    113: "MULTIPLES PROVEEDORES",
    114: "EMPERADOR",
    115: "GOOD FOOD",
    116: "SOPROLE",
    117: "CAMBIASSO",
    118: "ALIACE",
    119: "WATSON",
    120: "DRUGPLASTIC",
    121: "EIANSA",
    122: "MARITANO",
    123: "AGUACOL",
    124: "ALLENDES HNOS",
    125: "LUCCHETTI",
    126: "LC1 OFERTAS DE 1000",
    127: "UNIFICADOS PRONOBEL",
    128: "OMENACA",
    129: "NUBLE",
    130: "KRAMEL",
    131: "DON QUEBRACHO",
    132: "TEMPUS CLEAN SPA",
    133: "TOPK9",
    134: "FIESTAMANIA",
    135: "UNIFICADOS LIBESA",
    136: "IMPORTADORA BAMBI LIMITADA",
    137: "IMPORTADORA MODA ITALY LMTDA",
    138: "SANTA BARBARA",
    139: "TORRE",
    140: "ARTEL",
    141: "OSORIO E HIJOS LMTDA",
    142: "PAPELERA DEL PACIFICO",
    143: "ALVI SA",
    144: "DISTRIBUIDORA LA MEJOR SPA",
    145: "HARDY KUSCHEL CARRASCO",
    146: "RAPAK CHILE",
    147: "FREDIE ESTEBAN VALDIVIA RETAMAL",
    148: "SIAD TALEB",
    149: "FT FOODS SA",
    150: "SUSANA LEDESMA SUAGUA EIRL",
    152: "MATILHUE",
    153: "AGROSILVA",
    154: "LABORATORIO DURANDIN",
    155: "DISTRIBUIDORA DE INSUMOS",
    156: "ENGEL",
    157: "COMERCIAL TRES A LIMITADA",
    158: "ALCOHOL 20 5",
    159: "DESTILADO 31 5",
    160: "ROSSETTI SPA",
    161: "AGROCOMERCIAL CODIGUA",
    162: "DISTRIBUIDORA JAVIER GONZALEZ",
    163: "SOCIEDAD COMERCIAL IZADORA SYS",
    164: "SOCIEDAD PUNTA DE LOBOS",
    165: "NOVACEITES",
    166: "AGROCOMERCIAL SANTA BARBARA",
    167: "SOCIEDAD ESPINOZA GUERRA",
    168: "BAMBI",
    169: "NUTRISCO",
    170: "EDUARDO ALBERTO PFAU",
    171: "BLM",
    172: "BRICENO",
    173: "PREMIERHOUZ",
    174: "CAMI PLAS",
    175: "GOMEX CONSULTORIA LIMITADA",
    176: "COMERCIALIZADORA GAG",
    177: "GYG",
    178: "SHUN MEI LIMITADA",
    179: "IMPY EXP LULU",
    180: "TAMA SPA",
    181: "RHEIN",
}

# =====================================================
#  Utilidades / Preferencias
# =====================================================
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

HERE = app_dir()
PREF_PATH = HERE / "buscador_prefs.json"

# -----------------------------------------------------
# Cache persistente en disco para la BASE DE DATOS
# -----------------------------------------------------
LOCAL_APPDATA = os.getenv("LOCALAPPDATA")
if LOCAL_APPDATA:
    APP_DATA_DIR = Path(LOCAL_APPDATA) / "BuscadorCodigos"
    CACHE_DIR = APP_DATA_DIR / ".cache"
else:
    APP_DATA_DIR = HERE
    CACHE_DIR = HERE / ".cache"
try:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
CACHE_DB_PATH = CACHE_DIR / "base_codigos_cache.pkl"
CACHE_DB_META = CACHE_DIR / "base_codigos_cache_meta.json"
PACKS_CACHE_PATH = CACHE_DIR / "packs_cache.pkl"
PACKS_CACHE_META = CACHE_DIR / "packs_cache_meta.json"
RANGES_CACHE_PATH = CACHE_DIR / "ranges_cache.pkl"
RANGES_CACHE_META = CACHE_DIR / "ranges_cache_meta.json"
BASE_DB_CACHE_DIR = CACHE_DIR / "bases_generadas"
BASE_DB_CACHE_META = CACHE_DIR / "bases_generadas_meta.json"
try:
    BASE_DB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
AUTO_DOWNLOAD_DIR = APP_DATA_DIR / "auto_downloads"
AUTO_DOWNLOAD_STAGING_DIR = APP_DATA_DIR / "auto_downloads_tmp"
AUTO_CREDENTIALS_PATH = APP_DATA_DIR / "credenciales_auto.json"
DEFAULT_TIVENDO_USUARIO = "sistemamercadohouse@gmail.com"
AUTO_LAST_LOAD_PATH = APP_DATA_DIR / "ultima_carga_automatica.json"
AUTO_DIAG_DIR = APP_DATA_DIR / "diagnosticos_auto"
MERCADOHOUSE_SYNC_DATA_DIR = Path(os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")) / "MercadohouseSync"
MERCADOHOUSE_SYNC_CONFIG_PATH = MERCADOHOUSE_SYNC_DATA_DIR / "config_sucursal.json"
AUTO_SYNC_SUCURSALES = {
    "LIBERTADOR": "LISTA LOS LIBERTADORES 1476",
    "CANTERA": "LISTA LA CANTERA 3055",
    "BALMACEDA": "LISTA BALMACEDA 599",
}
AUTO_SYNC_DEFAULT_SUCURSAL = "LIBERTADOR"

def _base_db_cache_path(listado_path: Path) -> Path:
    """Ruta fija (persistente entre aperturas) de la BASE DE DATOS generada
    para este LISTADO DE ARTICULOS."""
    return BASE_DB_CACHE_DIR / f"MH_TMP_BASE_{listado_path.stem}.xlsx"


def _load_base_db_cache_meta() -> dict:
    try:
        return json.loads(BASE_DB_CACHE_META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_base_db_cache_meta(meta: dict) -> None:
    try:
        BASE_DB_CACHE_META.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _find_fresh_base_db_cache(listado_path: Path) -> Optional[Path]:
    """Devuelve la BASE DE DATOS ya generada para este listado si sigue
    vigente (el listado no cambio de tamano/fecha desde que se generó);
    si el listado se reemplazo por una version mas nueva, devuelve None
    para forzar una regeneracion."""
    candidate = _base_db_cache_path(listado_path)
    if not candidate.exists():
        return None
    try:
        src_mtime = listado_path.stat().st_mtime
    except Exception:
        return None
    entry = _load_base_db_cache_meta().get(str(listado_path.resolve()))
    if not entry or entry.get("src_mtime") != src_mtime:
        return None
    try:
        cols = pd.read_excel(candidate, sheet_name="BASE DE DATOS", nrows=0).columns
        if "Identificador" not in cols:
            return None
    except Exception:
        return None
    return candidate


def _remember_base_db_cache(listado_path: Path) -> None:
    try:
        src_mtime = listado_path.stat().st_mtime
    except Exception:
        return
    meta = _load_base_db_cache_meta()
    meta[str(listado_path.resolve())] = {"src_mtime": src_mtime}
    _save_base_db_cache_meta(meta)


EMP_PATH = HERE / "empresas.json"
JOIN_SEP = "\n"

def load_prefs() -> dict:
    try:
        with open(PREF_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_prefs(prefs: dict):
    try:
        with open(PREF_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_auto_credentials() -> dict:
    try:
        with open(AUTO_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {
                    "usuario": str(data.get("usuario", "")) or DEFAULT_TIVENDO_USUARIO,
                    "password": str(data.get("password", "")),
                }
    except Exception:
        pass
    return {"usuario": DEFAULT_TIVENDO_USUARIO, "password": ""}

def save_auto_credentials(usuario: str, password: str):
    try:
        AUTO_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUTO_CREDENTIALS_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {"usuario": usuario, "password": password},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        pass

def load_auto_last_load() -> dict:
    try:
        with open(AUTO_LAST_LOAD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_auto_last_load(articulos: Path, packs: Path, precios: Path):
    try:
        AUTO_LAST_LOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            "articulos_downloaded_at": datetime.now().isoformat(timespec="seconds"),
            "precios_downloaded_at": datetime.now().isoformat(timespec="seconds"),
            "articulos": str(Path(articulos)),
            "packs": str(Path(packs)),
            "precios": str(Path(precios)),
        }
        with open(AUTO_LAST_LOAD_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def save_auto_articles_load(articulos: Path):
    """Actualiza solo el listado y su fecha; conserva packs y precios."""
    data = load_auto_last_load()
    data.update(articulos=str(Path(articulos)),
                articulos_downloaded_at=datetime.now().isoformat(timespec="seconds"))
    AUTO_LAST_LOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    pending = AUTO_LAST_LOAD_PATH.with_suffix(".json.tmp")
    with open(pending, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    pending.replace(AUTO_LAST_LOAD_PATH)


def _resource_download_label(key, path) -> str:
    data = load_auto_last_load()
    try:
        if path and Path(data.get(key, "")).resolve() == Path(path).resolve():
            date = format_auto_last_load_date(data.get(f"{key}_downloaded_at") or data.get("downloaded_at", ""))
            if date:
                return date
    except (OSError, ValueError):
        pass
    return "sin fecha registrada (archivo manual)"


def article_download_label(path) -> str:
    return _resource_download_label("articulos", path)


def format_auto_last_load_date(value: str) -> str:
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return str(value or "").strip()

def _parse_geometry_size(geometry: str) -> Optional[tuple]:
    m = re.match(r"^(\d+)x(\d+)([+-]\d+[+-]\d+)?$", str(geometry or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), m.group(3) or ""

def _reasonable_root_geometry(root, saved_geometry: str = "") -> str:
    default_w, default_h = DEFAULT_WINDOW_SIZE
    min_w, min_h = MIN_WINDOW_SIZE
    try:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
    except Exception:
        screen_w, screen_h = 1366, 768

    max_w = max(min_w, min(1280, int(screen_w * 0.82)))
    max_h = max(min_h, min(820, int(screen_h * 0.82)))
    w, h, pos = default_w, default_h, ""

    parsed = _parse_geometry_size(saved_geometry)
    if parsed:
        saved_w, saved_h, saved_pos = parsed
        w = min(max(saved_w, min_w), max_w)
        h = min(max(saved_h, min_h), max_h)
        if saved_w <= max_w and saved_h <= max_h:
            pos = saved_pos

    if not pos:
        x = max(0, (screen_w - w) // 2)
        y = max(0, (screen_h - h) // 2)
        pos = f"+{x}+{y}"
    return f"{w}x{h}{pos}"

class AutoDownloadError(Exception):
    pass

class TivendoLoginError(AutoDownloadError):
    """Fallo especificamente al iniciar sesion en Tivendo (usuario/clave
    incorrectos), para poder distinguirlo de otros errores de descarga y
    mostrar un mensaje mas claro + permitir volver a pedir la contraseña."""
    pass

def _clean_auto_download_dir(download_dir: Path = AUTO_DOWNLOAD_DIR) -> int:
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    deleted = 0
    for path in download_dir.iterdir():
        if path.is_file():
            try:
                path.unlink()
                deleted += 1
            except Exception:
                pass
    return deleted

def _auto_active_price_list_name() -> str:
    key = AUTO_SYNC_DEFAULT_SUCURSAL
    try:
        if MERCADOHOUSE_SYNC_CONFIG_PATH.exists():
            data = json.loads(MERCADOHOUSE_SYNC_CONFIG_PATH.read_text(encoding="utf-8"))
            saved_key = str(data.get("sucursal", "")).upper().strip()
            if saved_key in AUTO_SYNC_SUCURSALES:
                key = saved_key
    except Exception:
        pass
    return AUTO_SYNC_SUCURSALES.get(key, AUTO_SYNC_SUCURSALES[AUTO_SYNC_DEFAULT_SUCURSAL])

def _promote_auto_downloads(paths: dict) -> dict:
    AUTO_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _clean_auto_download_dir(AUTO_DOWNLOAD_DIR)
    promoted = {}
    for key, src in paths.items():
        src_path = Path(src)
        dst_path = AUTO_DOWNLOAD_DIR / src_path.name
        shutil.move(str(src_path), str(dst_path))
        promoted[key] = dst_path
    return promoted

def _auto_log_path() -> Path:
    AUTO_DIAG_DIR.mkdir(parents=True, exist_ok=True)
    return AUTO_DIAG_DIR / "carga_automatica.log"

def _auto_log(message: str):
    try:
        with open(_auto_log_path(), "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass

async def _auto_wait_light(page, timeout: int = 15000):
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass

async def _auto_pause(seconds: float = 0.2):
    await asyncio.sleep(seconds)

async def _auto_retry(name: str, action, attempts: int = 3, wait: float = 0.8):
    start = asyncio.get_event_loop().time()
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return await action()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            _auto_log(f"Reintentando {name} ({attempt + 1}/{attempts})")
            await asyncio.sleep(wait)
    elapsed = asyncio.get_event_loop().time() - start
    # Envolvemos el error final con cuantos intentos hizo y cuanto tardo, para
    # que el mensaje de error que ve el usuario ya no se vea IDENTICO a un
    # fallo de un solo intento -- sin esto no habia forma de distinguir "se
    # reintento 3 veces y aun asi Tivendo estuvo lento/caido" de "el
    # reintento no se ejecuto de verdad".
    raise AutoDownloadError(
        f"{name}: sin éxito tras {attempts} intento(s) en {elapsed:.0f}s. "
        f"Último error: {last_error}"
    ) from last_error

async def _auto_launch_browser(playwright, downloads_path: Path):
    kwargs = {
        "headless": True,
        "downloads_path": str(downloads_path),
        "args": [
            "--headless=new",
            "--incognito",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--hide-scrollbars",
            "--mute-audio",
            "--window-position=-32000,-32000",
            "--window-size=1,1",
        ],
    }
    errors = []

    if not getattr(sys, "frozen", False):
        try:
            return await playwright.chromium.launch(**kwargs)
        except Exception as exc:
            errors.append(exc)

    for channel in ("msedge", "chrome"):
        try:
            return await playwright.chromium.launch(channel=channel, **kwargs)
        except Exception as exc:
            errors.append(exc)

    detail = str(errors[-1]) if errors else "sin detalle"
    raise AutoDownloadError(
        "No se pudo abrir un navegador compatible para la carga automática. "
        "Instala Microsoft Edge o Google Chrome.\n\nDetalle: " + detail
    )

async def _auto_new_page(playwright, download_dir: Path = AUTO_DOWNLOAD_DIR):
    browser = await _auto_launch_browser(playwright, download_dir)
    context = await browser.new_context(accept_downloads=True, bypass_csp=True)
    page = await context.new_page()
    return browser, context, page

async def _auto_click_capture_page(context, page, locator, timeout: int = 3500):
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    except Exception:
        PlaywrightTimeoutError = TimeoutError

    try:
        async with context.expect_page(timeout=timeout) as page_info:
            await _auto_retry("click que abre módulo", locator.click)
        new_page = await page_info.value
        await _auto_wait_light(new_page)
        return new_page
    except PlaywrightTimeoutError:
        await _auto_wait_light(page)
        return page

async def _auto_login_tivendo(page, usuario: str, password: str):
    _auto_log("Abriendo login Tivendo")
    await page.goto("https://tivendoapp.defontana.com/login", timeout=30000)
    try:
        await page.wait_for_selector("input", state="visible", timeout=10000)
    except Exception:
        await _auto_wait_light(page)
        if "login" not in page.url.lower():
            _auto_log("Sesion Tivendo reutilizada")
            return
        await page.wait_for_selector("input", state="visible", timeout=20000)

    _auto_log("Ingresando credenciales Tivendo")
    inputs = page.locator("input")
    await inputs.nth(0).click()
    await inputs.nth(0).press_sequentially(usuario, delay=20)
    await _auto_pause()
    await inputs.nth(1).click()
    await inputs.nth(1).press_sequentially(password, delay=20)
    await _auto_pause()
    await page.get_by_role("button", name="Iniciar Sesión").click()
    _auto_log("Esperando redireccion")
    try:
        await page.wait_for_url(lambda url: "login" not in url.lower(), timeout=20000)
    except Exception:
        pass
    await _auto_wait_light(page)
    if "login" in page.url.lower():
        raise TivendoLoginError("Login Tivendo fallido")
    _auto_log("Login Tivendo exitoso")

async def _auto_read_company(page) -> str:
    for text in ("MERCADO HOUSE SPA", "MERCADO HOUSE", "NO USAR"):
        try:
            loc = page.get_by_text(text, exact=False).first
            await loc.wait_for(state="visible", timeout=1200)
            value = (await loc.inner_text()).strip().upper()
            if value:
                return value
        except Exception:
            continue

    selectors = [
        "header p:has-text('MERCADO HOUSE')",
        "header p:has-text('NO USAR')",
        "header span:has-text('MERCADO HOUSE')",
        "header span:has-text('NO USAR')",
        "header div:has-text('MERCADO HOUSE')",
        "header div:has-text('NO USAR')",
        "header [class*='company']",
        "header [class*='empresa']",
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=900)
            value = (await loc.inner_text()).strip().upper()
            if "MERCADO HOUSE" in value or "NO USAR" in value:
                return value
        except Exception:
            continue
    return ""

async def _auto_ensure_mercado_house(page, usuario: str, password: str):
    company = await _auto_read_company(page)
    if not company:
        _auto_log("No se pudo leer empresa activa; se continúa de todas formas")
        return
    if "MERCADO HOUSE" in company:
        return

    clicked = False
    for selector in (
        "header p:has-text('NO USAR')",
        "header span:has-text('NO USAR')",
        "header div:has-text('NO USAR')",
        "text=NO USAR",
    ):
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                await loc.click()
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        raise AutoDownloadError("No se pudo abrir el selector de empresa en Defontana.")

    await _auto_pause(0.3)
    try:
        await page.wait_for_selector("text=MERCADO HOUSE SPA", state="visible", timeout=10000)
    except Exception:
        await page.wait_for_selector("text=MERCADO HOUSE", state="visible", timeout=10000)

    for action in (
        lambda: page.get_by_text("MERCADO HOUSE SPA", exact=True).click(),
        lambda: page.locator("text=MERCADO HOUSE SPA").first.click(),
        lambda: page.locator("text=MERCADO HOUSE").last.click(),
    ):
        try:
            await action()
            break
        except Exception:
            continue
    else:
        raise AutoDownloadError("No se pudo seleccionar MERCADO HOUSE SPA.")

    await _auto_wait_light(page, timeout=20000)
    await _auto_pause(0.5)
    if "login" in page.url.lower():
        await _auto_login_tivendo(page, usuario, password)

    new_company = await _auto_read_company(page)
    if "MERCADO HOUSE" not in new_company:
        raise AutoDownloadError(f"No se pudo confirmar MERCADO HOUSE. Empresa actual: {new_company or 'desconocida'}")

async def _auto_open_pos(context, page):
    pos_page = await _auto_click_capture_page(
        context,
        page,
        page.get_by_text("Punto de Ventas"),
    )
    await _auto_retry(
        "esperar menú 'Artículos' en Punto de Ventas",
        lambda: pos_page.locator("text=Artículos").first.wait_for(state="visible", timeout=25000),
    )
    return pos_page

async def _auto_open_pos_section(pos_page, section_link, menu_text: str = "Artículos", timeout: int = 15000):
    """Abre una sección del menú "Artículos" en el POS de Tivendo. Solo hace
    clic en el menú si el enlace de la sección todavía no aparecio en el
    DOM; si ya aparecio pero tarda en volverse visible (animación/carga
    lenta), NO vuelve a hacer clic — es un menú tipo toggle, asi que un
    segundo clic podria CERRARLO de nuevo justo cuando estaba a punto de
    quedar listo."""
    if await section_link.count() == 0:
        await pos_page.locator(f"text={menu_text}").first.click()
    await section_link.wait_for(state="visible", timeout=timeout)

async def _auto_download_from_pos(pos_page, section_name: str, fallback_name: str, download_dir: Path) -> Path:
    section_link = pos_page.get_by_role("link", name=section_name, exact=True)
    await _auto_retry(
        f"abrir sección '{section_name}' en Artículos",
        lambda: _auto_open_pos_section(pos_page, section_link),
        attempts=4,
        wait=1.5,
    )
    await section_link.click()
    await _auto_retry(
        "esperar botón 'Exportar'",
        lambda: pos_page.get_by_role("button", name="Exportar").wait_for(state="visible", timeout=30000),
    )

    async with pos_page.expect_download(timeout=300000) as download_info:
        await pos_page.get_by_role("button", name="Exportar").click()
    download = await download_info.value
    file_name = download.suggested_filename or fallback_name
    target = Path(download_dir) / file_name
    await download.save_as(str(target))
    if not target.exists():
        raise AutoDownloadError(f"No se encontró el archivo descargado: {target}")
    return target

async def _auto_wait_erp_open(page):
    limit = asyncio.get_event_loop().time() + 45
    while asyncio.get_event_loop().time() < limit:
        for text in ("Ecosistema Digital", "Clientes y Productos", "Listado de Documentos"):
            try:
                if await page.get_by_text(text, exact=True).count() > 0:
                    return
            except Exception:
                pass

        try:
            in_portal = "portal.defontana.com/dashboard" in page.url
            erp_card = page.get_by_text("ERP Digital", exact=True).last
            if in_portal and await erp_card.count() > 0:
                await erp_card.click()
        except Exception:
            pass
        await _auto_pause(0.5)

    raise AutoDownloadError(f"ERP Digital no terminó de abrir. URL actual: {page.url}")

async def _auto_open_erp(context, page):
    erp_page = await _auto_click_capture_page(
        context,
        page,
        page.get_by_text("ERP Digital", exact=True).last,
    )
    await _auto_wait_erp_open(erp_page)
    return erp_page

async def _auto_click_classic_sales_report(page):
    exact_links = page.get_by_role("link", name="Informes de Ventas", exact=True)
    if await exact_links.count() > 0:
        target = exact_links.last
        await target.scroll_into_view_if_needed(timeout=5000)
        try:
            await target.click(timeout=5000)
        except Exception as exc:
            # El menú desplegable de Tivendo a veces queda encima del enlace.
            # Playwright espera que reciba el clic físico y termina agotando el
            # tiempo; activar el enlace directamente evita esa superposición.
            if "intercepts pointer events" not in str(exc):
                raise
            _auto_log("Menú de Tivendo superpuesto a Informes de Ventas; activando el enlace directamente")
            try:
                await target.evaluate("element => element.click()", timeout=5000)
            except Exception as fallback_exc:
                _auto_log(f"También falló el clic directo de Informes de Ventas: {fallback_exc}")
                raise AutoDownloadError(
                    "No se pudo abrir Informes de Ventas porque el menú de Tivendo quedó superpuesto."
                ) from fallback_exc
        return

    result = await page.evaluate(
        """
        () => {
            const normalize = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
            const visible = Array.from(document.querySelectorAll('a, [role="link"], li, div, span'))
                .filter((el) => {
                    const text = normalize(el.innerText || el.textContent);
                    if (text !== 'Informes de Ventas') return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0;
                });
            const target = visible[visible.length - 1];
            if (!target) return { ok: false, count: visible.length };
            target.scrollIntoView({ block: 'center', inline: 'nearest' });
            target.click();
            return { ok: true, count: visible.length };
        }
        """
    )
    if not result.get("ok"):
        raise AutoDownloadError("No se encontró el enlace clásico 'Informes de Ventas'.")

async def _auto_click_lista_precios_tab(page):
    locator = page.locator("text=Lista de Precios").last
    await _auto_retry(
        "esperar pestaña 'Lista de Precios'",
        lambda: locator.wait_for(state="visible", timeout=25000),
    )
    await locator.scroll_into_view_if_needed()

    for action in (
        lambda: locator.click(timeout=5000),
        lambda: locator.click(timeout=5000, force=True),
    ):
        try:
            await action()
            await _auto_pause(0.5)
            return
        except Exception as exc:
            _auto_log(f"Click Lista de Precios reintentado: {exc}")

    clicked = await page.evaluate(
        """
        () => {
            const normalize = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll('a, [role="tab"], [role="link"], li, span, div'))
                .filter((el) => normalize(el.innerText || el.textContent) === 'Lista de Precios' && visible(el));
            const target = candidates[candidates.length - 1];
            if (!target) return false;
            target.scrollIntoView({ block: 'center', inline: 'nearest' });
            target.click();
            return true;
        }
        """
    )
    if not clicked:
        raise AutoDownloadError("No se pudo hacer clic en la pestaña Lista de Precios.")
    await _auto_pause(0.5)

async def _auto_get_price_report_frame(base_page):
    limit = asyncio.get_event_loop().time() + 15
    while asyncio.get_event_loop().time() < limit:
        for frame in base_page.frames:
            try:
                if await frame.locator("input[type='radio']").count() > 0:
                    return frame
            except Exception:
                pass
        await _auto_pause(0.3)
    return base_page

async def _auto_try_confirm_popup_download(popup):
    labels = ("Descargar", "Guardar", "Aceptar", "Excel", "Exportar", "Generar", "Continuar")
    for label in labels:
        locators = (
            popup.get_by_role("button", name=label),
            popup.get_by_role("link", name=label),
            popup.locator(f"button:has-text('{label}'), a:has-text('{label}'), input[value*='{label}']"),
        )
        for locator in locators:
            try:
                if await locator.count() > 0:
                    await locator.first.click(timeout=3000, force=True)
                    _auto_log(f"Confirmación en popup: {label}")
                    return True
            except Exception:
                continue
    return False

async def _auto_wait_price_export_download(erp_page, rframe):
    export_locator = rframe.locator(
        "a:has-text('Exportar'), button:has-text('Exportar'), input[value='Exportar']"
    ).last

    direct_download_task = asyncio.create_task(erp_page.wait_for_event("download", timeout=45000))
    popup_task = asyncio.create_task(erp_page.wait_for_event("popup", timeout=45000))

    try:
        await export_locator.click(force=True)
        done, pending = await asyncio.wait(
            {direct_download_task, popup_task},
            return_when=asyncio.FIRST_COMPLETED,
            timeout=45000,
        )
        if not done:
            raise AutoDownloadError("No comenzó la descarga ni apareció ventana nueva al exportar Lista de Precios.")

        if direct_download_task in done:
            popup_task.cancel()
            _auto_log("Lista de Precios: descarga directa detectada")
            return direct_download_task.result()

        popup = popup_task.result()
        direct_download_task.cancel()
        _auto_log("Lista de Precios: ventana nueva de exportación detectada")
        await _auto_wait_light(popup, timeout=15000)

        popup_download_task = asyncio.create_task(popup.wait_for_event("download", timeout=45000))
        try:
            await _auto_try_confirm_popup_download(popup)
            return await popup_download_task
        finally:
            if not popup_download_task.done():
                popup_download_task.cancel()
            try:
                await popup.close()
            except Exception:
                pass
    finally:
        for task in (direct_download_task, popup_task):
            if not task.done():
                task.cancel()

async def _auto_download_price_ranges(context, page, download_dir: Path) -> Path:
    erp_page = await _auto_open_erp(context, page)

    await erp_page.locator("text=Ventas").first.click()
    await _auto_pause(0.2)
    sales_items = erp_page.locator("text=Ventas")
    if await sales_items.count() >= 2:
        await sales_items.nth(1).click()
    await _auto_pause(0.2)

    await _auto_click_classic_sales_report(erp_page)
    await _auto_click_lista_precios_tab(erp_page)

    rframe = await _auto_get_price_report_frame(erp_page)
    radio_result = await rframe.evaluate(
        """
        () => {
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                const txt = (r.parentElement?.innerText || r.labels?.[0]?.innerText || '');
                if (txt.toLowerCase().includes('una en particular')) {
                    r.click();
                    return 'ok-text';
                }
            }
            if (radios.length >= 2) {
                radios[1].click();
                return 'ok-fallback';
            }
            return 'not-found';
        }
        """
    )
    if radio_result == "not-found":
        raise AutoDownloadError("No se encontró la opción para seleccionar una lista de precios en particular.")

    select_loc = rframe.locator("select").first
    try:
        await select_loc.wait_for(state="visible", timeout=10000)
    except Exception:
        pass

    options = await rframe.evaluate(
        "() => Array.from(document.querySelectorAll('select option')).map(o => ({v: o.value, t: o.text.trim()}))"
    )
    list_name = _auto_active_price_list_name()
    match = next((o for o in options if list_name.upper() in o["t"].upper()), None)
    if not match:
        keyword = list_name.split()[1] if len(list_name.split()) > 1 else list_name
        match = next((o for o in options if keyword.upper() in o["t"].upper()), None)
    if not match:
        found = ", ".join(o["t"] for o in options[:12])
        raise AutoDownloadError(f"No se encontró '{list_name}' en Lista de Precios. Opciones visibles: {found}")

    await select_loc.select_option(value=match["v"])
    await _auto_pause(0.2)

    _auto_log("Haciendo click en Exportar Lista de Precios")
    download = await _auto_wait_price_export_download(erp_page, rframe)
    file_name = download.suggested_filename or "lista_precios.xlsx"
    target = Path(download_dir) / file_name
    await download.save_as(str(target))
    if not target.exists():
        raise AutoDownloadError(f"No se encontró la lista de precios descargada: {target}")
    return target

async def auto_download_articulos_packs_y_precios(usuario: str, password: str, progress_cb=None) -> dict:
    def progress(text: str):
        _auto_log(text)
        if progress_cb:
            progress_cb(text)

    progress("Preparando descarga temporal...")
    _clean_auto_download_dir(AUTO_DOWNLOAD_STAGING_DIR)

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise AutoDownloadError(
            "Falta instalar Playwright para usar la carga automática.\n"
            "Instala la dependencia o usa el .exe portable actualizado."
        ) from exc

    browser = None
    try:
        async with async_playwright() as p:
            progress("Abriendo navegador automático...")
            browser, context, page = await _auto_new_page(p, AUTO_DOWNLOAD_STAGING_DIR)

            progress("Iniciando sesión en Tivendo...")
            await _auto_login_tivendo(page, usuario, password)

            progress("Verificando empresa Mercado House...")
            await _auto_ensure_mercado_house(page, usuario, password)

            progress("Abriendo Punto de Ventas...")
            pos_page = await _auto_open_pos(context, page)

            progress("Descargando listado de artículos...")
            articulos_path = await _auto_download_from_pos(
                pos_page,
                "Listado de artículos",
                "listado_articulos.xlsx",
                AUTO_DOWNLOAD_STAGING_DIR,
            )

            progress("Descargando maestro de packs...")
            packs_path = await _auto_download_from_pos(
                pos_page,
                "Packs",
                "packs.xlsx",
                AUTO_DOWNLOAD_STAGING_DIR,
            )

            progress("Descargando lista de precios...")
            prices_path = await _auto_download_price_ranges(context, page, AUTO_DOWNLOAD_STAGING_DIR)

            progress("Guardando última descarga correcta...")
            return _promote_auto_downloads({
                "articulos": articulos_path,
                "packs": packs_path,
                "precios": prices_path,
            })
    except AutoDownloadError:
        raise
    except Exception as exc:
        raise AutoDownloadError(str(exc)) from exc
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass


async def auto_download_solo_articulos(usuario: str, password: str, progress_cb=None):
    """Valida la descarga antes de reemplazar solo el listado compartido."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise AutoDownloadError("Usa el ejecutable actualizado para descargar el listado automáticamente.") from exc

    def progress(text):
        _auto_log(text)
        if progress_cb:
            progress_cb(text)

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="listado-", dir=APP_DATA_DIR) as staging:
        async with async_playwright() as playwright:
            progress("Iniciando sesión en Tivendo…")
            browser, context, page = await _auto_new_page(playwright, Path(staging))
            try:
                await _auto_login_tivendo(page, usuario, password)
                await _auto_ensure_mercado_house(page, usuario, password)
                progress("Descargando solo el listado de artículos…")
                pos = await _auto_open_pos(context, page)
                source = await _auto_download_from_pos(pos, "Listado de artículos", "listado_articulos.xlsx", Path(staging))
                progress("Comprobando el listado y el último código válido…")
                catalogo = leer_catalogo_articulos(source)
                AUTO_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                # Ruta nueva: el listado anterior sigue disponible si después
                # no se puede guardar la metadata o aplicar el cambio en la UI.
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                target = AUTO_DOWNLOAD_DIR / (f"listado_articulos_{stamp}" + source.suffix.lower())
                pending = target.with_suffix(target.suffix + ".part")
                shutil.copy2(source, pending)
                pending.replace(target)
                return target, catalogo
            finally:
                try:
                    await browser.close()
                except Exception as exc:
                    _auto_log(f"No se pudo cerrar el navegador de descarga: {exc}")


# =====================================================
#  Proveedores (empresas) — persistencia
# =====================================================
def load_empresas() -> Dict[int, str]:
    """
    Carga proveedores desde empresas.json.
    Si no existe/está vacío, inicializa con SEED_EMPRESAS y lo guarda.
    """
    data: Dict[int, str] = {}
    if EMP_PATH.exists():
        try:
            with open(EMP_PATH, "r", encoding="utf-8") as _f:
                raw = json.load(_f)
            data = {int(k): str(v) for k, v in raw.items() if str(k).lstrip("-").isdigit()}
        except Exception:
            data = {}
    if data:
        return data
    # Semilla del programa
    try:
        with open(EMP_PATH, "w", encoding="utf-8") as _f:
            json.dump(SEED_EMPRESAS, _f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return dict(SEED_EMPRESAS)

def save_empresas(d: Dict[int, str]):
    clean = {int(k): str(v).strip() for k, v in d.items() if str(k).lstrip("-").isdigit()}
    try:
        with open(EMP_PATH, "w", encoding="utf-8") as _f:
            json.dump(clean, _f, ensure_ascii=False, indent=2)
    except OSError:
        pass

def ensure_empresas_seed_applied() -> None:
    """Garantiza que empresas.json tenga, al menos, todas las empresas de SEED_EMPRESAS.

    - Si el archivo no existe o está vacío, se inicializa con la semilla.
    - Si existe, se fusiona manteniendo las empresas que el usuario haya agregado,
      pero asegurando que todas las de SEED_EMPRESAS estén presentes y actualizadas.
    El valor de retorno es None; el efecto es escribir el JSON a disco.
    """
    try:
        actuales = load_empresas()
    except Exception:
        actuales = {}
    fusionadas: Dict[int, str] = {**SEED_EMPRESAS, **actuales}
    save_empresas(fusionadas)

def empresas_df_for_excel(d: Dict[int, str]) -> pd.DataFrame:
    rows = [f"{name} (Id. {iid})" for iid, name in sorted(d.items(), key=lambda x: (str(x[1]).lower(), x[0]))]
    return pd.DataFrame({"LISTA": rows})

# =====================================================
#  Carga de datos (para Buscador)
# =====================================================
def try_read_parts(pattern: str, base_dir: Path):
    files = sorted(str(p) for p in base_dir.glob(pattern))
    if not files:
        return None
    frames = [pd.read_csv(f, dtype=str).fillna("") for f in files]
    return pd.concat(frames, ignore_index=True)

def _norm_lc(s) -> str:
    """Normaliza texto: sin tildes, minúsculas, strip."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()

def _strip_accents(text: str) -> str:
    """Elimina diacríticos/tildes de un string."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )

def _normalize_text(text: str) -> str:
    """Normaliza texto para búsquedas suaves: sin tildes, lower, sin puntuación."""
    s = _strip_accents(text).lower()
    s = s.replace("-", " ").replace("_", " ").replace(".", "").replace(",", "")
    return _ws_re.sub(" ", s).strip()

_EXCEL_COL_RENAME = {
    "Identificador": "identificador",
    "Código": "codigo",
    "Código": "codigo", "Nombre": "nombre", "Unidad": "unidad",
    "Código barra interno": "barcode_interno",
    "Código barra interno": "barcode_interno",
    "Código barra externo": "barcode_externo",
    "Código barra externo": "barcode_externo",
    "Descripción": "descripcion", "Id Categoría2": "empresa_id_raw",
    "Descripción": "descripcion", "Id Categoría2": "empresa_id_raw",
}
_EXCEL_KEEP = ["identificador", "codigo", "nombre", "barcode_interno", "barcode_externo", "empresa_id_raw"]

def _parse_excel_base(path) -> pd.DataFrame:
    """Lee la hoja BASE DE DATOS de un Excel y devuelve DataFrame normalizado."""
    with pd.ExcelFile(path, engine="openpyxl") as xf:
        base = xf.parse("BASE DE DATOS")
    base = base.rename(columns=_EXCEL_COL_RENAME)
    fallback_cols = [
        ("identificador", 0),
        ("codigo", 1),
        ("nombre", 2),
        ("barcode_interno", 4),
        ("barcode_externo", 5),
        ("empresa_id_raw", 7),
    ]
    for target, idx in fallback_cols:
        if target not in base.columns and idx < len(base.columns):
            base[target] = base.iloc[:, idx]
    keep = [c for c in _EXCEL_KEEP if c in base.columns]
    return base[keep].fillna("").astype(str)


def _extract_id(val) -> str:
    """Extrae primer grupo de dígitos de val; usado para normalizar empresa_id."""
    m = _RE_DIGITS.search(str(val))
    return m.group(1) if m else ""

def _extract_trailing_codes(texto) -> List[str]:
    """Extrae el/los codigo(s) al final de un Nombre o Codigo, ej.
    'CHOCOLATE NESTLE SAHNE-NUSS 90 GR - 7582 0' -> ['75820'].

    El separador real es el ULTIMO guion que tiene espacio a AMBOS lados
    (" - "), nunca un guion pegado a letras/numeros: eso evita confundir el
    separador con un guion que es parte de una marca ("SAHNE-NUSS") o parte
    de la estructura del propio codigo ("EAN13-0799192433702", "CJ-AO-VDR-
    SE-250-C"). Todo lo que sigue a ese separador se divide SOLO por "/"
    (multiples codigos por factura, ej. "8116 0/ 791 0"); los guiones DENTRO
    de cada trozo se conservan intactos porque son parte del codigo mismo,
    no un divisor (dividirlos rompería codigos compuestos como CJ-AO-VDR-
    SE-250-C). Los espacios internos de cada trozo se eliminan para que
    "7582 0" y "75820" sean la misma clave de busqueda."""
    m = _RE_LAST_SPACED_DASH.match(str(texto).strip())
    if not m:
        return []
    codes = []
    for piece in m.group(1).split("/"):
        compact = piece.replace(" ", "").strip().lower()
        if _RE_CODE_TOKEN.fullmatch(compact):
            codes.append(compact)
    return codes

def _drop_ambiguous_trailing_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Un codigo extraido del final de Nombre/Codigo solo sirve como clave de
    busqueda si identifica a UN SOLO producto en todo el catalogo. Algunos
    textos que quedan ahi no son codigos individuales: marcadores como
    "SINITEM" (sin codigo asignado) o prefijos de familia/categoria como
    "LC1" o "02025" (compartidos por decenas de variantes, ej. "02025/517",
    "02025/510", ...) se repiten en muchos productos distintos. Si dejaramos
    esos como claves buscables, buscar ese texto traeria decenas de
    productos no relacionados en vez de uno. Se descartan comparando contra
    TODO el catalogo (no solo unos ejemplos), asi este filtro se adapta solo
    a cualquier caso similar futuro sin necesitar listas de palabras."""
    owner: Dict[str, str] = {}
    ambiguous = set()
    for ident, codes in zip(df["identificador"], df["_nombre_suffix_codes"]):
        for c in codes:
            prev = owner.setdefault(c, ident)
            if prev != ident:
                ambiguous.add(c)
    for ident, codes in zip(df["identificador"], df["_codigo_suffix_codes"]):
        for c in codes:
            prev = owner.setdefault(c, ident)
            if prev != ident:
                ambiguous.add(c)
    if not ambiguous:
        return df
    df["_nombre_suffix_codes"] = df["_nombre_suffix_codes"].apply(lambda lst: [c for c in lst if c not in ambiguous])
    df["_codigo_suffix_codes"] = df["_codigo_suffix_codes"].apply(lambda lst: [c for c in lst if c not in ambiguous])
    return df

def _make_nf_row(code: str, pos: int) -> pd.DataFrame:
    """Crea una fila 'No encontrado' para el buscador."""
    return pd.DataFrame([{
        "identificador": "", "codigo": code, "nombre": "No encontrado",
        "barcode_interno": "", "barcode_externo": "",
        "empresa_id": "", "__input": code, "__pos": pos, "__rank": 0
    }])

def _ensure_search_helper_columns(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["identificador", "codigo", "nombre", "barcode_interno", "barcode_externo", "empresa_id"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].fillna("").astype(str)

    if "_codigo_lc" not in df.columns:
        df["_codigo_lc"] = df["codigo"].str.lower().str.strip()
    if "_identificador_lc" not in df.columns:
        df["_identificador_lc"] = df["identificador"].str.lower().str.strip()
    if "_identificador_ws" not in df.columns:
        df["_identificador_ws"] = df["identificador"].astype(str).str.strip().apply(lambda s: _ws_re.sub(" ", s))
    if "_codigo_ws" not in df.columns:
        df["_codigo_ws"] = df["codigo"].astype(str).str.strip().apply(lambda s: _ws_re.sub(" ", s))
    if "_nombre_suffix_codes" not in df.columns or "_codigo_suffix_codes" not in df.columns:
        df["_nombre_suffix_codes"] = df["nombre"].map(_extract_trailing_codes)
        df["_codigo_suffix_codes"] = df["codigo"].map(_extract_trailing_codes)
        df = _drop_ambiguous_trailing_codes(df)
    if "_nombre_lc" not in df.columns:
        df["_nombre_lc"] = df["nombre"].map(_norm_lc)
    if "_codigo_tokens" not in df.columns:
        df["_codigo_tokens"] = df["codigo"].apply(split_codes_by_slash)
    if "_codigo_tokens_norm" not in df.columns:
        df["_codigo_tokens_norm"] = df["_codigo_tokens"].apply(to_normalized_tokens)
    return df

def _clean_emp(empresas: Dict[int, str]) -> Dict[int, str]:
    """Filtra y convierte el dict de empresas a {int: str} limpio."""
    return {int(k): str(v) for k, v in empresas.items() if str(k).lstrip("-").isdigit()}

def load_data(selected_path: Optional[Path]):
    """
    Carga la base desde un archivo seleccionado (Excel/CSV). Si selected_path es None,
    intenta autodetectar en la carpeta. Devuelve: df, empresas(dict)
    """
    df = None
    empresas: Dict[int, str] = load_empresas()

    # -------------------------------------------------
    # Cache persistente en disco:
    # si existe una BASE ya preparada y asociada a la misma fuente,
    # la cargamos desde CACHE_DB_PATH y evitamos reprocesar.
    # -------------------------------------------------
    try:
        # Clave de origen: ruta seleccionada o "__AUTO__" si se usa autodetección
        src_key = str(selected_path) if selected_path is not None else "__AUTO__"
        src_mtime = None
        if selected_path is not None and selected_path.exists():
            try:
                src_mtime = selected_path.stat().st_mtime
            except Exception:
                src_mtime = None

        if CACHE_DB_PATH.exists() and CACHE_DB_META.exists():
            with open(CACHE_DB_META, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            if meta.get("src_key") == src_key and meta.get("src_mtime") == src_mtime:
                # Coincide el origen: usamos la base cacheada en disco
                df = pd.read_pickle(CACHE_DB_PATH)
                df = _ensure_search_helper_columns(df)

                # Construir índice invertido (rápido, siempre desde el df)
                tok_idx = _build_search_index(df)

                # Actualizar cache en memoria para esta sesión
                _LOAD_DATA_CACHE["path"] = selected_path
                _LOAD_DATA_CACHE["df"] = df
                _LOAD_DATA_CACHE["index"] = tok_idx

                # Normalizar empresas (igual que al final de load_data)
                return df, _clean_emp(empresas)
    except Exception:
        # Si algo falla, seguimos flujo normal sin cache persistente
        pass

    # -------------------------------------------------
    # Cache: si ya cargamos esta BASE en esta sesión,
    # devolvemos la copia en memoria y evitamos releer disco.
    # -------------------------------------------------
    cache_df = _LOAD_DATA_CACHE.get("df")
    cache_path = _LOAD_DATA_CACHE.get("path")

    if cache_df is not None and cache_path == selected_path:
        cache_df = _ensure_search_helper_columns(cache_df)
        return cache_df, _clean_emp(empresas)  # consistente con retorno de cache disco

    used_path: Optional[Path] = selected_path
    # Si el usuario eligió archivo, intentamos con prioridad ese (SOLO leemos "BASE DE DATOS")
    if selected_path is not None and selected_path.exists():
        ext = selected_path.suffix.lower()
        if ext in [".xlsm", ".xlsx", ".xls"]:
            try:
                df = _parse_excel_base(selected_path)
            except (ValueError, KeyError):
                raise FileNotFoundError("No se encontró la hoja 'BASE DE DATOS' en el Excel seleccionado.")
        elif ext == ".csv":
            df = pd.read_csv(selected_path, dtype=str).fillna("")
        elif ext == ".gz":
            df = pd.read_csv(selected_path, dtype=str, compression="gzip").fillna("")
        elif ext == ".zip":
            df = pd.read_csv(selected_path, dtype=str, compression="zip").fillna("")
        else:
            try:
                df = _parse_excel_base(selected_path)
            except Exception:
                pass

    # Autodetección en carpeta (comportamiento histórico)
    if df is None:
        csv = HERE / "base_codigos.csv"
        if csv.exists():
            df = pd.read_csv(csv, dtype=str).fillna("")
        if df is None:
            parts = try_read_parts("base_codigos_part*.csv", HERE)
            if parts is not None:
                df = parts
        if df is None:
            gz = HERE / "base_codigos.csv.gz"
            if gz.exists():
                df = pd.read_csv(gz, dtype=str, compression="gzip").fillna("")
        if df is None:
            z = HERE / "base_codigos.csv.zip"
            if z.exists():
                df = pd.read_csv(z, dtype=str, compression="zip").fillna("")
        if df is None:
            xlsm = HERE / "BDD_codigosv4.xlsm"
            if xlsm.exists():
                try:
                    df = _parse_excel_base(xlsm)
                except Exception:
                    pass
        if df is None:
            raise FileNotFoundError("No se pudo cargar la base. Selecciona un archivo válido o coloca base_codigos.csv en la carpeta.")

    # Normalizaciones
    if "empresa_id" not in df.columns:
        if "empresa_id_raw" in df.columns:
            df["empresa_id"] = df["empresa_id_raw"].apply(_extract_id)
        else:
            df["empresa_id"] = ""  # columna no presente; se inicializa vacía

    try:
        df = _ensure_search_helper_columns(df)
    except Exception:
        df["_codigo_tokens"] = [[] for _ in range(len(df))]
        df["_codigo_tokens_norm"] = [[] for _ in range(len(df))]

    clean_emp = _clean_emp(empresas)

    # Construir índice invertido de tokens
    tok_idx = _build_search_index(df)

    # Actualizar cache con la BASE que se usó en esta sesión
    try:
        _LOAD_DATA_CACHE["path"] = used_path
        _LOAD_DATA_CACHE["df"] = df
        _LOAD_DATA_CACHE["index"] = tok_idx
    except Exception:
        pass

    # Guardar cache persistente en disco para próximas ejecuciones
    try:
        src_key = str(used_path) if used_path is not None else "__AUTO__"
        src_mtime = None
        if used_path is not None and used_path.exists():
            try:
                src_mtime = used_path.stat().st_mtime
            except Exception:
                src_mtime = None
        meta = {"src_key": src_key, "src_mtime": src_mtime}
        with open(CACHE_DB_META, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        df.to_pickle(CACHE_DB_PATH)
    except Exception:
        # Si algo falla al escribir cache persistente, lo ignoramos.
        pass

    return df, clean_emp

def sanitize_cell(x) -> str:
    return str(x).replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()

def parse_codes(text: str):
    """Convierte el texto ingresado en una lista de códigos.

    NUEVA LÓGICA (más simple y acorde a tu uso):
    - Cada LÍNEA distinta en el cuadro de texto se considera un código.
    - Dentro de la línea, se respeta exactamente lo que escribas (guiones, espacios, etc.).
    - Las líneas vacías se ignoran.
    - Se eliminan duplicados manteniendo el orden.
    """
    seen, out = set(), []
    for ln in str(text or "").splitlines():
        code = ln.strip()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _looks_like_barcode(text: str) -> bool:
    digits = _RE_NO_DIGITS.sub("", str(text or ""))
    return len(digits) >= 6

def normalize_code_token(t: str) -> str:
    """Normaliza token para comparación: lower, strip y colapsa espacios internos."""
    t = str(t).strip().lower()
    return _ws_re.sub(" ", t)

def split_codes_by_slash(segment: str):
    """Divide un segmento de códigos por "/", limpiando espacios y omitiendo vacíos."""
    if not isinstance(segment, str) or not segment.strip():
        return []
    parts = [p.strip() for p in segment.split("/")]
    return [p for p in parts if p]

def to_normalized_tokens(tokens):
    return [t for tok in (tokens or []) if (t := normalize_code_token(tok))]

# =====================================================
#  Convertidor
# =====================================================
DROP_COLUMNS = [
    "Precio","Es Servicio","Es Exento","Impuesto Específico","Impuesto Especifico","Impuesto Espec\u00edfico",
    "Disponible para venta","Activo","Utilidad","TipoUtilidad"
]
TARGET_ORDER = ["Identificador","Código","Nombre","Unidad","Código barra interno","Código barra externo","Descripción","Id Categoría2"]

def _detect_header_row(df_loader, default: int, max_check: int = 30) -> int:
    """Helper interno: carga un DataFrame sin cabecera y busca la fila que
    contiene 'Código' y 'Nombre'. Devuelve su índice o `default` si no se halla.
    `df_loader` es un callable sin argumentos que devuelve el DataFrame.
    """
    try:
        df_noh = df_loader()
    except Exception:
        return default
    for i, row_data in enumerate(df_noh.head(max_check).itertuples(index=False, name=None)):
        row = [str(x).strip() for x in row_data]
        if "Código" in row and "Nombre" in row:
            return i
    return default


def detect_header_row_excel(path, sheet_name=0, max_check=30):
    return _detect_header_row(
        lambda: pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=max_check, dtype=str),
        default=4,
        max_check=max_check,
    )


def detect_header_row_csv(path, max_check=30, sep=',', encoding='utf-8'):
    return _detect_header_row(
        lambda: pd.read_csv(path, header=None, nrows=max_check, dtype=str, sep=sep, encoding=encoding),
        default=0,
        max_check=max_check,
    )

def read_export_any(path: Path, progress_cb=None):
    ext = path.suffix.lower()
    if progress_cb: progress_cb(5, "Detectando encabezados…")
    if ext in (".xlsx", ".xls", ".xlsm"):
        header_idx = detect_header_row_excel(path)
        if progress_cb: progress_cb(10, "Leyendo Excel…")
        df = pd.read_excel(path, sheet_name=0, header=header_idx, dtype=str)
    elif ext == ".csv":
        header_idx = detect_header_row_csv(path)
        if progress_cb: progress_cb(10, "Leyendo CSV…")
        df = pd.read_csv(path, header=header_idx, dtype=str)
    else:
        raise ValueError(f"Extensión no soportada: {ext}")
    if progress_cb: progress_cb(20, "Archivo leído")
    return df

def extract_code_from_name(name: str) -> str:
    """Toma lo que viene DESPUÉS del PRIMER guion '-' (izquierda→derecha)."""
    s = "" if pd.isna(name) else str(name)
    # Normaliza variantes de guion a '-'
    s = s.replace('–','-').replace('—','-').replace('−','-')
    if '-' in s:
        _, _, right = s.partition('-')  # primer guion
        return right.strip()
    return s.strip()

def fmt_id(x):
    x = "" if pd.isna(x) else str(x).strip()
    return f"(Id. {x})" if x else ""


def _pick_export_col(df: pd.DataFrame, names, fallback_idx=None):
    norm_map = {_normalize_text(c): c for c in df.columns}
    for name in names:
        col = norm_map.get(_normalize_text(name))
        if col is not None:
            return col
    if fallback_idx is not None and -len(df.columns) <= fallback_idx < len(df.columns):
        return df.columns[fallback_idx]
    return None


def transform_export(df: pd.DataFrame, progress_cb=None) -> pd.DataFrame:
    if progress_cb: progress_cb(35, "Limpiando columnas…")
    drop_now = [c for c in DROP_COLUMNS if c in df.columns]
    if drop_now:
        df = df.drop(columns=drop_now, errors='ignore')

    col_ident = _pick_export_col(df, ["Identificador", "Codigo", "Código"], 0)
    col_nombre = _pick_export_col(df, ["Nombre"], 1)
    col_unidad = _pick_export_col(df, ["Unidad"], 2)
    col_bar_int = _pick_export_col(df, ["Codigo barra interno", "Código barra interno"], 4)
    col_bar_ext = _pick_export_col(df, ["Codigo barra externo", "Código barra externo"], 5)
    col_desc = _pick_export_col(df, ["Descripcion", "Descripción"], 6)
    col_cat = _pick_export_col(df, ["Id Categoria", "Id Categoría"], -1)

    required = {
        "Identificador": col_ident,
        "Nombre": col_nombre,
        "Unidad": col_unidad,
        "Codigo barra interno": col_bar_int,
        "Codigo barra externo": col_bar_ext,
        "Descripcion": col_desc,
        "Id Categoria": col_cat,
    }
    missing = [label for label, col in required.items() if col is None]
    if missing:
        raise ValueError(f"No se encontraron columnas requeridas en el export: {missing}")

    if progress_cb: progress_cb(45, "Reordenando y renombrando…")
    out = pd.DataFrame({
        "Identificador": df[col_ident],
        "Código": df[col_ident],
        "Nombre": df[col_nombre],
        "Unidad": df[col_unidad],
        "Código barra interno": df[col_bar_int],
        "Código barra externo": df[col_bar_ext],
        "Descripción": df[col_desc],
        "Id Categoría2": df[col_cat],
    })

    if progress_cb: progress_cb(55, "Extrayendo CÓDIGO desde NOMBRE…")
    out["Código"] = out["Nombre"].map(extract_code_from_name)

    if progress_cb: progress_cb(65, "Formateando Id Categoría2…")
    out["Id Categoría2"] = out["Id Categoría2"].map(fmt_id)

    if progress_cb: progress_cb(75, "Ajustando estructura final…")
    out = out[TARGET_ORDER]
    out = out.iloc[4:].reset_index(drop=True)

    for c in out.columns:
        out[c] = out[c].astype(str).replace({"nan": ""})
    if progress_cb: progress_cb(80, "Transformación completada")
    return out

def _build_search_index(df: pd.DataFrame) -> Dict[str, List[int]]:
    """Construye índice invertido: token_normalizado → lista de posiciones enteras en df.

    Las posiciones son labels del índice original del DataFrame (no posiciones relativas),
    lo que permite usar df.index.isin() correctamente incluso con DataFrames filtrados.
    """
    idx: Dict[str, List[int]] = {}
    for label, toks in zip(df.index, df["_codigo_tokens_norm"]):
        for tok in toks:
            if tok:
                idx.setdefault(tok, []).append(label)
    return idx


def _score_results(df: pd.DataFrame, q_raw: str, q_ws: str, q_norm: str,
                   exact: bool, by_barras: bool, by_tivendo: bool = False,
                   tok_index: Optional[Dict] = None) -> pd.DataFrame:
    """Calcula scores de relevancia por fila y devuelve df filtrado y ordenado.

    Scores (de mayor a menor relevancia):
        100 — código exacto completo
         80 — código empieza con el término  (solo modo no-exacto)
         60 — token exacto dentro de código multi-parte
         40 — código contiene el término (no-exacto)
         35 — token contiene el término, mín. 3 chars (no-exacto)
         20 — nombre contiene el término (no-exacto)
         70 — barcode exacto  (modo exacto)
         10 — barcode contiene (modo no-exacto)
         95 — identificador Tivendo exacto
         55 — identificador Tivendo empieza con/contiene (modo no-exacto)

    Returns:
        DataFrame con columna __score, ordenado score desc. Vacío si sin resultados.
    """
    q_ws_lc = q_ws.lower()
    q_name  = _norm_lc(q_ws)
    n       = len(df)
    scores  = np.zeros(n, dtype=np.int32)

    if exact:
        if by_tivendo:
            im = (df["_identificador_ws"].str.lower() == q_ws_lc).values
            scores[im] = 95

        m = (df["_codigo_ws"].str.lower() == q_ws_lc).values
        scores[m] = 100

        if tok_index is not None and q_norm in tok_index:
            tok_mask = df.index.isin(tok_index[q_norm])
            scores[tok_mask & (scores < 60)] = 60
        else:
            for i, toks in enumerate(df["_codigo_tokens_norm"]):
                if scores[i] < 60 and any(tok == q_norm for tok in toks):
                    scores[i] = 60

        if by_barras:
            bm = ((df["barcode_interno"].str.strip() == q_ws) |
                  (df["barcode_externo"].str.strip() == q_ws)).values
            scores[bm & (scores == 0)] = 70
    else:
        # Los codigos multi-parte a veces repiten el mismo numero con y sin
        # cero(s) inicial(es) (ej. "058910/58910/66375": la misma pieza
        # aparece como "058910" y como "58910"). En modo no-exacto, si el
        # termino buscado es puramente numerico tambien se prueba la version
        # sin ceros a la izquierda, para que "066375" encuentre "66375"
        # igual que si se hubiera escrito sin el cero de mas.
        q_alt = None
        if q_ws_lc.isdigit():
            stripped = q_ws_lc.lstrip("0")
            # Se exige un minimo de 3 digitos restantes (mismo umbral que ya
            # usa el resto de esta funcion para matches por substring) para
            # no volver "000"/"0" en una busqueda que matchee casi cualquier
            # codigo por tener un cero en algun lado.
            if stripped and stripped != q_ws_lc and len(stripped) >= 3:
                q_alt = stripped
        needles_eq = {q_norm} if not q_alt else {q_norm, q_alt}
        needles_contains = {n for n in needles_eq if len(n) >= 3}

        if by_tivendo:
            im_exact = (df["_identificador_ws"].str.lower() == q_ws_lc).values
            scores[im_exact] = 95

            im_starts = df["_identificador_lc"].str.startswith(q_ws_lc, na=False).values
            scores[im_starts & (scores < 55)] = 55

            im_contains = df["_identificador_lc"].str.contains(re.escape(q_ws_lc), na=False).values
            scores[im_contains & (scores < 45)] = 45

        m_exact = (df["_codigo_ws"].str.lower() == q_ws_lc).values
        scores[m_exact] = 100

        m_starts = df["_codigo_lc"].str.startswith(q_ws_lc, na=False).values
        if q_alt:
            m_starts = m_starts | df["_codigo_lc"].str.startswith(q_alt, na=False).values
        scores[m_starts & (scores < 80)] = 80

        if tok_index is not None:
            tok_positions = set()
            for needle in needles_eq:
                tok_positions.update(tok_index.get(needle, ()))
            if tok_positions:
                tok_mask = df.index.isin(tok_positions)
                scores[tok_mask & (scores < 60)] = 60
        else:
            for i, toks in enumerate(df["_codigo_tokens_norm"]):
                if scores[i] < 60 and any(tok in needles_eq for tok in toks):
                    scores[i] = 60

        m_code = df["_codigo_lc"].str.contains(re.escape(q_ws_lc), na=False).values
        if q_alt:
            m_code = m_code | df["_codigo_lc"].str.contains(re.escape(q_alt), na=False).values
        scores[m_code & (scores < 40)] = 40

        if needles_contains:
            for i, toks in enumerate(df["_codigo_tokens_norm"]):
                if scores[i] < 35 and any(any(n in tok for n in needles_contains) for tok in toks):
                    scores[i] = 35

        m_name = df["_nombre_lc"].str.contains(re.escape(q_name), na=False).values
        if q_alt:
            m_name = m_name | df["_nombre_lc"].str.contains(re.escape(q_alt), na=False).values
        scores[m_name & (scores < 20)] = 20

        if by_barras:
            m_bar = (
                df["barcode_interno"].str.contains(re.escape(q_raw), na=False) |
                df["barcode_externo"].str.contains(re.escape(q_raw), na=False)
            ).values
            scores[m_bar & (scores == 0)] = 10

    if not scores.any():
        return pd.DataFrame()

    result = df[scores > 0].copy()
    result["__score"] = scores[scores > 0]
    return result.sort_values("__score", ascending=False)


def _find_fuzzy_suggestions(q_norm: str, df: pd.DataFrame, n: int = 3) -> List[str]:
    """Busca códigos similares a q_norm usando difflib (stdlib).

    Filtra candidatos por primera letra para mantener rendimiento en bases grandes.
    Retorna lista de hasta n códigos similares, vacía si q_norm < 3 chars.
    """
    if len(q_norm) < 3:
        return []
    candidates = df["_codigo_lc"].dropna().unique()
    first = q_norm[0]
    filtered = [c for c in candidates if c and c[0] == first]
    if not filtered:
        filtered = list(candidates)
    if len(filtered) > 5000:
        filtered = filtered[:5000]
    return difflib.get_close_matches(q_norm, filtered, n=n, cutoff=0.70)


def _filter_combobox_choices(term: str, choices: list, combo, result_var) -> None:
    """Filtra en vivo las opciones de un ttk.Combobox según el término buscado.

    Si el término no coincide con nada, restaura la lista completa.
    Mantiene la selección actual si sigue estando en la lista filtrada.

    Args:
        term       : texto de búsqueda ya en minúsculas y sin espacios extra
        choices    : lista completa de opciones del combobox
        combo      : widget ttk.Combobox a actualizar
        result_var : StringVar vinculado al combobox
    """
    if not term:
        values = choices
    else:
        values = [c for c in choices if term in c.lower()]
        if not values:
            values = choices
    current = combo.get()
    combo.configure(values=values)
    if current in values:
        result_var.set(current)
    elif values:
        result_var.set(values[0])
    else:
        result_var.set("")


# =====================================================
#  Vistas (Frames) y Navegación
# =====================================================

def _norm_pack_code(value: str) -> str:
    """Normaliza codigos de articulo/pack para cruces con Maestro de Packs."""
    s = "" if value is None else str(value).strip().upper()
    return _RE_NON_ALNUM.sub("", s)


def _load_cached_side_data(path: Path, cache_path: Path, cache_meta: Path, loader_fn):
    """Envuelve `loader_fn(path)` (load_packs_data / load_price_ranges_data)
    con un cache persistente en disco keyado por ruta+mtime, igual que
    load_data() ya hace para la BASE DE DATOS principal. Si el archivo no
    cambio desde la ultima vez (misma ruta, mismo mtime), se reusa el
    resultado ya parseado en vez de volver a leer/parsear el Excel/HTML,
    que es lo lento. Reabrir la app sin haber descargado un archivo nuevo
    deberia sentirse instantaneo gracias a esto."""
    schema_version = 3 if loader_fn is load_price_ranges_data else 1
    try:
        src_mtime = path.stat().st_mtime
    except Exception:
        src_mtime = None

    try:
        if cache_path.exists() and cache_meta.exists():
            with open(cache_meta, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            if (meta.get("src_path") == str(path) and meta.get("src_mtime") == src_mtime
                    and meta.get("schema_version", 1) == schema_version):
                return pd.read_pickle(cache_path)
    except Exception:
        pass

    result = loader_fn(path)

    try:
        pd.to_pickle(result, cache_path)
        with open(cache_meta, "w", encoding="utf-8") as fh:
            json.dump({"src_path": str(path), "src_mtime": src_mtime, "schema_version": schema_version}, fh)
    except Exception:
        pass

    return result


def _find_pack_column(columns, wanted_names, fallback_idx=None):
    norm_map = {_normalize_text(c): c for c in columns}
    for name in wanted_names:
        col = norm_map.get(_normalize_text(name))
        if col is not None:
            return col
    if fallback_idx is not None and fallback_idx < len(columns):
        return columns[fallback_idx]
    return None


def load_packs_data(path: Path):
    """Lee Maestro de Packs y devuelve (df_detalle, indice_por_codigo_articulo)."""
    df = pd.read_excel(path, sheet_name=0, dtype=str).fillna("")
    if df.empty:
        raise ValueError("El maestro de packs esta vacio.")

    cols = list(df.columns)
    pack_code_col = _find_pack_column(cols, ["Codigo"], 0)
    pack_name_col = _find_pack_column(cols, ["Nombre"], 1)
    pack_bar_col = _find_pack_column(cols, ["Codigo barra interno"], 3)
    comp_code_col = _find_pack_column(cols, ["Codigo producto en pack"], 6)
    qty_col = _find_pack_column(cols, ["Cantidad producto en pack"], 7)

    missing = [
        label for label, col in (
            ("Codigo pack", pack_code_col),
            ("Nombre pack", pack_name_col),
            ("Codigo barra pack", pack_bar_col),
            ("Codigo producto en pack", comp_code_col),
            ("Cantidad producto en pack", qty_col),
        ) if col is None
    ]
    if missing:
        raise ValueError(f"No se encontraron columnas requeridas: {missing}")

    work = df[[pack_code_col, pack_name_col, pack_bar_col, comp_code_col, qty_col]].copy()
    work.columns = ["pack_codigo", "pack_nombre", "pack_barra", "articulo_codigo", "cantidad"]
    for c in work.columns:
        work[c] = work[c].fillna("").astype(str).str.strip()

    for c in ("pack_codigo", "pack_nombre", "pack_barra"):
        work[c] = work[c].replace("", pd.NA).ffill().fillna("")

    work = work[work["articulo_codigo"].astype(str).str.strip() != ""].copy()
    if work.empty:
        raise ValueError("No se encontraron codigos de productos en pack.")

    work["_articulo_norm"] = work["articulo_codigo"].map(_norm_pack_code)
    work = work[work["_articulo_norm"] != ""].copy()
    work = work.reset_index(drop=True)

    packs_index = {}
    for _, row in work.iterrows():
        record = {
            "pack_codigo": row["pack_codigo"],
            "pack_nombre": row["pack_nombre"],
            "pack_barra": row["pack_barra"],
            "articulo_codigo": row["articulo_codigo"],
            "cantidad": row["cantidad"],
        }
        packs_index.setdefault(row["_articulo_norm"], []).append(record)

    return work, packs_index


class _HTMLTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._in_cell = False
        self._current_row = None
        self._current_cell = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th") and self._current_row is not None:
            self._in_cell = True
            self._current_cell = []

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("td", "th") and self._current_row is not None:
            text = " ".join("".join(self._current_cell).split()).strip()
            self._current_row.append(text)
            self._in_cell = False
            self._current_cell = []
        elif tag == "tr" and self._current_row is not None:
            if any(str(c).strip() for c in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None


def _read_text_any_encoding(path: Path) -> str:
    data = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")


def resumen_rango_venta(record) -> str:
    """Señala el segundo rango informado, sin interpretar precios ni inventar datos."""
    rango = str(record.get("rango2", "") or "").strip()
    if not rango:
        return "Sin información"
    if re.fullmatch(r"\(?\s*0(?:\s*-\s*0)?\s*\)?", rango):
        return "Sin rango adicional"
    return f"Sí · {rango}"


def rangos_guardados_para_revision(path):
    """Lee solo el archivo local existente. No inicia ninguna descarga."""
    if path is None or not Path(path).is_file():
        return {}, "Rangos: sin archivo guardado; compruébalos en Tivendo."
    path = Path(path)
    try:
        _, index = _load_cached_side_data(path, RANGES_CACHE_PATH, RANGES_CACHE_META, load_price_ranges_data)
        return index, f"Rangos del archivo guardado: {path.name} · {_resource_download_label('precios', path)}"
    except Exception:
        return {}, "No se pudo leer el archivo de rangos guardado; compruébalos en Tivendo."


def load_price_ranges_data(path: Path):
    """Lee la lista HTML/.xls e indexa los rangos de cantidades por artículo."""
    parser = _HTMLTableParser()
    parser.feed(_read_text_any_encoding(path))

    header_idx = None
    for i, row in enumerate(parser.rows):
        norm = [_normalize_text(c) for c in row]
        if "codigo articulo" in norm and "rango 1" in norm and "rango 2" in norm:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("No se encontraron columnas de Codigo articulo, Rango 1 y Rango 2.")

    header = [_normalize_text(c) for c in parser.rows[header_idx]]
    code_idx = header.index("codigo articulo")
    r1_idx = header.index("rango 1")
    r2_idx = header.index("rango 2")

    rows = []
    ranges_index = {}
    for row in parser.rows[header_idx + 1:]:
        if len(row) <= max(code_idx, r1_idx, r2_idx):
            continue
        codigo = str(row[code_idx]).replace("'", "").strip()
        rango1 = str(row[r1_idx]).strip()
        rango2 = str(row[r2_idx]).strip()
        norm_code = _norm_pack_code(codigo)
        if not norm_code:
            continue
        record = {"codigo": codigo, "rango1": rango1, "rango2": rango2}
        rows.append(record)
        ranges_index[norm_code] = record

    if not rows:
        raise ValueError("No se encontraron rangos de precios en el archivo.")

    return pd.DataFrame(rows), ranges_index


class StartView(ttk.Frame):
    """Inicio con tareas principales y fuentes de datos claramente separadas."""
    def __init__(
        self,
        master,
        on_choose_db,
        on_manage_prov,
        on_open_tivendo,
        on_open_ingreso_masivo,
        on_load_listado,
        on_load_packs,
        on_load_ranges,
        on_auto_load,
        listado_cargado: bool,
        packs_cargado: bool,
        ranges_cargado: bool,
        auto_last_load_text: str = "",
    ):
        super().__init__(master, style="Home.TFrame")
        self.master.title("Herramientas — MERCADO HOUSE")
        self.pack(fill="both", expand=True)

        # El pie se reserva primero para que permanezca abajo incluso en 960 × 620.
        footer = ttk.Frame(self, style="Home.TFrame")
        footer.pack(side="bottom", fill="x", padx=18, pady=(7, 12))
        ttk.Label(footer, text=f"Versión {APP_VERSION}", style="HomeMuted.TLabel").pack(side="right")
        self.btn_cargar_auto = ttk.Button(footer, text="Cargar automáticamente desde Tivendo",
                                          command=on_auto_load, style="HomeTeal.TButton")
        self.btn_cargar_auto.pack(side="left")
        self.lbl_estado_auto = ttk.Label(footer, text="", style="HomeMuted.TLabel")
        self.lbl_estado_auto.pack(side="left", padx=14)

        header = ttk.Frame(self, style="HomeHero.TFrame", padding=(0, 8))
        header.pack(fill="x", padx=18, pady=(12, 9))
        ttk.Label(header, text="MERCADO HOUSE", style="HomeHeroEyebrow.TLabel").pack(anchor="center")
        ttk.Label(header, text="Herramientas", style="HomeHeroTitle.TLabel").pack(anchor="center", pady=(2, 0))
        ttk.Label(header, text="Artículos, proveedores y archivos para Tivendo.",
                  style="HomeHeroSubtitle.TLabel").pack(anchor="center", pady=(2, 0))

        ttk.Label(self, text="ELIGE UNA TAREA", style="HomeSection.TLabel").pack(
            anchor="w", padx=18, pady=(0, 3))

        tasks = ttk.Frame(self, style="Home.TFrame")
        tasks.pack(fill="x", padx=18)
        tasks.columnconfigure(0, weight=1, uniform="tasks")
        tasks.columnconfigure(1, weight=1, uniform="tasks")

        def task(row, col, tone, title, command):
            card = ttk.Frame(tasks, style=f"Home{tone}.TFrame", padding=7)
            card.grid(row=row, column=col, sticky="nsew", padx=(0, 7) if col == 0 else (7, 0), pady=4)
            button = ttk.Button(card, text=title, command=command,
                                style=f"Home{tone}.TButton")
            button.pack(fill="x")
            return button

        self.btn_buscar = task(0, 0, "Blue", "Buscar códigos", on_choose_db)
        self.btn_prov = task(0, 1, "Purple", "Proveedores", on_manage_prov)
        self.btn_tivendo = task(1, 0, "Coral", "Cambios masivos de precios", on_open_tivendo)
        self.btn_ingreso = task(1, 1, "Teal", "Ingreso masivo de artículos", on_open_ingreso_masivo)

        sources = ttk.Frame(self, style="HomeData.TFrame", padding=(14, 8))
        sources.pack(fill="x", padx=18, pady=(9, 0))
        sources.columnconfigure(0, weight=1)
        ttk.Label(sources, text="Datos cargados", style="HomeDataTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4))

        def source(row, title, command):
            line = ttk.Frame(sources, style="HomeDataInner.TFrame")
            line.grid(row=row + 1, column=0, sticky="ew", pady=2)
            line.columnconfigure(0, weight=1)
            label = ttk.Label(line, text=title, style="HomeDataMuted.TLabel")
            label.grid(row=0, column=0, sticky="w")
            button = ttk.Button(line, text="Elegir archivo", command=command)
            button.grid(row=0, column=1, padx=(8, 0))
            return label, button

        self.lbl_estado, self.btn_cargar_listado = source(0, "Listado de artículos", on_load_listado)
        self.lbl_estado_packs, self.btn_cargar_packs = source(1, "Maestro de packs", on_load_packs)
        self.lbl_estado_rangos, self.btn_cargar_rangos = source(2, "Lista de precios", on_load_ranges)

        self.set_listado_cargado(listado_cargado)
        self.set_packs_cargado(packs_cargado)
        self.set_ranges_cargado(ranges_cargado)
        self.set_auto_last_load(auto_last_load_text)

    @staticmethod
    def _estado_texto(cargado: bool) -> str:
        return ("Listado de artículos · Listo" if cargado
                else "Listado de artículos · Falta cargar (necesario para buscar y usar Tivendo)")

    def set_listado_cargado(self, cargado: bool):
        """Habilita/deshabilita los botones que necesitan el listado de artículos
        y actualiza el texto de estado en pantalla."""
        state_dep = "normal" if cargado else "disabled"
        self.btn_buscar.config(state=state_dep)
        self.btn_tivendo.config(state="normal")
        self.btn_ingreso.config(state="normal")
        try:
            self.lbl_estado.config(text=self._estado_texto(cargado),
                                   style="HomeDataSuccess.TLabel" if cargado else "HomeDataWarning.TLabel")
        except Exception:
            pass

    @staticmethod
    def _estado_packs_texto(cargado: bool) -> str:
        return ("Maestro de packs · Listo" if cargado
                else "Maestro de packs · Opcional, permite ver packs vinculados")

    def set_packs_cargado(self, cargado: bool):
        try:
            self.lbl_estado_packs.config(text=self._estado_packs_texto(cargado),
                                         style="HomeDataSuccess.TLabel" if cargado else "HomeDataMuted.TLabel")
        except Exception:
            pass

    @staticmethod
    def _estado_rangos_texto(cargado: bool) -> str:
        return ("Lista de precios y rangos · Lista" if cargado
                else "Lista de precios y rangos · Opcional")

    def set_ranges_cargado(self, cargado: bool):
        try:
            self.lbl_estado_rangos.config(text=self._estado_rangos_texto(cargado),
                                          style="HomeDataSuccess.TLabel" if cargado else "HomeDataMuted.TLabel")
        except Exception:
            pass

    def set_auto_last_load(self, texto: str):
        try:
            if texto:
                self.lbl_estado_auto.config(text=f"Listado descargado: {texto}")
            else:
                self.lbl_estado_auto.config(text="Listado descargado: sin registro")
        except Exception:
            pass

class ProvidersView(ttk.Frame):
    """CRUD de proveedores (sin importar desde Excel)."""
    def __init__(self, master, go_home_cb):
        super().__init__(master)
        self.master.title("Administrar proveedores")
        self.pack(fill="both", expand=True, padx=16, pady=14)
        self.go_home_cb = go_home_cb
        self.data: Dict[int,str] = load_empresas()

        top = ttk.Frame(self); top.pack(fill="x")
        ttk.Button(top, text="← Inicio", command=self._back_home).pack(side="left")
        ttk.Label(top, text="Proveedores", style="Title.TLabel").pack(side="left", padx=16)
        ttk.Label(self, text="Selecciona un proveedor para editarlo, o pulsa Nuevo para agregar uno.",
                  style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

        mid = ttk.Frame(self); mid.pack(fill="both", expand=True, pady=8)
        self.tree = ttk.Treeview(mid, columns=("id","nombre"), show="headings", selectmode="browse", height=20)
        self.tree.heading("id", text="Id"); self.tree.column("id", width=90, anchor="center")
        self.tree.heading("nombre", text="Nombre"); self.tree.column("nombre", width=520, anchor="w")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview); self.tree.configure(yscroll=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True); vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.LabelFrame(self, text="Datos del proveedor"); form.pack(fill="x", pady=6)
        row = ttk.Frame(form); row.pack(fill="x", pady=4, padx=8)
        ttk.Label(row, text="Id:").pack(side="left")
        self.ent_id = ttk.Entry(row, width=12); self.ent_id.pack(side="left", padx=(4,10))
        ttk.Label(row, text="Nombre:").pack(side="left")
        self.ent_nombre = ttk.Entry(row); self.ent_nombre.pack(side="left", fill="x", expand=True, padx=(4,10))

        actions = ttk.Frame(form); actions.pack(fill="x", pady=4, padx=8)
        ttk.Button(actions, text="Guardar proveedor", command=self.save_item,
                   style="Primary.TButton").pack(side="left", padx=4)
        ttk.Button(actions, text="Nuevo", command=self.clear_form).pack(side="left", padx=4)
        ttk.Button(actions, text="Eliminar", command=self.delete_item).pack(side="left", padx=4)

        self.status = ttk.Label(self, text="", style="Success.TLabel")
        # El formulario debe seguir visible cuando la tabla se contrae en
        # ventanas pequeñas; reservar su espacio antes de expandir la tabla.
        mid.pack_forget()
        form.pack_forget()
        self.status.pack(side="bottom", fill="x", pady=(4, 0))
        form.pack(side="bottom", fill="x", pady=6)
        mid.pack(side="top", fill="both", expand=True, pady=8)
        self.reload()

    def _back_home(self):
        save_empresas(self.data)
        self.destroy()
        self.go_home_cb()

    def reload(self):
        for x in self.tree.get_children():
            self.tree.delete(x)
        for iid, name in sorted(self.data.items(), key=lambda x: x[0]):
            self.tree.insert("", "end", values=(iid, name))
        self.clear_form()

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        iid, name = self.tree.item(sel[0], "values")
        self.ent_id.delete(0, "end"); self.ent_id.insert(0, str(iid))
        self.ent_nombre.delete(0, "end"); self.ent_nombre.insert(0, str(name))

    def clear_form(self):
        self.ent_id.delete(0, "end"); self.ent_nombre.delete(0, "end")
        self.tree.selection_remove(*self.tree.selection())
        self.status.config(text="")

    def save_item(self):
        id_txt = self.ent_id.get().strip()
        name = self.ent_nombre.get().strip()
        if not id_txt.isdigit():
            messagebox.showwarning("Atención", "El Id debe ser un número entero."); return
        if not name:
            messagebox.showwarning("Atención", "El nombre no puede estar vacío."); return
        iid = int(id_txt)
        exists = iid in self.data
        self.data[iid] = name
        save_empresas(self.data)
        self.reload()
        self.status.config(text=("Actualizado" if exists else "Agregado") + f": {name} (Id. {iid})")

    def delete_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Selecciona un proveedor para eliminar."); return
        iid, name = self.tree.item(sel[0], "values")
        if messagebox.askyesno("Confirmar", f"¿Eliminar '{name}' (Id. {iid})?"):
            try:
                iid_int = int(iid)
                if iid_int in self.data:
                    del self.data[iid_int]
                    save_empresas(self.data)
                self.reload()
                self.status.config(text=f"Eliminado: {name} (Id. {iid})")
            except Exception:
                pass

class SearchView(ttk.Frame):
    """Buscador con barra superior para el botón Volver (no desplaza el contenido)."""
    def __init__(
        self,
        master,
        go_home_cb,
        initial_db_path: Optional[Path],
        packs_path: Optional[Path] = None,
        ranges_path: Optional[Path] = None,
    ):
        super().__init__(master)
        self.master.title(f"Buscador de Códigos — MERCADO HOUSE ({APP_VERSION})")
        self.pack(fill="both", expand=True)
        self.go_home_cb = go_home_cb
        self.prefs = load_prefs()
        self.db_path: Optional[Path] = None  # inicializado explícitamente

        self.packs_path = packs_path
        self.ranges_path = ranges_path

        # Carga de datos
        try:
            self.df, self.empresas = load_data(initial_db_path)
            self.db_path = initial_db_path
        except Exception as e:
            messagebox.showerror("Error al cargar datos", str(e))
            self.destroy(); go_home_cb(); return

        self.last_results = pd.DataFrame()

        # El buscador conserva la apariencia nativa y la distribución de v133.
        # El resto de la aplicación mantiene el tema claro de v134.
        self._previous_theme = None
        search_style = ttk.Style(self)
        if "vista" in search_style.theme_names():
            self._previous_theme = search_style.theme_use()
            search_style.theme_use("vista")

        header = ttk.Frame(self, padding=(10, 10, 10, 0))
        header.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(header, text="Volver al Menú", command=self._back_home).pack(side="left")

        # ===== Contenido del buscador =====
        content = ttk.Frame(self, padding=10)
        content.pack(side=tk.TOP, fill=tk.X)
        content.columnconfigure(0, weight=1)

        ttk.Label(content, text="Código(s) (pega varios: uno por línea o separados por coma/tab):").grid(
            row=0, column=0, sticky="w")
        area = ttk.Frame(content); area.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        area.columnconfigure(0, weight=1)
        self.txt_query = tk.Text(area, height=5, wrap="word")
        self.txt_query.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(area, orient="vertical", command=self.txt_query.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.txt_query.configure(yscrollcommand=vsb.set)
        self.txt_query.bind("<Button-3>", self.show_query_context_menu)
        self.txt_query.bind("<Button-2>", self.show_query_context_menu)

        opts = ttk.Frame(content); opts.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.exact = tk.BooleanVar(value=True)
        self.by_barras = tk.BooleanVar(value=False)
        self.by_tivendo = tk.BooleanVar(value=False)
        self.by_packs = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Coincidencia exacta (código)", variable=self.exact).pack(side="left")
        ttk.Checkbutton(opts, text="Buscar por códigos de barra", variable=self.by_barras).pack(side="left", padx=(12,0))
        ttk.Checkbutton(opts, text="Buscar por código Tivendo", variable=self.by_tivendo).pack(side="left", padx=(12,0))
        ttk.Checkbutton(opts, text="Buscar código de pack", variable=self.by_packs).pack(side="left", padx=(12,0))

        row3 = ttk.Frame(content); row3.grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(row3, text="Empresa:").pack(side="left")
        self.var_emp = tk.StringVar()

        # Filtro en vivo de proveedores (mini buscador)
        self.var_emp_search = tk.StringVar()
        ttk.Label(row3, text="Buscar:").pack(side="left", padx=(8, 2))
        ent_emp = ttk.Entry(row3, textvariable=self.var_emp_search, width=22)
        ent_emp.pack(side="left")
        ent_emp.bind("<KeyRelease>", self.on_emp_search)

        self.empresas_choices = ["— Cualquiera —"] + [f"{v} (Id. {k})" for k, v in sorted(self.empresas.items(), key=lambda x: x[1].lower())]
        self.cbo_emp = ttk.Combobox(row3, textvariable=self.var_emp, values=self.empresas_choices, width=40, state="readonly")
        self.cbo_emp.pack(side="left", padx=8)
        self.cbo_emp.set("— Cualquiera —")
        self.cbo_emp.bind("<Key>", self.on_emp_key)

        btns = ttk.Frame(row3)
        btns.pack(side="left")
        ttk.Button(btns, text="Buscar por Proveedor", command=self.on_search).pack(side="left", padx=4)
        ttk.Button(btns, text="Buscar general", command=lambda: self.on_search(force_general=True)).pack(side="left", padx=4)
        ttk.Button(btns, text="Limpiar", command=self.on_clear).pack(side="left", padx=4)
        ttk.Button(btns, text="Copiar...", command=self.show_copy_menu).pack(side="left", padx=4)

        self.var_result_count = tk.StringVar(value="Aún no hay búsqueda")

        # ttk.Treeview desplaza cada nivel hijo ("indent") bastante hacia la
        # derecha por defecto, asi que la casilla ☐ de un pack (nivel 1)
        # quedaria mucho mas a la derecha que el ▸ del articulo (nivel 0).
        # Con un estilo propio de indent chico, la casilla queda pegada a la
        # izquierda, alineada con el ▸/▾.
        style = ttk.Style(self)
        style.configure("Acordeon.Treeview", indent=0)
        cols = ("codigo","nombre","barcode_interno","barcode_externo","empresa","packs","rango1","rango2")
        self.tree = ttk.Treeview(self, columns=cols, show="tree headings", selectmode="extended", style="Acordeon.Treeview")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=34, minwidth=34, stretch=False, anchor="w")
        for c, t in zip(cols, ["Código","Nombre","Cód. barra interno","Cód. barra externo","Empresa","Packs","Rango 1","Rango 2"]):
            self.tree.heading(c, text=t)
        self.tree.heading("packs", text="Packs")
        self.tree.heading("rango1", text="Rango 1")
        self.tree.heading("rango2", text="Rango 2")
        self._tree_headers = {
            "codigo": "Código",
            "nombre": "Nombre",
            "barcode_interno": "Cód. barra interno",
            "barcode_externo": "Cód. barra externo",
            "empresa": "Empresa",
            "packs": "Packs",
            "rango1": "Rango 1",
            "rango2": "Rango 2",
        }
        self._tree_width_limits = {
            "codigo": (95, 220),
            "nombre": (240, 760),
            "barcode_interno": (145, 240),
            "barcode_externo": (145, 240),
            "empresa": (120, 360),
            "packs": (70, 105),
            "rango1": (90, 170),
            "rango2": (90, 170),
        }
        for c in cols:
            min_width, _max_width = self._tree_width_limits[c]
            anchor = "center" if c in {"packs", "rango1", "rango2"} else "w"
            self.tree.column(c, width=min_width, minwidth=min_width, anchor=anchor, stretch=False)
        self.tree.tag_configure("dup_input", background="#FFF3CD")
        self.tree.tag_configure("pack_row", background="#F1F1FB")

        # ---- Acordeon de packs vinculados ----
        # _row_lookup_code: iid de articulo -> codigo/identificador con el que
        #   se consulta el Maestro de Packs (para cargar sus packs al abrir).
        # _pack_children_loaded: iids de articulo cuyos packs ya se insertaron
        #   de verdad como hijos en el arbol (para no volver a consultarlos
        #   cada vez que se abre el acordeon, solo la primera vez).
        # _checked_pack_iids: iids de fila de PACK marcados con la casilla ☑,
        #   son los que "Copiar codigo pack" copia.
        # El indicador ▸/▾ nativo del Treeview solo aparece si el item ya
        # tiene hijos, asi que a cada articulo CON pack se le agrega un hijo
        # "placeholder" vacio en populate() para que el indicador se vea
        # desde el principio, sin cargar los packs todavia. <<TreeviewOpen>>
        # se dispara al hacer clic en ese indicador (o doble clic nativo
        # sobre la fila): ahi se reemplaza el placeholder por los packs
        # reales, una sola vez.
        self._row_lookup_code = {}
        self._pack_children_loaded = set()
        self._checked_pack_iids = set()
        self._pack_child_records = {}
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<Button-1>", self._on_tree_click_toggle_checkbox, add="+")

        vsb2 = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb2 = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb2.set, xscroll=hsb2.set)
        # hsb2 NO se superpone sobre el arbol (a diferencia de vsb2): un
        # scrollbar horizontal ocupa casi el alto de una fila entera, y
        # superponerlo sobre el borde inferior tapaba la ultima fila (no se
        # podia ver ni hacer scroll hasta ella). Se empaqueta en su propio
        # espacio justo debajo, con el mismo padx que la tabla para que sus
        # bordes queden alineados con ella en vez de verse "suelto".
        self.var_status = tk.StringVar(value=self.status_db_text)
        lbl_status = ttk.Label(self, textvariable=self.var_status, anchor="w", cursor="hand2")
        lbl_status.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        lbl_status.bind("<Button-1>", lambda e: self.on_change_db())  # click para cambiar BD
        hsb2.pack(side=tk.BOTTOM, fill=tk.X, padx=10)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(8, 10))
        vsb2.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")

        self._context_column = None
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copiar columna seleccionada", command=self.copy_selected_context_column)
        self.menu.add_separator()
        self.menu.add_command(label="Eliminar fila(s) seleccionada(s)", command=self.remove_selected_rows)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Button-2>", self.show_context_menu)
        self.tree.bind("<Button-1>", self.clear_result_selection_on_blank_click, add="+")

        self.query_menu = tk.Menu(self, tearoff=0)
        self.query_menu.add_command(label="Pegar", command=lambda: self.txt_query.event_generate("<<Paste>>"))
        self.query_menu.add_command(label="Eliminar código seleccionado", command=self.delete_selected_query_code)
        self.query_menu.add_command(label="Limpiar códigos", command=lambda: self.txt_query.delete("1.0", "end"))

        self.bind_all("<Return>", lambda e: self.on_search())
        self.bind_all("<Control-s>", lambda e: self.export_csv())
        self.bind_all("<Control-l>", lambda e: self.on_clear())
        self.tree.bind("<Control-c>", lambda e: self.copy_selected_rows())
        self.tree.bind("<Delete>", lambda e: self.remove_selected_rows())
        self.txt_query.focus_set()

    def on_emp_search(self, event=None):
        """Filtra en vivo la lista de proveedores en el combobox según el mini buscador."""
        _filter_combobox_choices(
            self.var_emp_search.get().strip().lower(),
            self.empresas_choices,
            self.cbo_emp,
            self.var_emp,
        )

    def _back_home(self):
        try:
            prefs = self.prefs
            prefs["exact"] = bool(self.exact.get())
            prefs["by_barras"] = bool(self.by_barras.get())
            prefs["empresa_display"] = self.cbo_emp.get()
            save_prefs(prefs)
        except Exception:
            pass
        self.destroy()
        self.go_home_cb()

    def destroy(self):
        previous_theme = getattr(self, "_previous_theme", None)
        if previous_theme:
            try:
                ttk.Style(self).theme_use(previous_theme)
            except tk.TclError:
                pass
            self._previous_theme = None
        super().destroy()

    # ---- Helpers buscador ----
    def on_change_db(self):
        """Permite seleccionar una nueva base de datos sin reiniciar la aplicación."""
        newf = filedialog.askopenfilename(
            title="Selecciona la base de datos (Excel/CSV)",
            initialdir=self.prefs.get("last_dir"),
            filetypes=[("Excel","*.xlsm *.xlsx *.xls"),("CSV","*.csv *.gz *.zip"),("Todos","*.*")]
        )
        if not newf:
            return
        newp = Path(newf)
        try:
            df, emp = load_data(newp)
        except Exception as e:
            messagebox.showerror("Error al cargar la nueva BD", str(e)); return
        self.db_path = newp
        self.df, self.empresas = df, emp
        old = self.cbo_emp.get()
        self.empresas_choices = ["— Cualquiera —"] + [f"{v} (Id. {k})" for k, v in sorted(self.empresas.items(), key=lambda x: x[1].lower())]
        self.cbo_emp["values"] = self.empresas_choices
        self.cbo_emp.set(old if old in self.empresas_choices else "— Cualquiera —")
        self.on_clear()
        self.var_status.set(self.status_db_text)
        try:
            self.prefs["last_dir"] = str(newp.parent)
            save_prefs(self.prefs)
        except Exception:
            pass

    @property
    def status_db_text(self) -> str:
        return f"BD: {self.db_path.name} | Listo." if self.db_path else "BD: autodetectada en carpeta | Listo."

    def on_emp_key(self, event):
        """Navega el combobox de empresa por primera letra al escribir."""
        ch = event.char
        if not ch or len(ch) != 1 or not ch.isprintable():
            return
        target = _norm_lc(ch)
        vals = list(self.cbo_emp["values"])
        if not vals:
            return
        cur = self.cbo_emp.current()
        start = (cur + 1) % len(vals) if cur is not None and cur >= 0 else 0
        for offset in range(len(vals)):
            k = (start + offset) % len(vals)
            if _norm_lc(vals[k].lstrip("— ").strip()).startswith(target):
                try:
                    self.cbo_emp.current(k)
                except Exception:
                    self.cbo_emp.set(vals[k])
                return

    def show_context_menu(self, event):
        """Muestra el menú contextual al hacer click derecho en la tabla."""
        try:
            iid = self.tree.identify_row(event.y)
            col_id = self.tree.identify_column(event.x)
            columns = list(self.tree["columns"])
            self._context_column = None
            if col_id.startswith("#"):
                try:
                    idx = int(col_id[1:]) - 1
                    if 0 <= idx < len(columns):
                        self._context_column = columns[idx]
                except ValueError:
                    self._context_column = None

            if iid:
                self.tree.focus(iid)
                if iid not in self.tree.selection():
                    self.tree.selection_set(iid)
            if self.tree.selection():
                label = self._tree_headers.get(self._context_column, "columna")
                self.menu.entryconfig(0, label=f"Copiar {label} seleccionado(s)")
                self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def clear_result_selection_on_blank_click(self, event):
        if self.tree.identify_row(event.y):
            return
        self.tree.selection_remove(*self.tree.selection())
        self.tree.focus("")

    def _query_has_selection_at(self, index: str) -> bool:
        ranges = self.txt_query.tag_ranges("sel")
        if len(ranges) != 2:
            return False
        return (
            self.txt_query.compare(ranges[0], "<=", index)
            and self.txt_query.compare(index, "<=", ranges[1])
        )

    def _select_query_code_at(self, index: str) -> bool:
        text = self.txt_query.get("1.0", "end-1c")
        if not text:
            return False

        try:
            pos = int(self.txt_query.count("1.0", index, "chars")[0])
        except Exception:
            return False

        pos = max(0, min(pos, len(text) - 1))
        separators = {",", "\t", "\n"}
        if text[pos] in separators:
            if pos > 0 and text[pos - 1] not in separators:
                pos -= 1
            else:
                nxt = pos + 1
                while nxt < len(text) and text[nxt] in separators.union({" "}):
                    nxt += 1
                if nxt >= len(text):
                    return False
                pos = nxt

        start = pos
        while start > 0 and text[start - 1] not in separators:
            start -= 1
        end = pos + 1
        while end < len(text) and text[end] not in separators:
            end += 1

        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start >= end:
            return False

        start_idx = f"1.0 + {start} chars"
        end_idx = f"1.0 + {end} chars"
        self.txt_query.tag_remove("sel", "1.0", "end")
        self.txt_query.tag_add("sel", start_idx, end_idx)
        self.txt_query.mark_set("insert", end_idx)
        self.txt_query.see(start_idx)
        return True

    def show_query_context_menu(self, event):
        """Muestra acciones para el código pegado/escrito bajo el cursor."""
        try:
            self.txt_query.focus_set()
            index = self.txt_query.index(f"@{event.x},{event.y}")
            if not self._query_has_selection_at(index):
                self._select_query_code_at(index)
            self.query_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.query_menu.grab_release()
        return "break"

    def delete_selected_query_code(self):
        try:
            self.txt_query.delete("sel.first", "sel.last")
            self.txt_query.tag_remove("sel", "1.0", "end")
        except tk.TclError:
            return

    def copy_selected_context_column(self):
        sels = self.tree.selection()
        col = self._context_column
        if not sels or not col:
            return
        lines = [str(self.tree.set(iid, col)) for iid in sels]
        label = self._tree_headers.get(col, col)
        self._copy_to_clipboard(
            JOIN_SEP.join(lines),
            f"Copiados {len(lines)} valor(es) de {label} al portapapeles.",
        )

    def copy_selected_rows(self):
        sels = self.tree.selection()
        if not sels:
            return
        rows = ["\t".join(str(v) for v in self.tree.item(iid, "values")) for iid in sels]
        self._copy_to_clipboard(
            JOIN_SEP.join(rows),
            f"Copiadas {len(rows)} fila(s) seleccionada(s) al portapapeles.",
        )

    def remove_selected_rows(self):
        """Elimina las filas seleccionadas SOLO de la lista de resultados actual
        (no modifica la base de datos original). Permite limpiar duplicados antes de copiar.
        """
        sels = self.tree.selection()
        if not sels:
            messagebox.showinfo("Info", "Selecciona una o más filas para eliminar de la lista.")
            return

        # Mapear cada item visual a su índice en last_results
        children = list(self.tree.get_children())
        remove_set = {i for i, iid in enumerate(children) if iid in sels}
        if not remove_set or self.last_results is None or self.last_results.empty:
            return

        # Construir nuevo DataFrame sin esas filas
        keep_indices = [i for i in range(len(self.last_results)) if i not in remove_set]
        if not keep_indices:
            # Si el usuario eliminó todo, dejamos resultados vacíos
            self.last_results = self.last_results.head(0).copy()
        else:
            self.last_results = self.last_results.iloc[keep_indices].reset_index(drop=True)

        # Recalcular cantidad de 'No encontrado' para el texto de estado
        try:
            nombre_series = self.last_results["nombre"] if "nombre" in self.last_results.columns else pd.Series(dtype=str)
            nf_count = int((nombre_series.astype(str) == "No encontrado").sum())
        except Exception:
            nf_count = 0

        # Volver a poblar la grilla desde last_results ya filtrado
        self.populate(self.last_results, emp_id=None, not_found_count=nf_count)

    def on_clear(self):
        """Limpia el cuadro de búsqueda, los resultados y restaura el estado inicial."""
        self.txt_query.delete("1.0", "end")
        self.cbo_emp.set("— Cualquiera —")
        for x in self.tree.get_children(): self.tree.delete(x)
        self.var_status.set(self.status_db_text)
        self.var_result_count.set("Aún no hay búsqueda")
        self.last_results = pd.DataFrame()

    def _selected_emp_id(self):
        m = re.search(r"\(Id\.?\s*(\d+)\)", self.cbo_emp.get())
        return m.group(1) if m else None

    def _filter_by_empresa(self, df, force_general=False):
        emp_id = self._selected_emp_id()
        if not force_general and emp_id is not None:
            # empresa_id ya contiene solo dígitos (normalizado en load_data)
            df = df[df["empresa_id"] == emp_id]
        return df, emp_id

    def _display_emp(self, eid):
        # empresa_id siempre contiene solo dígitos tras load_data/_extract_id
        num = str(eid).strip()
        if not num or not num.isdigit():
            return ""
        name = self.empresas.get(int(num), "")
        return f"{name} (Id. {num})"

    @property
    def packs_index(self) -> dict:
        """Siempre lee el valor actual desde RootApp (self.master), en vez de
        una copia tomada al construir esta vista. La carga de packs/rangos
        de la ultima carga automatica termina en un hilo de fondo despues de
        que la ventana ya esta abierta; si esta vista guardara una copia fija
        tomada al momento de crearse, se quedaria con el diccionario vacio
        para siempre aunque los packs terminen de cargar mas tarde."""
        return getattr(self.master, "packs_index", None) or {}

    @property
    def ranges_index(self) -> dict:
        return getattr(self.master, "ranges_index", None) or {}

    @property
    def packs_by_code_index(self) -> Dict[str, List[dict]]:
        """Indice inverso: identificador del PACK (su codigo interno O su
        codigo de barra) -> sus articulos componentes. self.packs_index esta
        indexado por articulo, asi que aca lo invertimos para poder buscar
        directamente por cualquiera de los dos identificadores del pack (por
        ejemplo, al escanear el codigo de barra impreso en el pack). Se
        recalcula en cada acceso para reflejar siempre el packs_index actual
        (ver comentario de esa property)."""
        index: Dict[str, List[dict]] = {}
        for records in self.packs_index.values():
            for rec in records:
                for field in ("pack_codigo", "pack_barra"):
                    key = _norm_pack_code(rec.get(field, ""))
                    if key:
                        index.setdefault(key, []).append(rec)
        return index

    def _pack_records_for_code(self, codigo: str):
        if not self.packs_index:
            return []
        return self.packs_index.get(_norm_pack_code(codigo), [])

    def _pack_component_codes(self, codigo: str):
        """Si `codigo` es el codigo de un PACK (no de un articulo suelto),
        devuelve los codigos de los articulos que lo componen (sin
        duplicados, conservando el orden)."""
        if not self.packs_by_code_index:
            return []
        records = self.packs_by_code_index.get(_norm_pack_code(codigo), [])
        codes = [r["articulo_codigo"] for r in records if str(r.get("articulo_codigo", "")).strip()]
        return list(dict.fromkeys(codes))

    def _catalog_rows_for_exact_code(self, df, codigo: str, include_suffix: bool = False):
        """Filas del catalogo cuyo codigo o identificador (Tivendo) sea
        exactamente `codigo`. Se usa para resolver los articulos que
        componen un pack, sin depender de los checkbox de busqueda (exacto/
        por codigo Tivendo/por codigo de barra) que aplican a la busqueda
        que escribio el usuario, no a esta resolucion interna.

        Si `include_suffix` es True, tambien compara contra el/los codigo(s)
        al final de Nombre/Codigo (ej. "... - 7582 0"). Esto queda atado a la
        casilla "Coincidencia exacta (código)": solo se activa cuando esa
        casilla esta marcada; desmarcada, se sigue usando la busqueda difusa
        normal (encuentra el mas similar)."""
        code_ws_lc = _ws_re.sub(" ", str(codigo)).strip().lower()
        if not code_ws_lc:
            return df.iloc[0:0]
        direct_mask = (df["_codigo_ws"].str.lower() == code_ws_lc)
        if "_identificador_ws" in df.columns:
            direct_mask = direct_mask | (df["_identificador_ws"].str.lower() == code_ws_lc)
        if not include_suffix:
            return df[direct_mask]

        code_compact = code_ws_lc.replace(" ", "")
        suffix_mask = pd.Series(False, index=df.index)
        if "_nombre_suffix_codes" in df.columns:
            suffix_mask = suffix_mask | df["_nombre_suffix_codes"].apply(lambda codes: code_compact in codes)
        if "_codigo_suffix_codes" in df.columns:
            suffix_mask = suffix_mask | df["_codigo_suffix_codes"].apply(lambda codes: code_compact in codes)

        result = df[direct_mask | suffix_mask].copy()
        # Las filas que SOLO calzaron por el codigo al final del nombre (no
        # por su Codigo/Identificador real) muestran el codigo que escribio
        # el usuario en la columna "Código", en vez del campo Codigo crudo
        # del catalogo (que puede traer texto de mas, ej. "NUSS 90 GR -
        # 7582 0" en vez de solo "7582 0").
        only_suffix = (suffix_mask & ~direct_mask).reindex(result.index, fill_value=False)
        if only_suffix.any():
            result.loc[only_suffix, "codigo"] = _ws_re.sub(" ", str(codigo)).strip()
        return result

    def _score_results_with_pack_fallback(self, df, code, exact, by_barras, by_tivendo, tok_index, by_packs=True):
        """Busca `code` en el catalogo. Si no aparece pero coincide con el
        codigo de un PACK, busca en su lugar los articulos que lo componen
        (los codigos de pack no existen como filas del catalogo). Si
        `by_packs` es False, se omite ese paso (queda igual que antes de
        que existiera la busqueda por pack)."""
        code_ws = _ws_re.sub(" ", str(code)).strip()
        code_norm = normalize_code_token(code_ws)
        sub = _score_results(df, code, code_ws, code_norm, exact, by_barras, by_tivendo, tok_index)
        if not sub.empty:
            return sub, False

        # Antes de asumir que es un codigo de PACK: puede que el producto
        # exista de verdad en el catalogo por su Identificador, pero la
        # casilla "Buscar por codigo Tivendo" este apagada. Un producto real
        # y exacto siempre gana por sobre la interpretacion "es un pack",
        # sin importar esa casilla (que solo afecta busquedas difusas).
        direct = self._catalog_rows_for_exact_code(df, code, include_suffix=exact)
        if not direct.empty:
            result = direct.copy()
            result["__score"] = 100
            return result, False

        if not by_packs:
            return sub, False

        component_codes = self._pack_component_codes(code)
        if not component_codes:
            return sub, False

        frames = [self._catalog_rows_for_exact_code(df, c) for c in component_codes]
        frames = [f for f in frames if not f.empty]
        if not frames:
            return sub, False
        result = pd.concat(frames, ignore_index=True).copy()
        result["__score"] = 100
        return result, True

    # ---- Acordeon de packs vinculados ----
    def _on_tree_open(self, event):
        """Se dispara con <<TreeviewOpen>> cuando el usuario abre una fila
        (clic en el indicador ▸ nativo, o doble clic nativo sobre la fila).
        Solo actua la PRIMERA vez que se abre un articulo: reemplaza su hijo
        "placeholder" (vacio, solo estaba para que el indicador se vea) por
        sus packs reales. Abrirla de nuevo despues no vuelve a consultar
        nada, y cerrarla solo la oculta (ttk.Treeview no borra los hijos al
        cerrar), asi que las casillas marcadas se mantienen."""
        iid = self.tree.focus()
        if not iid or iid in self._pack_children_loaded:
            return
        self._populate_pack_children(iid)

    def _populate_pack_children(self, iid):
        """Reemplaza el hijo placeholder de `iid` por sus packs reales, cada
        uno con su propia casilla ☐ (columna #0) para marcarla antes de
        copiar."""
        self.tree.delete(*self.tree.get_children(iid))
        codigo_busqueda = self._row_lookup_code.get(iid, "")
        records = self._pack_records_for_code(codigo_busqueda)
        if not records:
            self._pack_children_loaded.add(iid)
            return
        for rec in records:
            child = self.tree.insert(
                iid, "end",
                text="☐",
                values=(
                    rec.get("pack_codigo", ""),
                    rec.get("pack_nombre", ""),
                    rec.get("pack_barra", ""),
                    "", "", "(pack)", "", "",
                ),
                tags=("pack_row",),
            )
            self._pack_child_records[child] = rec
        self.tree.item(iid, open=True)
        self._pack_children_loaded.add(iid)

    def _on_tree_click_toggle_checkbox(self, event):
        """Clic en la columna de icono (#0) de una fila de PACK marca/
        desmarca su casilla ☐/☑. En una fila de articulo esa misma columna
        solo tiene la flecha nativa de expandir/colapsar, asi que ahi no
        hacemos nada."""
        if self.tree.identify_region(event.x, event.y) != "tree":
            return
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self._pack_child_records:
            return
        if iid in self._checked_pack_iids:
            self._checked_pack_iids.discard(iid)
            self.tree.item(iid, text="☐")
        else:
            self._checked_pack_iids.add(iid)
            self.tree.item(iid, text="☑")

    def copy_checked_pack_barcodes(self):
        """Copia SOLO el codigo de barra de los packs marcados con ☑. A
        diferencia del resto de los botones "Copiar...", si no hay ningun
        pack marcado NO copia todo: avisa y no copia nada."""
        if not self._checked_pack_iids:
            messagebox.showwarning(
                "Atención",
                "No hay ningun pack marcado. Abre el ▸ de una fila con "
                "\U0001F7E2 para ver sus packs y marca ☐ los que quieras copiar.",
            )
            return
        codes = []
        for parent in self.tree.get_children():
            for child in self.tree.get_children(parent):
                if child not in self._checked_pack_iids:
                    continue
                rec = self._pack_child_records.get(child)
                if not rec:
                    continue
                code = str(rec.get("pack_barra", "")).strip()
                if code and code not in codes:
                    codes.append(code)
        if not codes:
            messagebox.showwarning("Atención", "Los packs marcados no tienen codigo de barra valido.")
            return
        self._copy_to_clipboard(
            JOIN_SEP.join(codes),
            f"Copiados {len(codes)} codigo(s) de barra de pack (marcados).",
        )

    def _range_record_for_code(self, codigo: str):
        if not self.ranges_index:
            return {}
        return self.ranges_index.get(_norm_pack_code(codigo), {})

    def _autosize_result_columns(self):
        """Ajusta las columnas al texto visible, con topes para mantener la tabla usable."""
        try:
            body_font = tkfont.nametofont("TkDefaultFont")
            heading_font = tkfont.nametofont("TkHeadingFont")
        except Exception:
            body_font = heading_font = None

        def measure(font, text):
            text = str(text or "")
            if font is None:
                return len(text) * 7
            return font.measure(text)

        children = self.tree.get_children()
        for col in self.tree["columns"]:
            min_width, max_width = self._tree_width_limits.get(col, (90, 260))
            best = measure(heading_font, self._tree_headers.get(col, col)) + 34
            for row_id in children:
                best = max(best, measure(body_font, self.tree.set(row_id, col)) + 28)
                if best >= max_width:
                    break
            width = max(min_width, min(best, max_width))
            self.tree.column(col, width=width, minwidth=min_width)

    def populate(self, df, emp_id, not_found_count=0):
        """Rellena el Treeview con los resultados de búsqueda y actualiza la barra de estado."""
        for x in self.tree.get_children(): self.tree.delete(x)
        total = len(df)
        self.var_result_count.set(f"{total} fila(s) · {not_found_count} no encontrado(s)")

        # Cada busqueda nueva reinicia el estado del acordeon de packs (los
        # hijos ya cargados se borraron junto con las filas padre arriba).
        self._row_lookup_code = {}
        self._pack_children_loaded = set()
        self._checked_pack_iids = set()
        self._pack_child_records = {}

        dup_inputs = set()
        if "__input" in df.columns:
            inp_series = df["__input"].fillna("").astype(str).str.strip()
            if not inp_series.empty:
                counts = inp_series[inp_series != ""].value_counts()
                dup_inputs = set(counts[counts > 1].index)

        # Extraer columnas como listas (mucho más rápido que iterrows)
        col_ident     = df["identificador"].fillna("").astype(str).tolist() if "identificador" in df.columns else [""] * total
        col_codigo    = df["codigo"].fillna("").astype(str).tolist() if "codigo" in df.columns else [""] * total
        col_nombre    = df["nombre"].fillna("").astype(str).tolist() if "nombre" in df.columns else [""] * total
        col_bi        = df["barcode_interno"].fillna("").astype(str).tolist() if "barcode_interno" in df.columns else [""] * total
        col_be        = df["barcode_externo"].fillna("").astype(str).tolist() if "barcode_externo" in df.columns else [""] * total
        col_eid       = df["empresa_id"].fillna("").astype(str).tolist() if "empresa_id" in df.columns else [""] * total
        col_inp       = df["__input"].fillna("").astype(str).tolist() if "__input" in df.columns else [""] * total

        ins = self.tree.insert
        disp = self._display_emp
        show_packs = self.by_packs.get()
        for ident, cod, nom, bi, be, eid, inp in zip(col_ident, col_codigo, col_nombre, col_bi, col_be, col_eid, col_inp):
            emp_txt = "" if nom == "No encontrado" else disp(eid)
            lookup_code = ident or cod
            # Si la casilla "Buscar código de pack" esta desmarcada, no se
            # muestra nada de packs (ni la columna ni el acordeon): el
            # usuario explicitamente no pidio esa busqueda.
            pack_records = [] if (nom == "No encontrado" or not show_packs) else self._pack_records_for_code(lookup_code)
            if nom == "No encontrado" or not show_packs:
                pack_txt = ""
            elif pack_records:
                pack_txt = f"🟢 Si ({len(pack_records)})"
            else:
                pack_txt = "No"
            range_rec = {} if nom == "No encontrado" else self._range_record_for_code(ident or cod)
            rango1 = range_rec.get("rango1", "")
            rango2 = range_rec.get("rango2", "")
            tags = ("dup_input",) if inp.strip() in dup_inputs else ()
            row_iid = ins("", "end", values=(cod, nom, bi, be, emp_txt, pack_txt, rango1, rango2), tags=tags)
            if nom != "No encontrado":
                # Guarda con que codigo consultar el Maestro de Packs cuando
                # se abra el acordeon de esta fila.
                self._row_lookup_code[row_iid] = lookup_code
                if pack_records:
                    # Placeholder vacio: existe solo para que el Treeview
                    # dibuje el indicador ▸ desde el principio (sin el, no
                    # se muestra ningun indicador hasta que la fila ya
                    # tenga hijos reales). _on_tree_open lo reemplaza por
                    # los packs de verdad la primera vez que se abre.
                    ins(row_iid, "end", tags=("pack_placeholder",))

        self._autosize_result_columns()

        extra = ""
        if not_found_count: extra += f" | No encontrados: {not_found_count}"
        if dup_inputs: extra += f" | Duplicados (por código ingresado): {len(dup_inputs)}"
        if self.packs_index:
            extra += " | Packs activos"
        if self.ranges_index:
            extra += " | Rangos activos"
        self.var_status.set(f"{self.status_db_text} | Resultados: {total} fila(s). Mostrando hasta {MAX_RESULTS}.{extra}")
        self.last_results = df

    def on_search(self, force_general=False):
        """Ejecuta la búsqueda con los códigos ingresados y popula la tabla."""
        raw   = self.txt_query.get("1.0", "end")
        codes = parse_codes(raw)
        df, emp_id = self._filter_by_empresa(self.df, force_general=force_general)

        if len(codes) == 0:
            self.populate(df.head(MAX_RESULTS), emp_id)
            return

        exact     = self.exact.get()
        by_barras = self.by_barras.get()
        by_tivendo = self.by_tivendo.get()
        by_packs  = self.by_packs.get()
        tok_index = _LOAD_DATA_CACHE.get("index")

        if len(codes) == 1:
            q      = codes[0]
            q_ws   = _ws_re.sub(" ", q).strip()
            q_norm = normalize_code_token(q_ws)
            out, is_pack = self._score_results_with_pack_fallback(df, q, exact, by_barras, by_tivendo, tok_index, by_packs)
            if out.empty:
                if not by_barras and _looks_like_barcode(q):
                    hint = "  Parece codigo de barra: marca 'Buscar por codigos de barra' y vuelve a buscar."
                    suggs = []
                else:
                    suggs = _find_fuzzy_suggestions(q_norm, df)
                if suggs:
                    hint = "  ¿Quisiste decir: " + ", ".join(suggs) + "?"
                elif not (not by_barras and _looks_like_barcode(q)):
                    hint = ""
                self.populate(_make_nf_row(q, 0), emp_id, not_found_count=1)
                self.var_status.set(f"{self.status_db_text} | No encontrado: {q}.{hint}")
                return
            out = out.drop(columns=["__score"])
            out["__input"] = q
            self.populate(out.head(MAX_RESULTS), emp_id)
            if is_pack:
                self.var_status.set(
                    self.var_status.get()
                    + f" | '{q}' es un código de PACK: se muestran sus {len(out)} artículo(s) componentes."
                )
            return

        frames, nf = [], 0
        for i, code in enumerate(codes):
            code_ws = _ws_re.sub(" ", str(code)).strip()
            if not code_ws:
                continue
            sub, is_pack = self._score_results_with_pack_fallback(df, code, exact, by_barras, by_tivendo, tok_index, by_packs)
            if sub.empty:
                nf_row = _make_nf_row(code, i)
                nf_row["__pos"] = i
                nf_row["__score"] = -1
                frames.append(nf_row)
                nf += 1
            else:
                sub["__input"] = code
                sub["__pos"]   = i
                frames.append(sub)

        if not frames:
            self.populate(
                pd.DataFrame(columns=["identificador","codigo","nombre","barcode_interno","barcode_externo","empresa_id","__input"]),
                emp_id, not_found_count=nf,
            )
            return

        out = pd.concat(frames, ignore_index=True)
        if "__pos" not in out.columns:
            out["__pos"] = range(len(out))
        if "__score" not in out.columns:
            out["__score"] = -1
        out = out.sort_values(["__pos", "__score"], ascending=[True, False])
        drop_cols = [c for c in ("__score", "__pos") if c in out.columns]
        if drop_cols:
            out = out.drop(columns=drop_cols)
        self.populate(out.head(MAX_RESULTS), emp_id, not_found_count=nf)
        if nf and not by_barras and any(_looks_like_barcode(c) for c in codes):
            self.var_status.set(
                self.var_status.get()
                + " | Si estas buscando codigos de barra, marca 'Buscar por codigos de barra'."
            )

    # ---- Helper de portapapeles ----
    def _copy_to_clipboard(self, text: str, status_msg: str):
        """Copia texto al portapapeles y actualiza la barra de estado."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # necesario en algunos sistemas para que el clipboard se actualice
        self.var_status.set(status_msg)

    def show_copy_menu(self):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Códigos de barra internos", command=self.copy_barcodes_internos)
        menu.add_command(label="Códigos de barra externos", command=self.copy_barcodes_externos)
        menu.add_command(label="Nombres + código barra interno", command=self.copy_nombre_interno)
        menu.add_command(label="Nombres", command=self.copy_nombres)
        menu.add_separator()
        menu.add_command(label="NO encontrados", command=self.copy_not_found_inputs)
        menu.add_separator()
        menu.add_command(label="Copiar codigo pack", command=self.copy_checked_pack_barcodes)
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _require_results(self) -> bool:
        """Devuelve True si hay resultados; muestra aviso y devuelve False si no."""
        if self.last_results is None or self.last_results.empty:
            messagebox.showwarning("Atención", "No hay resultados para copiar. Realiza una búsqueda primero.")
            return False
        return True

    def _copy_barcode_col(self, col: str, label: str):
        """Helper para copiar una columna de códigos de barra de last_results."""
        if not self._require_results():
            return
        lines = self.last_results.get(col, pd.Series(dtype=str)).fillna("").astype(str).tolist()
        self._copy_to_clipboard(
            JOIN_SEP.join(lines),
            f"{self.status_db_text} | Copiados {len(lines)} {label} al portapapeles.",
        )

    def copy_barcodes_internos(self):
        self._copy_barcode_col("barcode_interno", "códigos internos")

    def copy_barcodes_externos(self):
        self._copy_barcode_col("barcode_externo", "códigos externos")

    def copy_nombre_interno(self):
        """Copia nombre + código de barra interno de cada resultado al portapapeles."""
        if not self._require_results():
            return
        df = self.last_results
        nombres = df.get("nombre", pd.Series(dtype=str)).fillna("").astype(str)
        internos = df.get("barcode_interno", pd.Series(dtype=str)).fillna("").astype(str)
        lines = [
            ("" if n == "No encontrado" else sanitize_cell(n)) + "\t" + b
            for n, b in zip(nombres, internos)
        ]
        self._copy_to_clipboard(
            JOIN_SEP.join(lines),
            f"{self.status_db_text} | Copiadas {len(lines)} filas (nombre + interno) al portapapeles.",
        )

    def copy_nombres(self):
        """Copia solo los nombres de cada resultado al portapapeles."""
        if not self._require_results():
            return
        nombres = self.last_results.get("nombre", pd.Series(dtype=str)).fillna("").astype(str)
        lines = ["" if n == "No encontrado" else sanitize_cell(n) for n in nombres]
        self._copy_to_clipboard(
            JOIN_SEP.join(lines),
            f"{self.status_db_text} | Copiados {len(lines)} nombres al portapapeles.",
        )

    def copy_not_found_inputs(self):
        """Copia los códigos buscados que no se encontraron al portapapeles."""
        if not self._require_results():
            return
        if "__input" not in self.last_results.columns:
            messagebox.showwarning("Atención", "No hay resultados 'No encontrado' para copiar.")
            return
        nf = self.last_results[self.last_results["nombre"].astype(str) == "No encontrado"]
        if nf.empty:
            messagebox.showinfo("Info", "No hay códigos 'No encontrado' en los resultados."); return
        lines = nf["__input"].astype(str).tolist()
        self._copy_to_clipboard(
            JOIN_SEP.join(lines),
            f"{self.status_db_text} | Copiados {len(lines)} código(s) NO ENCONTRADOS.",
        )

    def export_csv(self):
        """Exporta los resultados actuales a un archivo CSV elegido por el usuario."""
        if self.last_results is None or self.last_results.empty:
            messagebox.showwarning("Atención", "No hay resultados para exportar. Realiza una búsqueda primero."); return
        path = filedialog.asksaveasfilename(
            title="Guardar resultados como CSV", defaultextension=".csv",
            filetypes=[("CSV","*.csv")], initialdir=self.prefs.get("last_dir")
        )
        if not path: return
        cols = ["codigo","nombre","barcode_interno","barcode_externo","empresa_id","__input"]
        df = self.last_results.copy()
        for c in cols:
            if c not in df.columns: df[c] = ""
        try:
            df.to_csv(path, index=False, encoding="utf-8")
            self.var_status.set(f"Resultados exportados a: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


# =====================================================
#  App principal
# =====================================================

class AutoBuildDBWindow(tk.Toplevel):
    """
    Ventana mínima con barra de progreso para crear la BASE DE DATOS
    en forma automática a partir del EXCEL de listado de artículos.
    """
    def __init__(self, master, listado_path: Path, on_done):
        super().__init__(master)
        self.title("Creando base de datos…")
        self.resizable(False, False)
        self.transient(master)
        self.listado_path = listado_path
        self.on_done = on_done  # callback Path|None

        self.grab_set()  # bloquear interacción con la ventana principal mientras trabaja

        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Preparando el buscador", style="Section.TLabel").pack(anchor="w")
        ttk.Label(frm, text=f"Creando la base de datos desde {listado_path.name}",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        frm_bar = ttk.Frame(frm)
        frm_bar.pack(fill="x", pady=(12, 4))

        self.progress = ttk.Progressbar(frm_bar, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)

        self.lbl_pct = ttk.Label(frm_bar, text="0%")
        self.lbl_pct.pack(side="left", padx=(8, 0))

        self.lbl_status = ttk.Label(frm, text="Preparando…", style="Muted.TLabel")
        self.lbl_status.pack(anchor="w", pady=(4, 0))

        # Ajuste tamaño aproximado
        self.update_idletasks()
        self.minsize(self.winfo_width(), self.winfo_height())

        # Centrar sobre la ventana principal en vez de dejar la posición
        # por defecto (arriba a la izquierda, asimétrica respecto al programa).
        try:
            x = master.winfo_rootx() + max(0, (master.winfo_width() - self.winfo_width()) // 2)
            y = master.winfo_rooty() + max(0, (master.winfo_height() - self.winfo_height()) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self._start_work()

    def _set_progress(self, value: int, text: str | None = None):
        value = max(0, min(100, int(value)))
        self.progress["value"] = value
        self.lbl_pct.config(text=f"{value}%")
        if text is not None:
            self.lbl_status.config(text=text)
        self.update_idletasks()

    def _start_work(self):
        def work():
            try:
                # Aplicamos la conversión activa del listado de Tivendo
                def cb(p, t):
                    self.after(0, lambda: self._set_progress(p, t or ""))

                self.after(0, lambda: self._set_progress(5, "Leyendo archivo de origen…"))
                df = read_export_any(self.listado_path, progress_cb=cb)
                out_df = transform_export(df, progress_cb=cb)
                empresas = load_empresas()
                lista_df = empresas_df_for_excel(empresas)

                # Ubicacion persistente (no se borra al cerrar el programa)
                # para poder reutilizarla en la proxima apertura si el
                # listado de origen no cambio.
                out_file = _base_db_cache_path(self.listado_path)

                self.after(0, lambda: self._set_progress(90, "Escribiendo archivo Excel…"))
                with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
                    out_df.to_excel(writer, sheet_name="BASE DE DATOS", index=False)
                    lista_df.to_excel(writer, sheet_name="LISTA", index=False)
                _remember_base_db_cache(self.listado_path)

                self.after(0, lambda: self._finish(True, out_file))
            except Exception as e:
                self.after(0, lambda: self._finish(False, e))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, ok: bool, result):
        if ok:
            self._set_progress(100, "Completado")
            # No mostramos messagebox para no molestar; vamos directo al buscador
            out_path = Path(result)
            try:
                self.on_done(out_path)
            finally:
                self.destroy()
        else:
            self._set_progress(0, "Error")
            messagebox.showerror("Error al crear base de datos", f"{result}")
            try:
                self.on_done(None)
            finally:
                self.destroy()

class RootApp(tk.Tk):
    def __init__(self):
        super().__init__()
        _configure_ui(self)
        # Restaurar tamaño/posición si existe en prefs
        prefs = load_prefs()
        geom = prefs.get("geometry")
        try:
            self.geometry(_reasonable_root_geometry(self, geom))
        except Exception:
            self.geometry(f"{DEFAULT_WINDOW_SIZE[0]}x{DEFAULT_WINDOW_SIZE[1]}")
        self.minsize(*MIN_WINDOW_SIZE)

        # Ruta global del EXCEL "Listado de artículos" que usarán los módulos
        self.listado_path: Optional[Path] = None
        self.packs_path: Optional[Path] = None
        self.packs_df = None
        self.packs_index = {}
        self.ranges_path: Optional[Path] = None
        self.ranges_df = None
        self.ranges_index = {}
        self.auto_last_load_text = ""

        ensure_empresas_seed_applied()  # Sincroniza empresas.json con la semilla y conserva agregados
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # La selección del LISTADO DE ARTÍCULOS ahora se hace desde el menú principal
        self._restore_last_auto_load()
        self._show_start()

    def _on_close(self):
        try:
            prefs = load_prefs()
            prefs["geometry"] = self.geometry()
            save_prefs(prefs)
        except Exception:
            pass
        self.destroy()

    def _restore_last_auto_load(self):
        """Restaura las rutas de la última carga automática sin bloquear el
        arranque: solo hace comprobaciones baratas (leer JSON, comprobar que
        los archivos existan). Los datos pesados de packs/precios NO se leen
        aca — se cargan mas adelante, recien cuando hacen falta de verdad
        (al apretar 'Buscar Código'), ver _ensure_packs_ranges_loaded.
        """
        data = load_auto_last_load()
        try:
            articulos_raw = str(data.get("articulos", "")).strip()
            packs_raw = str(data.get("packs", "")).strip()
            precios_raw = str(data.get("precios", "")).strip()
            articulos = Path(articulos_raw) if articulos_raw else None
            packs = Path(packs_raw) if packs_raw else None
            precios = Path(precios_raw) if precios_raw else None
            self.listado_path = articulos if articulos and articulos.is_file() else None
            self.packs_path = packs if packs and packs.is_file() else None
            self.ranges_path = precios if precios and precios.is_file() else None
            self.auto_last_load_text = article_download_label(self.listado_path) if self.listado_path else ""
        except Exception as exc:
            _auto_log(f"No se pudo restaurar última carga automática: {exc}")

    def _ensure_packs_ranges_loaded(self, on_ready):
        """Garantiza que packs/precios estén cargados en memoria antes de
        abrir el buscador, cargándolos junto con el LISTADO DE ARTICULOS en
        ese mismo momento (no automáticamente al abrir el programa). Si ya
        están cargados (o no hay ningún archivo asociado), llama a
        on_ready() de inmediato; si hace falta leerlos, lo hace en un hilo
        de fondo (con una ventanita de progreso) y solo entonces continúa."""
        needs_packs = self.packs_path is not None and not self.packs_index
        needs_ranges = self.ranges_path is not None and not self.ranges_index
        if not needs_packs and not needs_ranges:
            on_ready()
            return

        progress = tk.Toplevel(self)
        progress.title("Cargando datos")
        progress.configure(background=UI["background"])
        progress.resizable(False, False)
        progress.transient(self)
        progress.grab_set()
        frm = ttk.Frame(progress, padding=20)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Preparando datos complementarios", style="Section.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Cargando maestro de packs y lista de precios…",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        pb = ttk.Progressbar(frm, mode="indeterminate", length=320)
        pb.pack(fill="x", pady=(10, 0))
        pb.start(10)
        try:
            progress.update_idletasks()
            x = self.winfo_rootx() + max(0, (self.winfo_width() - progress.winfo_width()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - progress.winfo_height()) // 2)
            progress.geometry(f"+{x}+{y}")
        except Exception:
            pass

        def work():
            packs_result = ranges_result = None
            error = None
            try:
                if needs_packs:
                    packs_result = _load_cached_side_data(self.packs_path, PACKS_CACHE_PATH, PACKS_CACHE_META, load_packs_data)
                if needs_ranges:
                    ranges_result = _load_cached_side_data(self.ranges_path, RANGES_CACHE_PATH, RANGES_CACHE_META, load_price_ranges_data)
            except Exception as exc:
                error = exc

            def apply():
                try:
                    progress.destroy()
                except Exception:
                    pass
                if error is not None:
                    messagebox.showerror(
                        "Error al cargar packs/precios",
                        f"No se pudieron cargar los archivos asociados.\n\nDetalle: {error}",
                    )
                    on_ready()
                    return
                if packs_result is not None:
                    self.packs_df, self.packs_index = packs_result
                if ranges_result is not None:
                    self.ranges_df, self.ranges_index = ranges_result
                on_ready()

            self.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def _choose_listado_inicial(self):
        """Pide el Excel de LISTADO DE ARTÍCULOS y actualiza el estado de los botones."""
        prefs = load_prefs()
        path = filedialog.askopenfilename(
            title="Selecciona el EXCEL de LISTADO DE ARTÍCULOS",
            initialdir=prefs.get("last_dir"),
            filetypes=[("Excel", "*.xlsm *.xlsx *.xls"), ("Todos los archivos", "*.*")],
        )
        if path:
            try:
                p = Path(path)
                self.listado_path = p
                prefs["last_dir"] = str(p.parent)
                save_prefs(prefs)
            except Exception:
                self.listado_path = None
        else:
            self.listado_path = None
        if hasattr(self, "start_view") and self.start_view is not None:
            try:
                self.start_view.set_listado_cargado(self.listado_path is not None)
                self.auto_last_load_text = article_download_label(self.listado_path) if self.listado_path else ""
                self.start_view.set_auto_last_load(self.auto_last_load_text)
            except Exception:
                pass
        if self.listado_path is not None:
            messagebox.showinfo(
                "Listado cargado",
                f"Se cargó correctamente el LISTADO DE ARTICULOS.\n\nArchivo:\n{self.listado_path.name}"
            )

    def _ask_auto_credentials(self) -> Optional[tuple]:
        saved = load_auto_credentials()
        if saved.get("usuario") and saved.get("password"):
            # Ya quedaron guardadas de una carga anterior: no volver a preguntar
            # cada vez que se abre el programa.
            return saved["usuario"], saved["password"]

        dialog = tk.Toplevel(self)
        dialog.title("Carga automática")
        dialog.configure(background=UI["background"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Conectar con Tivendo", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Label(frame, text="Usuario:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        user_var = tk.StringVar(value=saved.get("usuario", ""))
        user_entry = ttk.Entry(frame, textvariable=user_var, width=38)
        user_entry.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Contraseña:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        pass_var = tk.StringVar(value=saved.get("password", ""))
        pass_entry = ttk.Entry(frame, textvariable=pass_var, width=34, show="*")
        pass_entry.grid(row=2, column=1, sticky="ew", pady=4)

        def toggle_password_visibility():
            pass_entry.config(show="" if pass_entry.cget("show") == "*" else "*")

        eye_btn = ttk.Button(frame, text="👁", width=3, command=toggle_password_visibility)
        eye_btn.grid(row=2, column=2, padx=(4, 0), pady=4)

        note = ttk.Label(
            frame,
            text="Estos datos se guardan localmente: la próxima vez no se volverán a pedir.",
            style="Muted.TLabel",
            wraplength=360,
        )
        note.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 12))

        result = {"value": None}

        def accept():
            usuario = user_var.get().strip()
            password = pass_var.get().strip()
            if not usuario or not password:
                messagebox.showwarning("Datos requeridos", "Ingresa usuario y contraseña.", parent=dialog)
                return
            result["value"] = (usuario, password)
            dialog.destroy()

        def cancel():
            result["value"] = None
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e")
        ttk.Button(buttons, text="Cancelar", command=cancel).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Cargar automáticamente", command=accept,
                   style="Primary.TButton").pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.bind("<Return>", lambda _e: accept())
        dialog.bind("<Escape>", lambda _e: cancel())
        frame.columnconfigure(1, weight=1)

        try:
            dialog.update_idletasks()
            x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
            dialog.geometry(f"+{x}+{y}")
        except Exception:
            pass

        user_entry.focus_set() if not user_var.get() else pass_entry.focus_set()
        self.wait_window(dialog)
        return result["value"]

    def _actualizar_solo_articulos(self, on_success):
        if getattr(self, "_auto_load_busy", False):
            messagebox.showinfo("Descarga en curso", "Espera a que termine la descarga actual.")
            return
        credentials = self._ask_auto_credentials()
        if not credentials:
            return
        usuario, password = credentials
        save_auto_credentials(usuario, password)
        self._auto_load_busy = True
        progress = tk.Toplevel(self)
        progress.title("Actualizar listado de artículos")
        progress.transient(self)
        progress.resizable(False, False)
        progress.protocol("WM_DELETE_WINDOW", lambda: None)
        progress.grab_set()
        box = ttk.Frame(progress, padding=20)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Actualizando el listado", style="Section.TLabel").pack(anchor="w")
        ttk.Label(box, text="El menú y este asistente usarán el mismo archivo.", style="Muted.TLabel").pack(anchor="w", pady=(4, 8))
        status = tk.StringVar(value="Preparando descarga…")
        ttk.Label(box, textvariable=status, wraplength=450).pack(anchor="w")
        bar = ttk.Progressbar(box, mode="indeterminate", length=440)
        bar.pack(fill="x", pady=(12, 0))
        bar.start(10)
        progress.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - progress.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - progress.winfo_height()) // 2)
        progress.geometry(f"+{x}+{y}")

        def worker():
            error = None
            result = None
            try:
                result = asyncio.run(auto_download_solo_articulos(
                    usuario, password, lambda text: self.after(0, lambda value=text: status.set(value))))
                save_auto_articles_load(result[0])
            except Exception as exc:
                error = exc
                _auto_log(f"Error al actualizar solo artículos: {exc}")

            def apply():
                self._auto_load_busy = False
                bar.stop()
                progress.destroy()
                if error is not None:
                    if isinstance(error, TivendoLoginError):
                        save_auto_credentials(usuario, "")
                    messagebox.showerror("No se actualizó el listado",
                        "Se conserva el listado que tenías cargado.\n\n" + str(error).split("Call log:", 1)[0].strip())
                    return
                self.listado_path = result[0]
                self.auto_last_load_text = article_download_label(self.listado_path)
                if self.start_view is not None:
                    self.start_view.set_listado_cargado(True)
                    self.start_view.set_auto_last_load(self.auto_last_load_text)
                on_success(*result)
            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()


    def _auto_load_articulos_packs(self):
        if getattr(self, "_auto_load_busy", False):
            messagebox.showinfo("Descarga en curso", "Espera a que termine la descarga actual.")
            return
        credentials = self._ask_auto_credentials()
        if not credentials:
            return
        usuario, password = credentials
        save_auto_credentials(usuario, password)

        progress = tk.Toplevel(self)
        self._auto_load_busy = True
        progress.protocol("WM_DELETE_WINDOW", lambda: None)
        progress.grab_set()
        progress.title("Carga automática")
        progress.configure(background=UI["background"])
        progress.transient(self)
        progress.resizable(False, False)
        box = ttk.Frame(progress, padding=20)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Descargando datos de Tivendo", style="Section.TLabel").pack(anchor="w")
        ttk.Label(box, text="Artículos, packs y precios", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        status_var = tk.StringVar(value="Preparando...")
        ttk.Label(box, textvariable=status_var, width=54, wraplength=420,
                  style="Muted.TLabel").pack(anchor="w", pady=(10, 8))
        pb = ttk.Progressbar(box, mode="indeterminate", length=360)
        pb.pack(fill="x")
        pb.start(10)
        try:
            progress.update_idletasks()
            x = self.winfo_rootx() + max(0, (self.winfo_width() - progress.winfo_width()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - progress.winfo_height()) // 2)
            progress.geometry(f"+{x}+{y}")
        except Exception:
            pass

        if hasattr(self, "start_view") and self.start_view is not None:
            try:
                self.start_view.btn_cargar_auto.config(state="disabled")
            except Exception:
                pass

        def set_status(text: str):
            try:
                self.after(0, lambda: status_var.set(text))
            except Exception:
                pass

        def worker():
            try:
                paths = asyncio.run(auto_download_articulos_packs_y_precios(usuario, password, set_status))
                set_status("Procesando maestro de packs...")
                packs_df, packs_index = _load_cached_side_data(Path(paths["packs"]), PACKS_CACHE_PATH, PACKS_CACHE_META, load_packs_data)
                set_status("Procesando lista de precios...")
                ranges_df, ranges_index = _load_cached_side_data(Path(paths["precios"]), RANGES_CACHE_PATH, RANGES_CACHE_META, load_price_ranges_data)
                result = {
                    "articulos": Path(paths["articulos"]),
                    "packs": Path(paths["packs"]),
                    "precios": Path(paths["precios"]),
                    "packs_df": packs_df,
                    "packs_index": packs_index,
                    "ranges_df": ranges_df,
                    "ranges_index": ranges_index,
                }

                def done():
                    self._auto_load_busy = False
                    try:
                        pb.stop()
                        progress.destroy()
                    except Exception:
                        pass

                    self.listado_path = result["articulos"]
                    self.packs_path = result["packs"]
                    self.packs_df = result["packs_df"]
                    self.packs_index = result["packs_index"]
                    self.ranges_path = result["precios"]
                    self.ranges_df = result["ranges_df"]
                    self.ranges_index = result["ranges_index"]
                    save_auto_last_load(self.listado_path, self.packs_path, self.ranges_path)
                    self.auto_last_load_text = article_download_label(self.listado_path)

                    prefs = load_prefs()
                    prefs["last_dir"] = str(AUTO_DOWNLOAD_DIR)
                    save_prefs(prefs)

                    if hasattr(self, "start_view") and self.start_view is not None:
                        try:
                            self.start_view.set_listado_cargado(True)
                            self.start_view.set_packs_cargado(True)
                            self.start_view.set_ranges_cargado(True)
                            self.start_view.set_auto_last_load(self.auto_last_load_text)
                            self.start_view.btn_cargar_auto.config(state="normal")
                        except Exception:
                            pass

                    messagebox.showinfo(
                        "Carga automática lista",
                        "Se descargaron y cargaron correctamente los archivos.\n\n"
                        f"Listado: {self.listado_path.name}\n"
                        f"Packs: {self.packs_path.name}\n"
                        f"Lista de precios: {self.ranges_path.name}\n"
                        f"Artículos con packs: {len(self.packs_index)}\n"
                        f"Artículos con rangos: {len(self.ranges_index)}",
                    )

                self.after(0, done)
            except Exception as exc:
                err = str(exc)
                _auto_log(f"Error en carga automática: {err}")
                # El registro conserva el detalle de Playwright; el cuadro de
                # diálogo solo muestra la causa, no cientos de líneas de reintentos.
                err = err.split("Call log:", 1)[0].strip()
                login_failed = isinstance(exc, TivendoLoginError)

                def fail():
                    self._auto_load_busy = False
                    try:
                        pb.stop()
                        progress.destroy()
                    except Exception:
                        pass
                    if hasattr(self, "start_view") and self.start_view is not None:
                        try:
                            self.start_view.btn_cargar_auto.config(state="normal")
                        except Exception:
                            pass
                    if login_failed:
                        # Borramos la contraseña guardada (mala) para que la
                        # proxima vez _ask_auto_credentials() vuelva a pedirla
                        # en vez de reintentar en silencio con la misma clave.
                        save_auto_credentials(usuario, "")
                        messagebox.showerror(
                            "Fallo al iniciar sesión",
                            "No se pudo iniciar sesión en Tivendo. Revisa la contraseña.\n\n"
                            "La próxima vez que uses 'Cargar automático' se te pedirá que la ingreses de nuevo.",
                        )
                    else:
                        messagebox.showerror(
                            "Error en carga automática",
                            "No se pudo completar la carga automática.\n"
                            "No se cambió lo que ya estaba cargado.\n\n"
                            f"Detalle: {err}",
                        )

                self.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()
        self.start_view = None  # evitar referencia colgante a widget destruido

    def _choose_packs_inicial(self):
        """Pide el Excel MAESTRO DE PACKS y lo deja disponible para el buscador."""
        prefs = load_prefs()
        path = filedialog.askopenfilename(
            title="Selecciona el EXCEL MAESTRO DE PACKS",
            initialdir=prefs.get("last_dir"),
            filetypes=[("Excel", "*.xlsm *.xlsx *.xls"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return

        try:
            p = Path(path)
            packs_df, packs_index = _load_cached_side_data(p, PACKS_CACHE_PATH, PACKS_CACHE_META, load_packs_data)
            self.packs_path = p
            self.packs_df = packs_df
            self.packs_index = packs_index
            prefs["last_dir"] = str(p.parent)
            save_prefs(prefs)
        except Exception as e:
            self.packs_path = None
            self.packs_df = None
            self.packs_index = {}
            messagebox.showerror("Error al cargar maestro de packs", str(e))
            return

        if hasattr(self, "start_view") and self.start_view is not None:
            try:
                self.start_view.set_packs_cargado(True)
            except Exception:
                pass

        messagebox.showinfo(
            "Maestro de packs cargado",
            f"Se cargo correctamente el MAESTRO DE PACKS.\n\n"
            f"Archivo: {self.packs_path.name}\n"
            f"Articulos con packs: {len(self.packs_index)}",
        )

    def _choose_ranges_inicial(self):
        """Pide el Excel/HTML LISTA DE PRECIOS y deja rangos disponibles."""
        prefs = load_prefs()
        path = filedialog.askopenfilename(
            title="Selecciona la LISTA DE PRECIOS",
            initialdir=prefs.get("last_dir"),
            filetypes=[("Excel/HTML", "*.xls *.xlsx *.html *.htm"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return

        try:
            p = Path(path)
            ranges_df, ranges_index = _load_cached_side_data(p, RANGES_CACHE_PATH, RANGES_CACHE_META, load_price_ranges_data)
            self.ranges_path = p
            self.ranges_df = ranges_df
            self.ranges_index = ranges_index
            prefs["last_dir"] = str(p.parent)
            save_prefs(prefs)
        except Exception as e:
            self.ranges_path = None
            self.ranges_df = None
            self.ranges_index = {}
            messagebox.showerror("Error al cargar lista de precios", str(e))
            return

        if hasattr(self, "start_view") and self.start_view is not None:
            try:
                self.start_view.set_ranges_cargado(True)
            except Exception:
                pass

        messagebox.showinfo(
            "Lista de precios cargada",
            f"Se cargo correctamente la LISTA DE PRECIOS.\n\n"
            f"Archivo: {self.ranges_path.name}\n"
            f"Articulos con rangos: {len(self.ranges_index)}",
        )

    def _show_start(self):
        self._clear()
        self.start_view = StartView(
            self,
            on_choose_db=self._choose_db_flow,
            on_manage_prov=self._manage_prov_flow,
            on_open_tivendo=self._tivendo_flow,
            on_open_ingreso_masivo=self._ingreso_masivo_flow,
            on_load_listado=self._choose_listado_inicial,
            on_load_packs=self._choose_packs_inicial,
            on_load_ranges=self._choose_ranges_inicial,
            on_auto_load=self._auto_load_articulos_packs,
            listado_cargado=self.listado_path is not None,
            # Refleja si hay un archivo asociado (se cargará al abrir el
            # buscador), no si ya está leído en memoria en este instante.
            packs_cargado=bool(self.packs_path),
            ranges_cargado=bool(self.ranges_path),
            auto_last_load_text=self.auto_last_load_text,
        )

    def _require_listado(self) -> bool:
        """Devuelve True si hay listado cargado; muestra aviso y devuelve False si no."""
        if not self.listado_path:
            messagebox.showwarning(
                "Listado no cargado",
                "Primero debes seleccionar el Excel LISTADO DE ARTÍCULOS al inicio.",
            )
            return False
        return True

    def _choose_db_flow(self):
        """Crear automáticamente la BASE DE DATOS desde el listado y abrir el buscador.

        Optimización: la BASE DE DATOS generada queda cacheada de forma
        persistente (no solo durante esta sesión). Si el LISTADO DE
        ARTICULOS no cambió desde la última vez que se generó, se reutiliza
        en vez de volver a crearla; si cambió, se regenera automáticamente.

        Los packs/precios de la última carga automática (si hay) se cargan
        junto con el listado en este mismo paso, no antes.
        """
        if not self._require_listado():
            return

        def _open_search():
            candidate = _find_fresh_base_db_cache(self.listado_path)
            if candidate is not None:
                try:
                    self._show_search(candidate)
                    return
                except Exception:
                    # Si algo falla, seguimos con el flujo estándar de creación
                    pass

            def _done(db_path: Optional[Path]):
                # Callback que se ejecuta cuando termina la creación
                if db_path is None:
                    return
                self._show_search(db_path)

            # Abre una ventanita con barra de progreso y lanza el proceso en segundo plano
            AutoBuildDBWindow(self, self.listado_path, _done)

        self._ensure_packs_ranges_loaded(_open_search)

    def _manage_prov_flow(self):
        self._clear()
        ProvidersView(self, go_home_cb=self._show_start)

    def _tivendo_flow(self):
        # Abre la herramienta de cambios masivos de precios en la ventana principal
        try:
            self._clear()
            TivendoWindow(self, listado_path=self.listado_path, go_home_cb=self._show_start)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la herramienta de Tivendo.\n{e}")

    def _ingreso_masivo_flow(self):
        # Abre la herramienta de ingreso masivo de artículos en la ventana principal
        try:
            self._clear()
            TivendoIngresoMasivoArticulosWindow(self, catalogo_path=self.listado_path, go_home_cb=self._show_start)
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"No se pudo abrir la herramienta de ingreso masivo de artículos.\n{e}",
            )
    def _show_search(self, db_path: Optional[Path]):
        self._clear()
        SearchView(
            self,
            go_home_cb=self._show_start,
            initial_db_path=db_path,
            packs_path=self.packs_path,
            ranges_path=self.ranges_path,
        )

def is_ident_header(x: str) -> bool:
    x = _norm_lc(x)
    if not x or x.startswith("unnamed"): return False
    if "barra" in x: return False
    return x in {"código","codigo","identificador","id"} or x.startswith("cod") or "identif" in x

def is_barra_interna_header(x: str) -> bool:
    x = _norm_lc(x)
    if not x or x.startswith("unnamed"): return False
    return ("barra" in x and "intern" in x) or x in {"codigo de barra interno","código de barra interno"}

def is_nombre_header(x: str) -> bool:
    x = _norm_lc(x)
    if not x or x.startswith("unnamed"): return False
    return "nombre" in x or "descrip" in x


def clean_price(s: str) -> str:
    if s is None: return ""
    s = str(s).strip().replace("$","").replace(" ","")
    if _RE_PRICE_DEC.search(s):
        dec = s[-3]
        s = _RE_PRICE_SEP.sub("", s[:-3]) + dec + s[-2:]
    else:
        s = _RE_PRICE_SEP.sub("", s)
    return s


def normalizar_cantidad_rango(texto):
    """Una cantidad por campo, con coma o punto decimal, sin separador de miles."""
    text = str(texto).strip()
    if not re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", text):
        raise ValueError("ingresa una cantidad, por ejemplo 1, 1000 o 0,001")
    value = Decimal(text.replace(",", "."))
    if value <= 0 or value > 1000:
        raise ValueError("la cantidad debe ser mayor que cero y como máximo 1000")
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def preparar_fila_precio(values, con_rangos=True, con_rango2=False):
    """Valida una fila sin UI y devuelve las columnas originales de la importación."""
    code, initial1, final1, price1, initial2, final2, price2 = (str(value).strip() for value in values)
    result = {"CodigoBarraInterno": code, "Precio1": clean_price(price1),
              "RangoInicial1": "1", "RangoFinal1": "1000",
              "Precio2": "", "RangoInicial2": "", "RangoFinal2": ""}
    errors = {}
    if not code:
        errors[0] = "falta barra interna"
    if not re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", result["Precio1"]):
        errors[3] = "revisa el precio 1"
    if con_rangos:
        for index, column, value, label in ((1, "RangoInicial1", initial1, "rango inicial 1"),
                (2, "RangoFinal1", final1, "rango final 1")):
            try:
                result[column] = normalizar_cantidad_rango(value)
            except ValueError as exc:
                errors[index] = f"{label}: {exc}"
        if 1 not in errors and 2 not in errors and Decimal(result["RangoFinal1"]) < Decimal(result["RangoInicial1"]):
            errors[2] = "el rango final 1 no puede ser menor que el inicial 1"
    if con_rango2 and (initial2 or final2 or price2):
        for index, column, value, label in ((4, "RangoInicial2", initial2, "rango inicial 2"),
                (5, "RangoFinal2", final2, "rango final 2")):
            try:
                result[column] = normalizar_cantidad_rango(value)
            except ValueError as exc:
                errors[index] = f"{label}: {exc}"
        if 4 not in errors and 5 not in errors:
            if Decimal(result["RangoFinal2"]) < Decimal(result["RangoInicial2"]):
                errors[5] = "el rango final 2 no puede ser menor que el inicial 2"
            if 1 not in errors and 2 not in errors and Decimal(result["RangoInicial2"]) <= Decimal(result["RangoFinal1"]):
                errors[4] = "el rango inicial 2 debe empezar después del final del rango 1"
        result["Precio2"] = clean_price(price2)
        if not re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", result["Precio2"]):
            errors[6] = "falta un precio 2 válido para el segundo rango"
    return result, errors


def parsear_tabla_precios(texto):
    """Barra, inicial/final/precio de cada rango; admite 2, 4 o 7 columnas."""
    rows = list(csv.reader(io.StringIO(texto), delimiter="\t"))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    headers = {"barra", "barra interna", "codigo", "codigo barra interno", "codigo de barra interno", "codigo de barras", "codigobarrainterno"}
    if rows and _normalize_text(rows[0][0]) in headers:
        rows.pop(0)
    if not rows:
        raise ValueError("Copia primero las filas de Excel que quieres pegar.")
    width = max(map(len, rows))
    if width not in (2, 4, 7) or any("\n" in cell or "\r" in cell for row in rows for cell in row):
        raise ValueError("Copia 2, 4 o 7 columnas, con un producto por fila y sin saltos dentro de las celdas.")
    rows = [row + [""] * (width - len(row)) for row in rows]
    return rows

class TivendoWindow(ttk.Frame):
    def __init__(self, master, listado_path: Optional[Path] = None, go_home_cb=None):
        super().__init__(master)
        self.master.title(f"Tivendo - Cambios masivos de precios ({APP_VERSION})")
        self.pack(fill="both", expand=True)
        self.go_home_cb = go_home_cb

        top = ttk.Frame(self, padding=(16, 12, 16, 4))
        top.pack(fill="x")
        # Botón para volver al menú principal sin usar métodos adicionales
        ttk.Button(
            top,
            text="← Inicio",
            command=lambda: (self.destroy(), self.go_home_cb() if callable(self.go_home_cb) else None),
        ).pack(side="left")
        ttk.Label(top, text="Cambios masivos de precios", style="Title.TLabel").pack(side="left", padx=16)

        self.path_listado = None
        self.df_map = None
        self.df_preview = None     # DataFrame completo
        self.df_view = None        # DataFrame filtrado (None = sin filtro)
        self._df_preview_norm = {} # columnas normalizadas para filtro rápido
        self._modo_ejemplo_precios = False
        self._listado_load_job = 0
        self._listado_cargando = False
        self._rangos_index = {}
        self._rangos_fuente = "Rangos: sin archivo guardado; compruébalos en Tivendo."

        self.enable_r2 = tk.BooleanVar(value=False)
        self.ingresar_rangos = tk.BooleanVar(value=True)
        self.export_only_valid = tk.BooleanVar(value=True)

        self._build_stepA_select_listado()
        self._build_stepB_paste()
        self._build_stepC_preview()

        # Si ya tenemos un listado entregado desde la app principal, lo cargamos automáticamente
        # PERO en segundo plano para que la ventana se abra al instante (mejor percepción de velocidad).
        if listado_path is not None:
            try:
                self.path_listado = Path(listado_path)
            except Exception:
                self.path_listado = None

        self._show(self.stepA)

        # Carga diferida del listado (no bloquea la UI)
        if self.path_listado is not None:
            try:
                self._start_async_listado_load(self.path_listado)
            except Exception:
                pass

    def _build_stepA_select_listado(self):
        f = self.stepA = ttk.Frame(self, padding=16)
        _wizard_steps(f, 1, ("Listado", "Pegar precios", "Revisar y exportar"))
        ttk.Label(
            f,
            text="Cambia precios de productos que ya existen",
            style="Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            f,
            text="1. Confirma el listado.  2. Pega barras y precios nuevos.  3. Revisa y guarda el Excel para Tivendo.",
            foreground="#444",
        ).pack(anchor="w", pady=(4, 12))

        article_box = ttk.Frame(f, style="Card.TFrame", padding=10)
        article_box.pack(fill="x", pady=(4, 8))
        article_box.columnconfigure(0, weight=1)
        ttk.Label(article_box, text="Artículos", style="Card.Section.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_listado = ttk.Label(
            article_box,
            text="Listado aún no cargado",
            style="Card.Muted.TLabel", wraplength=850,
        )
        self.lbl_listado.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.lbl_archivo_articulos = ttk.Label(article_box, text="Todavía no hay un listado cargado.",
            style="Card.Muted.TLabel", wraplength=850)
        self.lbl_archivo_articulos.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.lbl_fecha_articulos = ttk.Label(article_box, text="", style="Card.Muted.TLabel")
        self.lbl_fecha_articulos.grid(row=3, column=0, sticky="w", pady=(4, 0))
        article_controls = ttk.Frame(article_box, style="Card.TFrame")
        article_controls.grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Button(article_controls, text="Actualizar artículos", command=self._actualizar_listado_precios,
            style="Primary.TButton").pack(side="left")

        ttk.Label(f, text="Usa el listado guardado. Actualiza artículos solo cuando lo necesites.",
            style="Muted.TLabel").pack(anchor="w", pady=(4, 6))

        # Botón para pasar al siguiente paso (pegar los datos)
        self.btn_to_paste = ttk.Button(
            f,
            text="Continuar: pegar precios →", style="Primary.TButton",
            state="disabled",
            command=lambda: self._show(self.stepB),
        )
        self.btn_to_paste.pack(side="bottom", anchor="e", pady=12)
        self.btn_to_paste.pack_configure(before=f.winfo_children()[0])

    def _actualizar_listado_precios(self):
        self.master._actualizar_solo_articulos(lambda ruta, catalogo: self._start_async_listado_load(ruta))


    def _actualizar_estado_continuar(self):
        ready = self.df_map is not None and not self._listado_cargando
        self.btn_to_paste.config(state="normal" if ready else "disabled")
        if hasattr(self, "btn_revisar_precios"):
            self._actualizar_pegado_precios()


    def _start_async_listado_load(self, path: Path):
        """Carga el listado en un hilo para no congelar la apertura de la ventana."""
        self._listado_load_job += 1
        job = self._listado_load_job
        self._listado_cargando = True
        self._actualizar_estado_continuar()
        ranges_path = getattr(self.master, "ranges_path", None)
        # UI: mostrar estado cargando + progressbar si existe
        try:
            self.lbl_listado.config(text=f"Cargando listado: {path.name} ...")
        except Exception:
            pass

        # Asegurar progressbar (indeterminado) en Step A si existe, o crear uno liviano
        try:
            if not hasattr(self, "_pb_listado"):
                self._pb_listado = ttk.Progressbar(self.stepA, mode="indeterminate")
            self._pb_listado.pack(anchor="w", fill="x", pady=(4, 0))
            self._pb_listado.start(10)
        except Exception:
            pass

        # Deshabilitar botón continuar mientras carga
        try:
            self.btn_to_paste.config(state="disabled")
        except Exception:
            pass

        def worker():
            err = None
            result = None
            ranges_index, ranges_label = rangos_guardados_para_revision(ranges_path)
            try:
                result = self._parse_listado_for_map(path)
            except Exception as e:
                err = str(e)

            def apply():
                # detener progress
                if not self.winfo_exists() or job != self._listado_load_job:
                    return
                try:
                    if hasattr(self, "_pb_listado"):
                        self._pb_listado.stop()
                        self._pb_listado.pack_forget()
                except Exception:
                    pass

                self._listado_cargando = False
                if err:
                    self._actualizar_estado_continuar()
                    try:
                        messagebox.showerror("Error", f"No se pudo cargar el listado.\n{err}")
                    except Exception:
                        pass
                    return

                try:
                    df_map, label_text = result
                    self.path_listado = Path(path)
                    self.df_map = df_map
                    self._rangos_index, self._rangos_fuente = ranges_index, ranges_label
                    self.lbl_rangos_fuente.config(text=ranges_label)
                    status, _, filename = label_text.partition("\nArchivo:")
                    self.lbl_listado.config(text=status, style="Card.Success.TLabel")
                    self.lbl_archivo_articulos.config(text=f"Archivo:{filename}" if filename else f"Archivo: {Path(path).name}")
                    self.lbl_fecha_articulos.config(text=f"Última descarga de artículos: {article_download_label(path)}")
                    self._actualizar_estado_continuar()
                    # Si estábamos en Paso 2, igual queda listo para usar
                except Exception:
                    pass

            try:
                self.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _parse_listado_for_map(self, path: Path):
        """Lee el Excel UNA sola vez y construye df_map. No toca la UI (apto para hilo)."""
        df_raw = pd.read_excel(path, header=None, dtype=str)

        header_row = None
        for r, row_data in enumerate(df_raw.head(12).itertuples(index=False, name=None)):
            vals = [str(v) if pd.notna(v) else "" for v in row_data]
            if any(is_ident_header(v) for v in vals) and any(is_barra_interna_header(v) for v in vals):
                header_row = r
                break
        if header_row is None:
            raise ValueError("No se localizaron encabezados de 'Código' y 'Código barra interno' en las primeras filas.")

        # Reutilizar df_raw: renombrar con la fila de encabezado encontrada
        df = df_raw.iloc[header_row:].copy()
        df.columns = df.iloc[0]          # primera fila del slice es el encabezado
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = [str(c) for c in df.columns]  # asegurar str

        cols = list(df.columns)
        ident_col  = next((c for c in cols if is_ident_header(c)), None)
        barra_col  = next((c for c in cols if is_barra_interna_header(c)), None)
        nombre_col = next((c for c in cols if is_nombre_header(c)), None) or ident_col
        if not (ident_col and barra_col):
            raise ValueError(f"No se identificaron columnas válidas. Detectadas: {cols}")

        df_map = df[[ident_col, barra_col, nombre_col]].copy()
        df_map.columns = ["Identificador", "CodigoBarraInterno", "Nombre"]
        df_map = df_map.fillna("").astype(str).apply(lambda s: s.str.strip())
        df_map = df_map[df_map["Identificador"].ne("") & df_map["CodigoBarraInterno"].ne("")]

        label_text = f"Listado comprobado · {len(df_map):,} artículos con barra interna\nArchivo: {path.name}"
        return df_map, label_text

    def _build_stepB_paste(self):
        f = self.stepB = ttk.Frame(self, padding=16)
        _wizard_steps(f, 2, ("Listado", "Pegar precios", "Revisar y exportar"))
        ttk.Label(f, text="Pega tus columnas de Excel", style="Section.TLabel").pack(anchor="w")
        ttk.Label(f, text="Primero pega las barras y después los precios. Cada línea corresponde al mismo producto.",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 8))
        tools = ttk.Frame(f)
        tools.pack(fill="x", pady=(0, 6))
        ttk.Label(tools, text="Rango 1 habilitado", style="Muted.TLabel").pack(side="left")
        self.btn_segundo_rango = ttk.Button(tools, text="+ Segundo rango y precio", command=self._alternar_segundo_rango)
        self.btn_segundo_rango.pack(side="left", padx=8)
        self.btn_pegar_precios = ttk.Button(tools, text="Pegar tabla de Excel", command=self._pegar_tabla_precios)
        self.btn_pegar_precios.pack(side="right")
        ttk.Button(tools, text="Ejemplo", command=self._ejemplo_precios).pack(side="right", padx=6)
        self.lbl_pegado_precios = ttk.Label(f, text="Pega una columna completa en cada cuadro.", style="Muted.TLabel", wraplength=900)
        self.lbl_pegado_precios.pack(anchor="w", pady=(0, 6))

        area = ttk.Frame(f)
        area.pack(fill="y", expand=True, anchor="n")
        area.rowconfigure(0, weight=1)
        self._area_columnas_precios = area
        self._campos_columnas_precios = []
        self._sincronizando_columnas_precios = False
        fields = (("txt_cod", "Barras internas", 24), ("txt_ri1", "Rango inicial 1", 8),
                  ("txt_rf1", "Rango final 1", 8), ("txt_prec", "Precios 1", 14),
                  ("txt_ri2", "Rango inicial 2", 8), ("txt_rf2", "Rango final 2", 8),
                  ("txt_prec2", "Precios 2", 14))
        for index, (attribute, title, width) in enumerate(fields):
            shell = ttk.Frame(area)
            shell.grid(row=0, column=index, sticky="nsew", padx=(0, 6))
            shell.rowconfigure(1, weight=1)
            shell.rowconfigure(0, minsize=36)
            shell.columnconfigure(0, weight=1)
            ttk.Label(shell, text=title, style="Muted.TLabel", wraplength=86 if width == 8 else 180 if index == 0 else 120).grid(row=0, column=0, sticky="sw")
            text = tk.Text(shell, wrap="none", width=width, height=12, undo=True,
                           font=("Segoe UI", 10), background=UI["surface"], foreground=UI["ink"],
                           insertbackground=UI["ink"], selectbackground=UI["selected"],
                           relief="flat", borderwidth=0, highlightthickness=1,
                           highlightbackground=UI["border"], highlightcolor=UI["primary"], padx=5, pady=5)
            text.grid(row=1, column=0, sticky="nsew")
            text.configure(yscrollcommand=lambda first, last, i=index: self._al_desplazar_columna_precio(i, first, last))
            text.bind("<<Modified>>", self._al_editar_precios)
            text.bind("<Control-v>", lambda event, i=index: self._pegar_columna_precio(i))
            text.bind("<Control-V>", lambda event, i=index: self._pegar_columna_precio(i))
            text.bind("<Control-a>", lambda event: (event.widget.tag_add("sel", "1.0", "end-1c"), "break")[-1])
            text.bind("<Control-A>", lambda event: (event.widget.tag_add("sel", "1.0", "end-1c"), "break")[-1])
            text.tag_configure("error_dato", background="#FDEBEC")
            setattr(self, attribute, text)
            self._campos_columnas_precios.append(shell)
        self._scroll_columnas_precios = ttk.Scrollbar(area, orient="vertical", command=self._desplazar_columnas_precios)
        self._scroll_columnas_precios.grid(row=0, column=7, sticky="ns", pady=(36, 0))
        ttk.Label(f, text="Ctrl+V reemplaza solo la columna elegida. Las cantidades admiten hasta 1000.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        bottom = ttk.Frame(f)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="← Volver", command=lambda: self._show(self.stepA)).pack(side="left")
        ttk.Button(bottom, text="Limpiar columnas", command=self._limpiar_pegado_precios).pack(side="left", padx=6)
        self.btn_revisar_precios = ttk.Button(bottom, text="Comprobar y revisar precios →", command=self._build_preview_from_paste,
                                               style="Primary.TButton", state="disabled")
        self.btn_revisar_precios.pack(side="right")
        area.pack_forget()
        bottom.pack_forget()
        bottom.pack(side="bottom", fill="x", pady=(10, 0))
        area.pack(fill="y", expand=True, anchor="n")
        self._configurar_columnas_pegado()

    def _textos_precios(self):
        return self.txt_cod, self.txt_ri1, self.txt_rf1, self.txt_prec, self.txt_ri2, self.txt_rf2, self.txt_prec2

    def _indices_columnas_precios(self):
        indices = [0, 1, 2, 3]
        return indices + [4, 5, 6] if self.enable_r2.get() else indices

    def _configurar_columnas_pegado(self):
        self.ingresar_rangos.set(True)
        active = self._indices_columnas_precios()
        for index, shell in enumerate(self._campos_columnas_precios):
            if index in active:
                shell.grid()
            else:
                shell.grid_remove()
            # El bloque mantiene un ancho moderado y centrado; el alto usa el espacio disponible.
            self._area_columnas_precios.columnconfigure(index, weight=0)
        self.btn_segundo_rango.config(text="− Quitar segundo rango" if self.enable_r2.get() else "+ Segundo rango y precio")
        self.btn_pegar_precios.config(text=f"Pegar tabla de {len(active)} columnas")
        self._actualizar_pegado_precios()

    def _desplazar_columnas_precios(self, *args):
        self._sincronizando_columnas_precios = True
        try:
            self.txt_cod.yview(*args)
            line = self.txt_cod.index("@0,0")
            for index in self._indices_columnas_precios()[1:]:
                self._textos_precios()[index].yview(line)
        finally:
            self._sincronizando_columnas_precios = False
        first, last = self.txt_cod.yview()
        self._scroll_columnas_precios.set(first, last)

    def _al_desplazar_columna_precio(self, index, first, last):
        if getattr(self, "_sincronizando_columnas_precios", False) or not hasattr(self, "_scroll_columnas_precios"):
            return
        if index not in self._indices_columnas_precios():
            return
        self._sincronizando_columnas_precios = True
        try:
            self._scroll_columnas_precios.set(first, last)
            line = self._textos_precios()[index].index("@0,0")
            for other in self._indices_columnas_precios():
                if other != index:
                    self._textos_precios()[other].yview(line)
        finally:
            self._sincronizando_columnas_precios = False

    def _rellenar_rango1_por_defecto(self):
        if not self.ingresar_rangos.get() or self.txt_ri1.get("1.0", "end-1c").strip() or self.txt_rf1.get("1.0", "end-1c").strip():
            return
        codes = self.txt_cod.get("1.0", "end-1c").splitlines()
        for widget, value in ((self.txt_ri1, "1"), (self.txt_rf1, "1000")):
            widget.insert("1.0", "\n".join(value if code.strip() else "" for code in codes))

    def _alternar_segundo_rango(self):
        self.enable_r2.set(not self.enable_r2.get())
        if self.enable_r2.get():
            self.ingresar_rangos.set(True)
            self._rellenar_rango1_por_defecto()
        self._toggle_r2()

    def _cambiar_ingreso_rangos(self):
        self.ingresar_rangos.set(True)
        self._rellenar_rango1_por_defecto()
        self._toggle_r2()

    def _pegar_columna_precio(self, index):
        try:
            text = self.clipboard_get()
            raw = list(csv.reader(io.StringIO(text), delimiter="\t"))
            if any(any(cell.strip() for cell in row[1:]) for row in raw):
                if index == 0:
                    self._pegar_tabla_precios()
                else:
                    messagebox.showwarning("Pega una columna", "En este cuadro pega una sola columna de Excel. Para pegar una tabla completa usa el botón de arriba.")
                return "break"
            values = [row[0].strip() if row else "" for row in raw]
            headers = ({"barra", "barras", "barra interna", "barras internas", "codigo barra interno", "codigobarrainterno", "codigo"},
                       {"rango inicial 1", "rangoinicial1"}, {"rango final 1", "rangofinal1"},
                       {"precio", "precios", "precio 1", "precio1"}, {"rango inicial 2", "rangoinicial2"},
                       {"rango final 2", "rangofinal2"}, {"precio 2", "precio2", "precios 2"})
            if values and _normalize_text(values[0]) in headers[index]:
                values.pop(0)
            while values and not values[-1]:
                values.pop()
            if any("\n" in value or "\r" in value for value in values):
                raise ValueError("Cada celda debe ocupar una sola fila.")
            widget = self._textos_precios()[index]
            widget.delete("1.0", "end")
            widget.insert("1.0", "\n".join(values))
            widget.see("1.0")
            if index == 0:
                self._rellenar_rango1_por_defecto()
            self._actualizar_pegado_precios()
        except (tk.TclError, ValueError, csv.Error) as exc:
            messagebox.showwarning("No se pudo pegar", f"Copia la columna desde Excel y vuelve a pegarla.\n{exc}")
        return "break"

    def _leer_filas_precios(self):
        columns = [widget.get("1.0", "end-1c").splitlines() for widget in self._textos_precios()]
        if not self.enable_r2.get():
            columns[4] = columns[5] = columns[6] = []
        rows = []
        for index in range(max(map(len, columns), default=0)):
            values = [column[index].strip() if index < len(column) else "" for column in columns]
            if any(values):
                rows.append((index + 1, values))
        return rows

    def _read_pasted_lists(self):
        rows = self._leer_filas_precios()
        return [values[0] for _, values in rows], [clean_price(values[3]) for _, values in rows]

    def _al_editar_precios(self, event):
        if event.widget.edit_modified():
            event.widget.edit_modified(False)
            self._actualizar_pegado_precios()

    def _actualizar_pegado_precios(self):
        # Igual altura lógica para que una columna corta conserve sus filas vacías
        # al desplazar la vista junto a las demás, sin correr precios de producto.
        active = [self._textos_precios()[index] for index in self._indices_columnas_precios()]
        height = max((len(widget.get("1.0", "end-1c").splitlines()) for widget in active), default=0)
        for widget in active:
            missing = height - (widget.get("1.0", "end-1c").count("\n") + 1)
            if missing > 0:
                widget.insert("end-1c", "\n" * missing)
                widget.edit_modified(False)
        rows = self._leer_filas_precios()
        valid = bool(rows)
        first_error = ""
        widgets = self._textos_precios()
        for widget in widgets:
            widget.tag_remove("error_dato", "1.0", "end")
        for line, values in rows:
            _, errors = preparar_fila_precio(values, True, self.enable_r2.get())
            if errors:
                valid = False
            for index, detail in errors.items():
                widgets[index].tag_add("error_dato", f"{line}.0", f"{line}.end+1c")
                if not first_error:
                    first_error = f"Fila {line}: {detail}."
        count = len(rows)
        text = ("PRÁCTICA · " if self._modo_ejemplo_precios else "")
        text += f"{count} producto(s) · " + ("Listo para comprobar en el listado." if valid else first_error or "Completa una barra, su rango y su precio por fila.")
        self.lbl_pegado_precios.config(text=text, style="Success.TLabel" if valid else "Muted.TLabel" if not count else "Warning.TLabel")
        self.btn_revisar_precios.config(state="normal" if valid and self.df_map is not None
            and not self._listado_cargando else "disabled")
        return valid

    def _limpiar_pegado_precios(self):
        self._modo_ejemplo_precios = False
        for widget in self._textos_precios():
            widget.delete("1.0", "end")
        self._actualizar_pegado_precios()

    def _escribir_tabla_precios(self, rows, ejemplo=False):
        width = max(map(len, rows), default=4)
        if width not in (2, 4, 7):
            raise ValueError("La tabla debe tener 2, 4 o 7 columnas.")
        self._modo_ejemplo_precios = ejemplo
        self.ingresar_rangos.set(True)
        self.enable_r2.set(width == 7)
        normalized = []
        for row in rows:
            row = list(row) + [""] * (width - len(row))
            normalized.append([row[0], "1" if row[0].strip() else "", "1000" if row[0].strip() else "", row[1], "", "", ""]
                              if width == 2 else row + [""] * (7 - width))
        for index, widget in enumerate(self._textos_precios()):
            widget.delete("1.0", "end")
            widget.insert("1.0", "\n".join(row[index] for row in normalized))
        self._toggle_r2()

    def _pegar_excel_en_barras(self, event=None):
        try:
            if "\t" in self.clipboard_get():
                self._pegar_tabla_precios()
                return "break"
        except tk.TclError:
            pass

    def _pegar_tabla_precios(self):
        try:
            rows = parsear_tabla_precios(self.clipboard_get())
            if any(widget.get("1.0", "end-1c").strip() for widget in self._textos_precios()):
                if not messagebox.askyesno("Reemplazar datos", "¿Reemplazar los códigos y precios pegados con la tabla copiada?"):
                    return
            self._escribir_tabla_precios(rows)
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Cómo pegar desde Excel", f"{exc}\n\nBarra | Rango inicial 1 | Rango final 1 | Precio 1\nCon segundo rango: añade Rango inicial 2 | Rango final 2 | Precio 2.\nTambién se admite Barra | Precio.")

    def _ejemplo_precios(self):
        if self.df_map is None or self.df_map.empty:
            messagebox.showinfo("Espera al listado", "Primero deja que termine de cargarse el listado.")
            return
        if any(widget.get("1.0", "end-1c").strip() for widget in self._textos_precios()):
            if not messagebox.askyesno("Probar ejemplo", "¿Reemplazar los datos pegados por precios de práctica?"):
                return
        sample = self.df_map[self.df_map["CodigoBarraInterno"].ne("") &
                             ~self.df_map["Nombre"].map(_normalize_text).str.match(r"^no\s+disponible\b")].head(2)
        rows = [[row.CodigoBarraInterno, "1", "1", "590", "2", "3", "450"]
                if self.enable_r2.get() else [row.CodigoBarraInterno, "1", "1000", "1290"]
                if self.ingresar_rangos.get() else [row.CodigoBarraInterno, "1290"] for row in sample.itertuples()]
        self._escribir_tabla_precios(rows, ejemplo=True)

    def _build_preview_from_paste(self):
        if self.df_map is None:
            messagebox.showwarning("Listado requerido", "Primero selecciona el Listado de artículos."); return
        if not self._actualizar_pegado_precios():
            messagebox.showwarning("Revisa las filas", "Corrige las celdas marcadas: barra, rango y precio deben corresponder a la misma fila.")
            return
        records = [preparar_fila_precio(values, True, self.enable_r2.get())[0]
                   for _, values in self._leer_filas_precios()]
        df_in = pd.DataFrame(records)
        df = df_in.merge(self.df_map, on="CodigoBarraInterno", how="left")

        self.df_preview = df
        # Pre-computar columnas normalizadas para que _apply_filter sea O(1) por keystroke
        self._df_preview_norm = {
            "Identificador":     df["Identificador"].astype(str).map(_normalize_text) if "Identificador" in df.columns else pd.Series(dtype=str),
            "Nombre":            df["Nombre"].astype(str).map(_normalize_text)         if "Nombre"        in df.columns else pd.Series(dtype=str),
            "CodigoBarraInterno":df["CodigoBarraInterno"].astype(str).map(_normalize_text) if "CodigoBarraInterno" in df.columns else pd.Series(dtype=str),
        }
        self.df_view = None
        self._toggle_opciones_rangos()
        self._fill_preview_table()
        self._show(self.stepC)

    def _build_stepC_preview(self):
        f = self.stepC = ttk.Frame(self, padding=16)
        _wizard_steps(f, 3, ("Listado", "Pegar precios", "Revisar y exportar"))
        ttk.Label(f, text="Revisa los artículos y genera el archivo", style="Section.TLabel").pack(anchor="w")
        ttk.Label(f, text="Comprueba el artículo y el precio nuevo que ingresaste.\n"
                  "Las filas rojas no están en el listado de artículos. Guarda el Excel e impórtalo en Tivendo.",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 0))

        self.lbl_rangos_fuente = ttk.Label(f, text=self._rangos_fuente,
            style="Muted.TLabel", wraplength=1000)
        self.lbl_rangos_fuente.pack(anchor="w", pady=(4, 0))

        # ---- Filtro rápido
        filter_bar = ttk.Frame(f); filter_bar.pack(fill="x", pady=(4,6))
        ttk.Label(filter_bar, text="Filtro rápido:").pack(side="left")
        self.var_filter = tk.StringVar(value="")
        self.ent_filter = ttk.Entry(filter_bar, width=24, textvariable=self.var_filter)
        self.ent_filter.pack(side="left", padx=6)
        ttk.Button(filter_bar, text="Aplicar filtro", command=self._apply_filter).pack(side="left", padx=(0,6))
        ttk.Button(filter_bar, text="Limpiar filtro", command=self._clear_filter).pack(side="left")
        self.var_opciones_rangos = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_bar, text="Opciones de rangos", variable=self.var_opciones_rangos,
            command=self._toggle_opciones_rangos).pack(side="right")
        # Atajos + Live search inmediato
        self.ent_filter.bind("<Return>", lambda e: (self._apply_filter(), self._refocus_filter()))
        self.ent_filter.bind("<Escape>", lambda e: (self._clear_filter(), self._refocus_filter()))
        self.ent_filter.bind("<KeyRelease>", lambda e: (self._apply_filter(), self._refocus_filter()))

        # Validador superior
        self.validator_bar = ttk.Frame(f); self.validator_bar.pack(fill="x", pady=(6,6))
        self.lbl_val_codes = ttk.Label(self.validator_bar, text="Códigos: 0")
        self.lbl_val_prices = ttk.Label(self.validator_bar, text="Precios: 0")
        self.lbl_val_found = ttk.Label(self.validator_bar, text="Encontrados: 0")
        self.lbl_val_nofound = ttk.Label(self.validator_bar, text="No encontrados: 0")
        for w in (self.lbl_val_codes, self.lbl_val_prices, self.lbl_val_found, self.lbl_val_nofound):
            w.pack(side="left", padx=(0,12))

        body = ttk.Frame(f); body.pack(fill="both", expand=True, pady=(8,0))

        cols = ("Código","Nombre","CodigoBarraInterno","Precio1","RangoInicial1","RangoFinal1",
                "Precio2","RangoInicial2","RangoFinal2","RangoExistente")
        self.columns = cols
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=22, selectmode="extended")
        widths = (100, 265, 150, 100, 125, 125, 100, 125, 125, 195)
        headings = ("Código", "Artículo", "Barra interna", "Precio 1", "Rango inicial 1", "Rango final 1", "Precio 2", "Rango inicial 2", "Rango final 2", "¿Tiene otro rango?")
        for c,w in zip(cols, widths):
            self.tree.heading(c, text=headings[cols.index(c)])
            self.tree.column(c, width=w, minwidth=180 if c == "Nombre" else 80, stretch=c == "Nombre", anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.preview_vsb = vsb
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="left", fill="y")

        self.tree.tag_configure("nofound", background="#FDEBEC")
        self.tree.tag_configure("stripe0", background="")
        self.tree.tag_configure("stripe1", background=STRIPE_COLOR)

        side_shell = ttk.Frame(body, padding=(10, 0, 0, 0))
        self.side_shell_rangos = side_shell
        side_shell.pack(side="left", fill="y")
        side_canvas = tk.Canvas(side_shell, width=228, background=UI["background"],
                                highlightthickness=0, borderwidth=0)
        side_canvas.pack(side="left", fill="y")
        side_scroll = ttk.Scrollbar(side_shell, orient="vertical", command=side_canvas.yview)
        side_scroll.pack(side="left", fill="y")
        side_canvas.configure(yscrollcommand=side_scroll.set)
        side = ttk.Frame(side_canvas)
        side_canvas.create_window((0, 0), window=side, anchor="nw")
        side.bind("<Configure>", lambda _e: side_canvas.configure(scrollregion=side_canvas.bbox("all")))

        sw = ttk.Checkbutton(side, text="Habilitar Rango 2 (opcional)", variable=self.enable_r2, command=self._toggle_r2)
        sw.pack(anchor="w", pady=(0,6))

        ttk.Label(side, text="Rango 1 por defecto / masivo").pack(anchor="w", pady=(0,6))
        self.var_def_ri1 = tk.StringVar(value="1")
        self.var_def_rf1 = tk.StringVar(value="1000")
        row1 = ttk.Frame(side); row1.pack(anchor="w", pady=2)
        ttk.Label(row1, text="Desde:").pack(side="left")
        ttk.Entry(row1, width=12, textvariable=self.var_def_ri1).pack(side="left", padx=6)
        row2 = ttk.Frame(side); row2.pack(anchor="w", pady=2)
        ttk.Label(row2, text="Hasta:").pack(side="left")
        ttk.Entry(row2, width=12, textvariable=self.var_def_rf1).pack(side="left", padx=6)
        ttk.Button(side, text="Aplicar (selección)", command=self._apply_range1_selected).pack(anchor="w", pady=(6,3))
        ttk.Button(side, text="Aplicar a todas", command=self._apply_range1_all).pack(anchor="w")

        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=10)

        ttk.Label(side, text="Rango 2 por defecto / masivo").pack(anchor="w", pady=(0,6))
        self.var_def_p2  = tk.StringVar(value="")
        self.var_def_ri2 = tk.StringVar(value="")
        self.var_def_rf2 = tk.StringVar(value="")
        r2a = ttk.Frame(side); r2a.pack(anchor="w", pady=2)
        ttk.Label(r2a, text="Precio2:").pack(side="left")
        ttk.Entry(r2a, width=12, textvariable=self.var_def_p2).pack(side="left", padx=6)
        r2b = ttk.Frame(side); r2b.pack(anchor="w", pady=2)
        ttk.Label(r2b, text="Desde:").pack(side="left")
        ttk.Entry(r2b, width=12, textvariable=self.var_def_ri2).pack(side="left", padx=6)
        r2c = ttk.Frame(side); r2c.pack(anchor="w", pady=2)
        ttk.Label(r2c, text="Hasta:").pack(side="left")
        ttk.Entry(r2c, width=12, textvariable=self.var_def_rf2).pack(side="left", padx=6)
        ttk.Button(side, text="Aplicar Rango 2 (sel.)", command=self._apply_range2_selected).pack(anchor="w", pady=(6,3))
        ttk.Button(side, text="Aplicar Rango 2 a todas", command=self._apply_range2_all).pack(anchor="w")

        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=10)
        ttk.Label(side, text="Sugerencias").pack(anchor="w")
        ttk.Label(side, text="- Precio x kilo: usar 0,001 a 1000", foreground="#555").pack(anchor="w")
        ttk.Checkbutton(side, text="Exportar solo válidas (encontradas)", variable=self.export_only_valid).pack(anchor="w", pady=(10,0))

        self._setup_cell_editing()

        bottom = ttk.Frame(f); bottom.pack(fill="x", pady=(8,0))
        self.lbl_info = ttk.Label(bottom, text="", foreground="#555"); self.lbl_info.pack(side="left")
        ttk.Button(bottom, text="← Volver a pegar", command=lambda:self._show(self.stepB)).pack(side="right", padx=8)
        self.btn_exportar_precios = ttk.Button(bottom, text="Guardar Excel para Tivendo", command=self._export,
                   style="Primary.TButton")
        self.btn_exportar_precios.pack(side="right")

        # Las columnas de la vista previa exceden el ancho de una pantalla.
        # Reservar primero espacio para acciones y controles laterales evita
        # que Treeview los empuje fuera de la ventana mínima.
        hsb = ttk.Scrollbar(f, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=hsb.set)
        bottom.pack_forget()
        body.pack_forget()
        bottom.pack(side="bottom", fill="x", pady=(8, 0))
        hsb.pack(side="bottom", fill="x", pady=(2, 0))
        body.pack(side="top", fill="both", expand=True, pady=(8, 0))
        self.tree.pack_forget()
        vsb.pack_forget()
        side_shell.pack_forget()
        side_shell.pack(side="right", fill="y")
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self._toggle_r2(initial=True)
        self._toggle_opciones_rangos()

    def _toggle_opciones_rangos(self):
        if self.var_opciones_rangos.get():
            self.side_shell_rangos.pack(side="right", fill="y", before=self.preview_vsb)
        else:
            self.side_shell_rangos.pack_forget()
        columns = ["Código", "Nombre", "CodigoBarraInterno"]
        if self.ingresar_rangos.get() or self.var_opciones_rangos.get():
            columns += ["RangoInicial1", "RangoFinal1"]
        columns += ["Precio1"]
        if self.enable_r2.get():
            columns += ["RangoInicial2", "RangoFinal2", "Precio2"]
        columns += ["RangoExistente"]
        self.tree.configure(displaycolumns=columns)

    def _refocus_filter(self):
        try:
            self.ent_filter.focus_set()
        except Exception:
            pass

    def _toggle_r2(self, initial=False):
        if self.enable_r2.get():
            self.ingresar_rangos.set(True)
        if hasattr(self, "_campos_columnas_precios"):
            self._configurar_columnas_pegado()
        if hasattr(self, "var_opciones_rangos"):
            self._toggle_opciones_rangos()

    def _current_df(self):
        return self.df_view if self.df_view is not None else self.df_preview

    def _fill_preview_table(self):
        self.tree.delete(*self.tree.get_children())
        df = self._current_df()

        # Extraer columnas como listas para inserción rápida
        def _col(name, default=""):
            return df[name].fillna(default).astype(str).tolist() if name in df.columns else [default] * len(df)

        ids   = _col("Identificador")
        noms  = _col("Nombre")
        cbis  = _col("CodigoBarraInterno")
        p1s   = _col("Precio1")
        ri1s  = _col("RangoInicial1", "1")
        rf1s  = _col("RangoFinal1", "1000")
        p2s   = _col("Precio2")
        ri2s  = _col("RangoInicial2")
        rf2s  = _col("RangoFinal2")

        ins = self.tree.insert
        no_count = 0
        for idx, (ident, nom, cbi, p1, ri1, rf1, p2, ri2, rf2) in enumerate(
                zip(ids, noms, cbis, p1s, ri1s, rf1s, p2s, ri2s, rf2s)):
            if ident.strip():
                tag = "stripe1" if idx % 2 == 1 else "stripe0"
            else:
                tag = "nofound"
                no_count += 1
            rango = resumen_rango_venta(self._rangos_index.get(_norm_pack_code(ident), {}))
            ins("", "end", values=(ident, nom, cbi, p1, ri1, rf1, p2, ri2, rf2, rango), tags=(tag,))

        total = len(df)
        self.lbl_info.config(text=("PRÁCTICA · No se exporta" if self._modo_ejemplo_precios else
                                   f"{total} fila(s) · {no_count} sin encontrar"))
        self.btn_exportar_precios.config(state="disabled" if self._modo_ejemplo_precios else "normal")
        self._update_validator_counts(total_codes=total, total_prices=total, nofound=no_count)

    def _apply_striped_rows(self):
        found_idx = 0
        for row_id in self.tree.get_children():
            tags = self.tree.item(row_id, "tags")
            if "nofound" in tags:
                continue
            new_tag = "stripe1" if (found_idx % 2 == 1) else "stripe0"
            self.tree.item(row_id, tags=(new_tag,))
            found_idx += 1

    # ---------- filtro ----------
    def _apply_filter(self):
        if self.df_preview is None:
            return
        q = _normalize_text(self.var_filter.get())
        if not q:
            self.df_view = None
        else:
            # Usar columnas pre-normalizadas (calculadas una sola vez al cargar datos)
            norm = self._df_preview_norm
            mask = (
                norm["Identificador"].str.contains(q, na=False)
                | norm["Nombre"].str.contains(q, na=False)
                | norm["CodigoBarraInterno"].str.contains(q, na=False)
            )
            self.df_view = self.df_preview[mask]
        self._fill_preview_table()

    def _clear_filter(self):
        self.var_filter.set("")
        self.df_view = None
        self._fill_preview_table()
        self._refocus_filter()

    def _update_validator_counts(self, total_codes: int, total_prices: int, nofound: int = -1):
        if nofound < 0:
            # Fallback: contar desde el árbol si no se provee
            found = sum(1 for r in self.tree.get_children() if self.tree.set(r, "Código").strip())
            nofound = total_codes - found
        found = total_codes - nofound
        self.lbl_val_codes.config(text=f"Códigos: {total_codes}")
        self.lbl_val_prices.config(text=f"Precios: {total_prices}")
        self.lbl_val_found.config(text=f"Encontrados: {found}")
        self.lbl_val_nofound.config(text=f"No encontrados: {nofound}")
        if total_codes != total_prices:
            self.lbl_val_prices.configure(foreground="#c00")
        else:
            self.lbl_val_prices.configure(foreground="#0a0")
        self.lbl_val_found.configure(foreground="#0a0")
        self.lbl_val_nofound.configure(foreground=("#c00" if nofound>0 else "#333"))

    # ----- edición de celdas (Treeview) -----
    def _setup_cell_editing(self):
        self.tree.bind("<Double-1>", self._begin_edit_cell)
        self._edit_entry = None
        self._edit_item = None
        self._edit_col = None

    def _begin_edit_cell(self, event):
        try:
            region = self.tree.identify("region", event.x, event.y)
            if region != "cell": return
            col = self.tree.identify_column(event.x)
            display_idx = int(col.replace("#","")) - 1
            visible = self.tree["displaycolumns"]
            colname = self.columns[display_idx] if visible == ("#all",) else visible[display_idx]
            editable = {"Precio1", "RangoInicial1", "RangoFinal1"}
            if self.enable_r2.get(): editable.update({"Precio2", "RangoInicial2", "RangoFinal2"})
            if colname not in editable: return
            col_idx = self.columns.index(colname)
            row_id = self.tree.identify_row(event.y)
            if not row_id: return
            bbox = self.tree.bbox(row_id, col)
            if not bbox: return
            x,y,w,h = bbox
            value = self.tree.set(row_id, self.columns[col_idx])

            self._edit_item = row_id; self._edit_col = col_idx
            if self._edit_entry is not None: self._edit_entry.destroy()
            self._edit_entry = tk.Entry(self.tree)
            self._edit_entry.insert(0, value); self._edit_entry.select_range(0, "end")
            self._edit_entry.focus(); self._edit_entry.place(x=x, y=y, width=w, height=h)
            self._edit_entry.bind("<Return>", self._end_edit_cell)
            self._edit_entry.bind("<Escape>", lambda e: self._cancel_edit_cell())
            self._edit_entry.bind("<FocusOut>", lambda e: self._end_edit_cell(e))
        except Exception:
            self._cancel_edit_cell()

    def _end_edit_cell(self, event):
        if self._edit_entry is None: return
        new_val = self._edit_entry.get().strip()
        colname = self.columns[self._edit_col]
        if colname in ("Precio1","Precio2"):
            new_val = clean_price(new_val)
        try:
            self.tree.set(self._edit_item, colname, new_val)
        finally:
            self._cancel_edit_cell()
            self._apply_striped_rows()

    def _cancel_edit_cell(self):
        if self._edit_entry is not None:
            try: self._edit_entry.destroy()
            except Exception: pass
        self._edit_entry = None; self._edit_item = None; self._edit_col = None

    # ----- aplicar rangos masivos -----
    def _apply_range1_selected(self):
        ri = self.var_def_ri1.get().strip(); rf = self.var_def_rf1.get().strip()
        for row_id in self.tree.selection():
            self.tree.set(row_id, "RangoInicial1", ri)
            self.tree.set(row_id, "RangoFinal1", rf)
        self._apply_striped_rows()

    def _apply_range1_all(self):
        ri = self.var_def_ri1.get().strip(); rf = self.var_def_rf1.get().strip()
        for row_id in self.tree.get_children():
            self.tree.set(row_id, "RangoInicial1", ri)
            self.tree.set(row_id, "RangoFinal1", rf)
        self._apply_striped_rows()

    def _apply_range2_selected(self):
        if not self.enable_r2.get():
            messagebox.showinfo("Rango 2", "Primero habilita Rango 2."); return
        p2 = clean_price(self.var_def_p2.get().strip())
        ri = self.var_def_ri2.get().strip(); rf = self.var_def_rf2.get().strip()
        for row_id in self.tree.selection():
            if p2: self.tree.set(row_id, "Precio2", p2)
            self.tree.set(row_id, "RangoInicial2", ri)
            self.tree.set(row_id, "RangoFinal2", rf)
        self._apply_striped_rows()

    def _apply_range2_all(self):
        if not self.enable_r2.get():
            messagebox.showinfo("Rango 2", "Primero habilita Rango 2."); return
        p2 = clean_price(self.var_def_p2.get().strip())
        ri = self.var_def_ri2.get().strip(); rf = self.var_def_rf2.get().strip()
        for row_id in self.tree.get_children():
            if p2: self.tree.set(row_id, "Precio2", p2)
            self.tree.set(row_id, "RangoInicial2", ri)
            self.tree.set(row_id, "RangoFinal2", rf)
        self._apply_striped_rows()

    # ----- exportar -----
    def _collect_df_from_tree(self):
        cols = list(self.columns)
        data = []
        for row_id in self.tree.get_children():
            data.append([self.tree.set(row_id, c) for c in cols])
        return pd.DataFrame(data, columns=cols)

    def _export(self):
        if self._modo_ejemplo_precios:
            messagebox.showinfo("Modo práctica", "Vuelve a pegar, limpia el ejemplo y usa tus precios reales para guardar el Excel.")
            return
        df_tabla = self._collect_df_from_tree()
        if df_tabla.empty:
            messagebox.showwarning("Sin datos", "No hay filas para exportar."); return

        if self.export_only_valid.get():
            df_tabla = df_tabla[df_tabla["Código"].astype(str).str.strip() != ""]
            if df_tabla.empty:
                messagebox.showwarning("Sin válidas", "No hay filas válidas para exportar."); return

        ok = df_tabla.copy()
        for col in ("RangoInicial2","RangoFinal2","Precio2"):
            if col not in ok.columns: ok[col] = ""

        output_cols = ["Código","RangoInicial1","RangoFinal1","Precio1","RangoInicial2","RangoFinal2","Precio2"]
        missing = [c for c in ("Código","RangoInicial1","RangoFinal1","Precio1") if c not in ok.columns]
        if missing:
            messagebox.showerror("Error", f"Faltan columnas para exportar: {missing}"); return

        # Revalidar también lo editado en la tabla. Un segundo rango desactivado
        # nunca se exporta aunque conserve datos ocultos para volver a activarlo.
        for line, (index, row) in enumerate(ok.iterrows(), 1):
            values = [row[column] for column in output_cols]
            checked, errors = preparar_fila_precio(values, con_rangos=True, con_rango2=self.enable_r2.get())
            # Si se eligió incluir no encontrados, se conserva la política anterior
            # de permitir el código vacío, sin omitir la validación de rangos/precios.
            if not self.export_only_valid.get():
                errors.pop(0, None)
            if errors:
                messagebox.showwarning("Revisa los rangos y precios", f"Fila {line}: {next(iter(errors.values()))}.\nCorrígela antes de guardar.")
                return
            for column in output_cols[1:]:
                ok.at[index, column] = checked[column]

        out = ok[output_cols]
        path = filedialog.asksaveasfilename(title="Guardar archivo para importar", defaultextension=".xlsx",
                                            filetypes=[("Excel","*.xlsx")])
        if not path: return
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as wr:
                out.to_excel(wr, index=False, sheet_name="Precios")
        except Exception as e:
            messagebox.showerror("Error al guardar", f"No se pudo escribir el Excel.\n{e}"); return

        messagebox.showinfo("Excel listo para importar", f"Se guardaron {len(out)} cambios en:\n{path}\n\nSiguiente: importa este Excel en los cambios masivos de precios de Tivendo.")

    def _show(self, frame):
        for child in (self.stepA, self.stepB, self.stepC):
            child.pack_forget()
        frame.pack(fill="both", expand=True)

# =====================================================
#  Módulo Tivendo: Ingreso masivo de artículos (integrado en menú principal)
# =====================================================


def incrementar_codigo_identificador(codigo: str) -> str:
    if not codigo:
        return codigo

    m = _RE_COD_IDENT.match(codigo.strip())
    if not m:
        return codigo

    prefijo = m.group(1)
    numeros = m.group(2)
    largo = len(numeros)

    n = int(numeros) + 1
    return f"{prefijo}{n:0{largo}d}"


def normalizar_codigo_catalogo(valor: str) -> str:
    if valor is None:
        return ""
    s = str(valor).strip().upper()
    s = _RE_NON_ALNUM.sub("", s)
    return s

def leer_catalogo_articulos(ruta) -> pd.DataFrame:
    """Lee el export original sin depender de posiciones fijas de filas o columnas."""
    path = Path(ruta)
    if path.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
        raw = pd.read_excel(path, header=None, dtype=str)
    elif path.suffix.lower() == ".csv":
        try:
            raw = pd.read_csv(path, header=None, dtype=str, sep=None, engine="python")
        except UnicodeDecodeError:
            raw = pd.read_csv(path, header=None, dtype=str, sep=None, engine="python", encoding="latin-1")
    else:
        raise ValueError("Utiliza el listado de artículos exportado por Tivendo en Excel o CSV.")
    for index, row in enumerate(raw.head(30).itertuples(index=False, name=None)):
        headers = [_normalize_text("" if pd.isna(value) else str(value)) for value in row]
        if "nombre" not in headers or not any(h in headers for h in ("identificador", "codigo")):
            continue
        ident = headers.index("identificador") if "identificador" in headers else headers.index("codigo")
        names = {"codigo": ident, "nombre": headers.index("nombre")}
        for output, candidates in (("precio", ("precio", "precio venta")),
                                   ("activo", ("activo", "estado"))):
            names[output] = next((headers.index(h) for h in candidates if h in headers), None)
        result = pd.DataFrame({key: raw.iloc[index + 1:, column].fillna("").astype(str).str.strip()
                               if column is not None else ""
                               for key, column in names.items()})
        result = result[result["codigo"].ne("")].reset_index(drop=True)
        result.attrs["estado_disponible"] = names["activo"] is not None
        if result.empty:
            raise ValueError("El listado no contiene artículos. Se conserva el listado anterior.")
        return result
    raise ValueError("No se encontraron los encabezados Código/Identificador y Nombre en el listado de Tivendo.")


def calcular_secuencia_articulos(catalogo: pd.DataFrame, reservados=()) -> dict:
    """Continúa después del mayor A+6 activo; todos los códigos siguen reservados."""
    codes = catalogo["codigo"].fillna("").astype(str).str.strip().str.upper()
    names = catalogo["nombre"].fillna("").astype(str)
    active = catalogo.get("activo", pd.Series("", index=catalogo.index)).fillna("").astype(str).map(_normalize_text)
    valid = codes.str.fullmatch(r"A[0-9]{6}")
    valid &= active.isin(("si", "s", "1", "true", "activo", "active"))
    valid &= ~names.map(_normalize_text).str.match(r"^no\s+disponible\b")
    valid &= names.str.strip().ne("")
    summary = {"ultimo": "", "nombre": "", "siguiente": "", "validos": int(valid.sum()),
               "ignorados": int((~valid).sum()),
               "estado_disponible": catalogo.attrs.get("estado_disponible", "activo" in catalogo.columns)}
    if not valid.any():
        return summary
    last_index = codes[valid].map(lambda value: int(value[1:])).idxmax()
    last = codes.loc[last_index]
    used = {normalizar_codigo_catalogo(value) for value in list(codes) + list(reservados)}
    number = int(last[1:]) + 1
    while number <= 999999 and f"A{number:06d}" in used:
        number += 1
    summary.update(ultimo=last, nombre=names.loc[last_index],
                   siguiente=f"A{number:06d}" if number <= 999999 else "")
    return summary


def parsear_tabla_pegada(texto: str, columnas: int, encabezados) -> list:
    rows = list(csv.reader(io.StringIO(texto), delimiter="\t"))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if rows and _normalize_text(rows[0][0]) in encabezados:
        rows.pop(0)
    if not rows:
        raise ValueError("Copia primero las filas de Excel que quieres pegar.")
    if any(len(row) > columnas or any("\n" in cell or "\r" in cell for cell in row) for row in rows):
        raise ValueError(f"Copia como máximo {columnas} columnas, con un artículo por fila y sin saltos de línea dentro de las celdas.")
    return [(row + [""] * columnas)[:columnas] for row in rows]


def buscar_siguiente_codigo_disponible(codigo_actual: str, codigos_catalogo_set, codigos_catalogo_norm_set) -> str:
    if not codigo_actual:
        return codigo_actual

    m = _RE_COD_IDENT.match(codigo_actual.strip())
    if not m:
        return incrementar_codigo_identificador(codigo_actual)

    prefijo = m.group(1).upper()
    numeros = m.group(2)
    largo = len(numeros)

    n = int(numeros)
    limite = 10**largo - 1

    while n < limite:
        n += 1
        candidato = f"{prefijo}{n:0{largo}d}"
        candidato_norm = normalizar_codigo_catalogo(candidato)

        if (candidato not in codigos_catalogo_set) and (candidato_norm not in codigos_catalogo_norm_set):
            return candidato

    return incrementar_codigo_identificador(codigo_actual)

class TivendoIngresoMasivoArticulosWindow(ttk.Frame):
    def __init__(self, master, catalogo_path: Optional[Path] = None, go_home_cb=None):
        super().__init__(master)
        self.master.title(f"Tivendo - Ingreso Masivo de Artículos ({APP_VERSION})")
        self.pack(fill="both", expand=True)
        self.go_home_cb = go_home_cb

        self.df_import = pd.DataFrame(columns=[
            "Código", "Nombre", "Unidad", "Precio",
            "Código barra interno", "Código barra externo",
            "Descripción", "Es Servicio", "Es Exento",
            "Impuesto Específico", "Id Categoría",
            "Disponible venta", "Activo",
            "Utilidad", "Tipo Utilidad", "Palabras Clave"
        ])

        self.df_catalogo = None
        self.codigos_catalogo_set = set()
        self.codigos_catalogo_norm_set = set()
        self.catalogo_path = Path(catalogo_path) if catalogo_path else None
        self._catalogo_cargando = False
        self._catalogo_job = 0
        self.var_codigo_inicial = tk.StringVar()
        self.var_codigo_manual = tk.BooleanVar(value=False)

        # Cargamos siempre la versión más reciente de proveedores desde empresas.json
        _emp = load_empresas()
        self.empresas_name_to_id = {v: k for k, v in _emp.items()}

        self.var_codigo_actual = tk.StringVar()
        self.var_nombre = tk.StringVar()
        self.var_precio = tk.StringVar()
        self.var_cod_barra_int = tk.StringVar()
        self.var_cod_barra_ext = tk.StringVar()
        self.var_usar_mismo_codigo = tk.BooleanVar(value=True)

        self.var_empresa_nombre = tk.StringVar()
        self.var_nombre_archivo_salida = tk.StringVar(value="ingreso_masivo_articulos.xlsx")

        self.text_nombre = None
        self.text_precio = None
        self.text_codint = None
        self.text_codext = None

        top = ttk.Frame(self, padding=(16, 12, 16, 4))
        top.pack(fill="x")
        ttk.Button(top, text="← Inicio", command=self._back_home).pack(side="left")
        ttk.Label(top, text="Ingreso masivo de artículos", style="Title.TLabel").pack(side="left", padx=16)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

        self.frame_paso1 = ttk.Frame(self.container)
        self.frame_paso2 = ttk.Frame(self.container)
        self.frame_paso3 = ttk.Frame(self.container)

        self.tree = None
        self._tree_editor = None  # Entry temporal para editar celdas

        self._crear_paso1()
        self._crear_paso2()
        self._crear_paso3()
        self._mostrar_paso(1)

        # Carga diferida del catálogo (no bloquea la UI)
        if catalogo_path:
            try:
                self._start_async_catalogo_load(catalogo_path)
            except Exception:
                pass
        else:
            self.lbl_catalogo_estado.config(text="Todavía no hay un listado cargado")
            self.lbl_ultimo_articulo.config(text="Pulsa Actualizar listado y último código para comenzar.", style="Card.Warning.TLabel")

    def _crear_paso1(self):
        _wizard_steps(self.frame_paso1, 1, ("Confirmar listado", "Pegar artículos", "Revisar y guardar"))
        lbl_titulo = ttk.Label(
            self.frame_paso1,
            text="Primero confirma desde qué artículo continuar",
            style="Section.TLabel",
            wraplength=1150,
            justify="left",
        )
        lbl_titulo.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(self.frame_paso1, text="Prepararás un Excel para importar en Tivendo. Aquí todavía no se crean artículos.",
                  style="Muted.TLabel").pack(anchor="w", padx=10)

        frame_cat = ttk.Frame(self.frame_paso1, style="Card.TFrame", padding=12)
        frame_cat.pack(fill="x", padx=10, pady=(12, 8))
        frame_cat.columnconfigure(0, weight=1)
        self.lbl_catalogo_estado = ttk.Label(frame_cat, text="Comprobando listado…", style="Card.Section.TLabel")
        self.lbl_catalogo_estado.grid(row=0, column=0, sticky="w")
        self.btn_actualizar_catalogo = ttk.Button(frame_cat, text="Actualizar listado y último código",
            style="Primary.TButton", command=self._actualizar_catalogo_desde_tivendo)
        self.btn_actualizar_catalogo.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.lbl_catalogo_archivo = ttk.Label(frame_cat, text="", style="Card.Muted.TLabel", wraplength=850)
        self.lbl_catalogo_archivo.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
        self.lbl_catalogo_fecha = ttk.Label(frame_cat, text="", style="Card.Muted.TLabel")
        self.lbl_catalogo_fecha.grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))
        self.lbl_ultimo_articulo = ttk.Label(frame_cat, text="", style="Card.Success.TLabel", wraplength=850)
        self.lbl_ultimo_articulo.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(frame_cat, text="Mismo listado que en Inicio. Esta actualización descarga solo artículos.",
            style="Card.Muted.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))

        frame_conf = ttk.LabelFrame(self.frame_paso1, text="Numeración y categoría")
        frame_conf.pack(fill="x", padx=10, pady=5)
        frame_conf.columnconfigure(1, weight=1)

        ttk.Label(frame_conf, text="Empezar desde:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        self.entry_codigo_inicial = ttk.Entry(
            frame_conf, textvariable=self.var_codigo_inicial, width=15, state="readonly"
        )
        self.entry_codigo_inicial.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Checkbutton(frame_conf, text="Cambiar código manualmente", variable=self.var_codigo_manual,
            command=self._toggle_codigo_manual).grid(row=0, column=2, columnspan=2, padx=8, pady=5, sticky="w")
        ttk.Label(frame_conf, text="Se continúa después del mayor A + 6 números activo; no se rellenan huecos antiguos.",
            style="Muted.TLabel").grid(row=1, column=0, columnspan=4, padx=8, pady=(0, 8), sticky="w")

        ttk.Label(frame_conf, text="Categoría / proveedor (opcional):").grid(
            row=2, column=0, padx=5, pady=5, sticky="e"
        )
        nombres_empresas = sorted(self.empresas_name_to_id.keys())
        # Guardamos la lista completa para poder filtrarla con el mini buscador
        self.empresas_choices_p1 = nombres_empresas

        self.combo_empresa = ttk.Combobox(
            frame_conf,
            textvariable=self.var_empresa_nombre,
            values=[""] + nombres_empresas,
            state="readonly",
            width=35,
        )
        self.combo_empresa.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.var_empresa_nombre.set("")
        ttk.Button(frame_conf, text="Dejar sin categoría", command=lambda: self.var_empresa_nombre.set("")).grid(
            row=2, column=2, columnspan=2, padx=8, pady=5, sticky="w")

        # Mini buscador de proveedor en vivo (para no recorrer toda la lista)
        self.var_empresa_search_p1 = tk.StringVar()
        entry_buscar = ttk.Entry(frame_conf, textvariable=self.var_empresa_search_p1, width=20)
        # Lo ubicamos a la derecha del combobox de proveedor
        entry_buscar.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(frame_conf, text="Buscar categoría:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        entry_buscar.bind("<KeyRelease>", self._on_empresa_search_p1)

        btn_instrucciones = ttk.Button(
            frame_conf, text="Ver instrucciones", command=self._abrir_instrucciones
        )
        btn_instrucciones.grid(row=3, column=2, padx=8, pady=5, sticky="w")

        frame_nav = ttk.Frame(self.frame_paso1)
        frame_nav.pack(side="bottom", fill="x", padx=10, pady=10)

        btn_anterior_p1 = ttk.Button(frame_nav, text="← Anterior", state="disabled")
        btn_anterior_p1.pack(side="left")

        self.btn_paso2 = ttk.Button(frame_nav, text="Continuar: pegar artículos →", command=self._ir_a_paso2,
                                  style="Primary.TButton", state="disabled")
        self.btn_paso2.pack(side="right")
        self.var_codigo_inicial.trace_add("write", lambda *_: self._actualizar_estado_codigo())

    def _on_empresa_search_p1(self, event=None):
        """Filtra en vivo la lista de proveedores del PASO 1 según el mini buscador."""
        _filter_combobox_choices(
            self.var_empresa_search_p1.get().strip().lower(),
            self.empresas_choices_p1,
            self.combo_empresa,
            self.var_empresa_nombre,
        )

    def _toggle_codigo_manual(self):
        self.entry_codigo_inicial.config(state="normal" if self.var_codigo_manual.get() else "readonly")
        if not self.var_codigo_manual.get() and self.df_catalogo is not None:
            self.var_codigo_inicial.set(calcular_secuencia_articulos(self.df_catalogo)["siguiente"])
        self._actualizar_estado_codigo()

    def _actualizar_estado_codigo(self):
        ready = self.df_catalogo is not None and not self._catalogo_cargando
        valid = re.fullmatch(r"A[0-9]{6}", self.var_codigo_inicial.get().strip().upper()) is not None
        self.btn_paso2.config(state="normal" if ready and valid else "disabled")

    def _aplicar_catalogo(self, ruta, catalogo):
        if not self.winfo_exists():
            return
        self._catalogo_cargando = False
        self.catalogo_path = Path(ruta)
        self.df_catalogo = catalogo
        self.codigos_catalogo_set = set(catalogo["codigo"].astype(str).str.strip())
        self.codigos_catalogo_norm_set = {normalizar_codigo_catalogo(code) for code in self.codigos_catalogo_set}
        summary = calcular_secuencia_articulos(catalogo)
        self.lbl_catalogo_estado.config(text=f"Listado comprobado · {len(catalogo):,} artículos")
        self.lbl_catalogo_archivo.config(text=f"Archivo: {self.catalogo_path.name}")
        self.lbl_catalogo_fecha.config(text=f"Última descarga del listado: {article_download_label(self.catalogo_path)}")
        if summary["siguiente"]:
            text = f"Último válido: {summary['ultimo']} · {summary['nombre']}\nSiguiente para crear: {summary['siguiente']}"
            style = "Card.Success.TLabel"
        else:
            text = ("No se puede proponer un código: falta la columna Activo/Estado." if not summary["estado_disponible"]
                    else "No se encontró una secuencia activa A + 6 números con espacio para continuar.")
            text += " Actualiza el listado o revisa el código manualmente."
            style = "Card.Warning.TLabel"
        self.lbl_ultimo_articulo.config(text=text, style=style)
        if not self.var_codigo_manual.get():
            self.var_codigo_inicial.set(summary["siguiente"])
        self.btn_actualizar_catalogo.config(state="normal")
        self._actualizar_estado_codigo()

    def _actualizar_catalogo_desde_tivendo(self):
        # Invalida cualquier lectura anterior que todavía esté en curso.
        self._catalogo_job += 1
        self.master._actualizar_solo_articulos(self._catalogo_actualizado)

    def _catalogo_actualizado(self, ruta, catalogo):
        self.var_codigo_manual.set(False)
        self.entry_codigo_inicial.config(state="readonly")
        self._aplicar_catalogo(ruta, catalogo)
        self.df_import = self.df_import.head(0).copy()
        self._refrescar_tabla()

    def _crear_paso2(self):
        _wizard_steps(self.frame_paso2, 2, ("Confirmar listado", "Pegar artículos", "Revisar y guardar"))
        lbl_titulo = ttk.Label(
            self.frame_paso2,
            text="Pega los datos de los artículos",
            style="Section.TLabel",
            wraplength=1150,
            justify="left"
        )
        lbl_titulo.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(self.frame_paso2,
                  text="Una fila por artículo. Copia desde Excel: nombre, precio, barra interna y, si lo tienes, código de proveedor.",
                  style="Muted.TLabel").pack(anchor="w", padx=10)

        toolbar = ttk.Frame(self.frame_paso2)
        toolbar.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Button(toolbar, text="Pegar tabla de Excel", command=self._pegar_tabla_articulos,
            style="Primary.TButton").pack(side="left")
        ttk.Button(toolbar, text="Probar con un ejemplo", command=self._ejemplo_articulos).pack(side="left", padx=8)
        ttk.Label(toolbar, text="También puedes pegar cada columna por separado.",
            style="Muted.TLabel").pack(side="left", padx=4)

        frame_cols = ttk.LabelFrame(self.frame_paso2, text="Ingreso masivo (uno por línea en cada columna)")
        frame_cols.pack(fill="both", expand=True, padx=10, pady=5)

        frame_cols.rowconfigure(0, weight=1)
        for index, (attribute, title, weight) in enumerate((
                ("text_nombre", "1. Nombre *", 3), ("text_precio", "2. Precio *", 1),
                ("text_codint", "3. Barra interna *", 1), ("text_codext", "4. Cód. proveedor (opcional)", 1))):
            column = ttk.Frame(frame_cols)
            column.grid(row=0, column=index, sticky="nsew", padx=5, pady=5)
            frame_cols.columnconfigure(index, weight=weight)
            setattr(self, attribute, _paste_text_column(column, title))

        frame_btns = ttk.Frame(self.frame_paso2)
        frame_btns.pack(fill="x", padx=10, pady=5)
        self.lbl_estado_pegado = ttk.Label(frame_btns, text="Pega los datos para comprobarlos aquí.", style="Muted.TLabel", wraplength=700)
        self.lbl_estado_pegado.pack(side="left")
        self._modo_ejemplo = False
        for widget in (self.text_nombre, self.text_precio, self.text_codint, self.text_codext):
            widget.tag_configure("error_dato", background="#FDEBEC")
            widget.bind("<<Modified>>", self._al_editar_articulos)
        self.text_nombre.bind("<Control-v>", self._pegar_excel_en_nombre)
        self.text_nombre.bind("<Control-V>", self._pegar_excel_en_nombre)

        btn_limpiar = ttk.Button(frame_btns, text="Limpiar todo", command=self.limpiar_textos_paso2)
        btn_limpiar.pack(side="right", padx=5)

        frame_nav = ttk.Frame(self.frame_paso2)
        frame_nav.pack(fill="x", padx=10, pady=10)

        btn_anterior = ttk.Button(frame_nav, text="← Anterior", command=lambda: self._mostrar_paso(1))
        btn_anterior.pack(side="left")

        self.btn_revisar_articulos = ttk.Button(frame_nav, text="Comprobar y revisar artículos →", command=self._procesar_y_ir_a_paso3,
                                  style="Primary.TButton", state="disabled")
        self.btn_revisar_articulos.pack(side="right")
        frame_cols.pack_forget()
        frame_btns.pack_forget()
        frame_nav.pack_forget()
        frame_nav.pack(side="bottom", fill="x", padx=10, pady=10)
        frame_btns.pack(side="bottom", fill="x", padx=10, pady=5)
        frame_cols.pack(side="top", fill="both", expand=True, padx=10, pady=5)

    def _lineas_articulos(self):
        return [widget.get("1.0", "end-1c").splitlines()
                for widget in (self.text_nombre, self.text_precio, self.text_codint, self.text_codext)]

    def _al_editar_articulos(self, event):
        if event.widget.edit_modified():
            event.widget.edit_modified(False)
            self._actualizar_pegado_articulos()

    def _actualizar_pegado_articulos(self):
        columns = self._lineas_articulos()
        widgets = (self.text_nombre, self.text_precio, self.text_codint, self.text_codext)
        for widget in widgets:
            widget.tag_remove("error_dato", "1.0", "end")
        count = 0
        errors = []
        for index in range(max(map(len, columns), default=0)):
            row = [column[index].strip() if index < len(column) else "" for column in columns]
            if not any(row):
                continue
            count += 1
            for col, label in ((0, "nombre"), (1, "precio"), (2, "barra interna")):
                if not row[col] or (col == 1 and (not re.fullmatch(r"[\d$.,\s]+", row[col]) or not _RE_NO_DIGITS.sub("", row[col]))):
                    errors.append(f"fila {index + 1}: {label}")
                    widgets[col].tag_add("error_dato", f"{index + 1}.0", f"{index + 1}.end+1c")
        if errors:
            text = f"{count} artículo(s) · Revisa {errors[0]}" + (f" y {len(errors)-1} dato(s) más." if len(errors) > 1 else ".")
            style = "Warning.TLabel"
        elif count:
            text = ("PRÁCTICA · " if self._modo_ejemplo else "") + f"{count} artículo(s) · Datos completos para revisar."
            style = "Success.TLabel"
        else:
            text, style = "Pega los datos. Los campos con * son obligatorios.", "Muted.TLabel"
        self.lbl_estado_pegado.config(text=text, style=style)
        self.btn_revisar_articulos.config(state="normal" if count and not errors else "disabled")
        return count > 0 and not errors

    def _escribir_tabla_articulos(self, rows, ejemplo=False):
        self._modo_ejemplo = ejemplo
        for column, widget in enumerate((self.text_nombre, self.text_precio, self.text_codint, self.text_codext)):
            widget.delete("1.0", "end")
            widget.insert("1.0", "\n".join(row[column] for row in rows))
        self._actualizar_pegado_articulos()

    def _pegar_excel_en_nombre(self, event=None):
        try:
            if "\t" in self.clipboard_get():
                self._pegar_tabla_articulos()
                return "break"
        except tk.TclError:
            pass

    def _pegar_tabla_articulos(self):
        try:
            rows = parsear_tabla_pegada(self.clipboard_get(), 4, {"nombre", "nombre del articulo"})
            if any(widget.get("1.0", "end-1c").strip() for widget in (self.text_nombre, self.text_precio, self.text_codint, self.text_codext)):
                if not messagebox.askyesno("Reemplazar datos pegados", "¿Reemplazar las columnas actuales con la tabla que copiaste?"):
                    return
            self._escribir_tabla_articulos(rows)
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Cómo pegar desde Excel", f"{exc}\n\nOrden: Nombre | Precio | Barra interna | Código de proveedor (opcional).")

    def _ejemplo_articulos(self):
        if any(widget.get("1.0", "end-1c").strip() for widget in (self.text_nombre, self.text_precio, self.text_codint, self.text_codext)):
            if not messagebox.askyesno("Probar ejemplo", "¿Reemplazar los datos pegados por dos artículos de práctica?"):
                return
        self._escribir_tabla_articulos([["GALLETAS DE EJEMPLO 100 G", "1290", "7800000000001", "GAL001"],
                                        ["JUGO DE EJEMPLO 1 L", "1890", "7800000000002", "JUG002"]], ejemplo=True)

    def _crear_paso3(self):
        _wizard_steps(self.frame_paso3, 3, ("Confirmar listado", "Pegar artículos", "Revisar y guardar"))
        lbl_titulo = ttk.Label(
            self.frame_paso3,
            text="Revisa los artículos y genera el Excel",
            style="Section.TLabel",
            wraplength=1150,
            justify="left"
        )
        lbl_titulo.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(self.frame_paso3, text="Haz doble clic para corregir. Al guardar obtendrás un Excel: después debes importarlo en Tivendo.",
                  style="Muted.TLabel").pack(anchor="w", padx=10)
        self.lbl_resumen_ingreso = ttk.Label(self.frame_paso3, text="", style="Success.TLabel", wraplength=900)
        self.lbl_resumen_ingreso.pack(anchor="w", padx=10, pady=(6, 0))

        frame_archivo = ttk.LabelFrame(self.frame_paso3, text="Configuración del archivo de salida")
        frame_archivo.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_archivo, text="Nombre archivo salida:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        ttk.Entry(frame_archivo, textvariable=self.var_nombre_archivo_salida, width=40).grid(
            row=0, column=1, padx=5, pady=5, sticky="w"
        )

        self.btn_generar_articulos = ttk.Button(
            frame_archivo,
            text="Guardar Excel para Tivendo",
            command=self.generar_excel, style="Primary.TButton"
        )
        self.btn_generar_articulos.grid(row=0, column=2, padx=10, pady=5, sticky="w")
        self.var_ver_todos_campos = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame_archivo, text="Ver todos los campos del Excel", variable=self.var_ver_todos_campos,
            command=self._toggle_campos_importacion).grid(row=1, column=0, columnspan=3, padx=8, pady=(0, 5), sticky="w")

        frame_tabla = ttk.LabelFrame(self.frame_paso3, text="Vista previa archivo de ingreso masivo")
        frame_tabla.pack(fill="both", expand=True, padx=10, pady=5)

        frame_tabla.rowconfigure(0, weight=1)
        frame_tabla.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(frame_tabla, columns=list(self.df_import.columns), show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar_y = ttk.Scrollbar(frame_tabla, orient="vertical", command=self.tree.yview)
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x = ttk.Scrollbar(frame_tabla, orient="horizontal", command=self.tree.xview)
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        for col in self.df_import.columns:
            self.tree.heading(col, text={"Código barra interno": "Barra interna", "Código barra externo": "Barra externa",
                                         "Id Categoría": "Categoría"}.get(col, col))
            self.tree.column(col, anchor="w", stretch=False, width=120)
        self._toggle_campos_importacion()

        # Colores alternados tipo Excel
        self.tree.tag_configure("fila_par", background=STRIPE_COLOR)
        self.tree.tag_configure("fila_impar", background="#FFFFFF")
        self.tree.tag_configure("error_fila", background="#FDEBEC")

        # Doble click para editar celdas (menos la columna Código)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        self._refrescar_tabla()

        frame_nav = ttk.Frame(self.frame_paso3)
        frame_nav.pack(fill="x", padx=10, pady=10)

        btn_anterior = ttk.Button(frame_nav, text="← Anterior", command=self._ir_a_paso2)
        btn_anterior.pack(side="left")
        frame_tabla.pack_forget()
        frame_nav.pack_forget()
        frame_nav.pack(side="bottom", fill="x", padx=10, pady=10)
        frame_tabla.pack(side="top", fill="both", expand=True, padx=10, pady=5)

    def _toggle_campos_importacion(self):
        self.tree.configure(displaycolumns="#all" if self.var_ver_todos_campos.get() else
            ("Código", "Nombre", "Precio", "Código barra interno", "Código barra externo"))

    def _ajustar_anchos_columnas(self):
        """Ajusta anchos de columnas en O(n): un solo recorrido sobre todas las filas."""
        if not self.tree:
            return
        cols = list(self.df_import.columns)
        max_lens = {col: len(str(col)) for col in cols}
        for item in self.tree.get_children():
            for col in cols:
                l = len(self.tree.set(item, col))
                if l > max_lens[col]:
                    max_lens[col] = l
        font = tkfont.Font(font=("Segoe UI", 10, "bold"))
        for col, max_len in max_lens.items():
            heading = self.tree.heading(col, "text")
            width = max(90, min(420, max_len * 7 + 24), font.measure(heading) + 24)
            self.tree.column(col, width=width, minwidth=90, stretch=col == "Nombre", anchor="w")

    def _mostrar_paso(self, n: int):
        for f in (self.frame_paso1, self.frame_paso2, self.frame_paso3):
            f.pack_forget()

        if n == 1:
            self.frame_paso1.pack(fill="both", expand=True)
        elif n == 2:
            self.frame_paso2.pack(fill="both", expand=True)
        elif n == 3:
            self.frame_paso3.pack(fill="both", expand=True)

    # ==========================
    # Edición en la vista previa
    # ==========================
    def _on_tree_double_click(self, event):
        # Cerrar editor anterior si existe
        if self._tree_editor is not None:
            self._tree_editor.destroy()
            self._tree_editor = None

        item_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)  # '#1', '#2', ...
        if not item_id or not col_id:
            return

        col_index = int(col_id.replace("#", "")) - 1
        columnas = list(self.df_import.columns)

        if col_index < 0 or col_index >= len(columnas):
            return

        visibles = self.tree["displaycolumns"]
        col_name = columnas[col_index] if visibles == ("#all",) else visibles[col_index]
        col_index = columnas.index(col_name)

        # No permitir editar el código
        if col_name == "Código":
            return

        # Índice de la fila en el DataFrame
        row_index = self.tree.index(item_id)
        if row_index < 0 or row_index >= len(self.df_import):
            return

        # Obtener bounding box de la celda clickeada
        bbox = self.tree.bbox(item_id, col_id)
        if not bbox:
            return

        x, y, w, h = bbox

        valor_actual = self.tree.set(item_id, col_name)

        # Crear Entry encima de la celda
        editor = tk.Entry(self.tree)
        editor.insert(0, valor_actual)
        editor.select_range(0, "end")
        editor.focus()
        editor.place(x=x, y=y, width=w, height=h)

        def _guardar_edicion(event=None):
            if self._tree_editor is not editor:
                return
            nuevo_valor = editor.get()
            # Actualizar Treeview
            valores_fila = list(self.tree.item(item_id, "values"))
            valores_fila[col_index] = nuevo_valor
            self.tree.item(item_id, values=valores_fila)
            # Actualizar DataFrame
            self.df_import.at[row_index, col_name] = nuevo_valor
            editor.destroy()
            self._tree_editor = None
            self._refrescar_tabla()

        def _cancelar_edicion(event=None):
            editor.destroy()
            self._tree_editor = None

        editor.bind("<Return>", _guardar_edicion)
        editor.bind("<Escape>", _cancelar_edicion)
        editor.bind("<FocusOut>", _guardar_edicion)

        self._tree_editor = editor

    def _custom_dialog_codigo_existente(self, codigo, desc_cat, siguiente_codigo):
        top = tk.Toplevel(self)
        top.title("Código ya existente")
        top.grab_set()

        msg = f"El código identificador '{codigo}' YA existe en el catálogo cargado.\n\n"
        if desc_cat:
            msg += f"Artículo actual en Tivendo (vista previa catálogo):\n{desc_cat}\n\n"

        msg += (
            "Si usas este código en el archivo de ingreso masivo, Tivendo REEMPLAZARÁ ese artículo por el nuevo.\n\n"
            "Selecciona una opción:"
        )

        lbl = ttk.Label(top, text=msg, justify="left", wraplength=600)
        lbl.pack(padx=15, pady=15)

        frame_btns = ttk.Frame(top)
        frame_btns.pack(pady=10)

        choice = {"value": "cancelar"}

        def set_choice(value):
            choice["value"] = value
            top.destroy()

        btn_cancelar = ttk.Button(frame_btns, text="Cancelar", command=lambda: set_choice("cancelar"))
        btn_cancelar.grid(row=0, column=0, padx=5)

        btn_reemplazar = ttk.Button(frame_btns, text="Reemplazar datos", command=lambda: set_choice("reemplazar"))
        btn_reemplazar.grid(row=0, column=1, padx=5)

        texto_siguiente = f"Continuar con {siguiente_codigo}"
        btn_siguiente = ttk.Button(frame_btns, text=texto_siguiente, command=lambda: set_choice("siguiente"))
        btn_siguiente.grid(row=0, column=2, padx=5)

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 200
        y = self.winfo_y() + (self.winfo_height() // 2) - 80
        top.geometry(f"+{x}+{y}")

        top.wait_window()
        return choice["value"]

    def validar_codigo_inicial(self) -> bool:
        codigo = self.var_codigo_actual.get().strip()
        if not codigo:
            messagebox.showwarning("Atención", "Debes ingresar el código identificador inicial.")
            return False

        if self.df_catalogo is None or (not self.codigos_catalogo_set and not self.codigos_catalogo_norm_set):
            return True

        codigo_norm = normalizar_codigo_catalogo(codigo)
        existe_directo = codigo in self.codigos_catalogo_set
        existe_normalizado = codigo_norm in self.codigos_catalogo_norm_set

        if not (existe_directo or existe_normalizado):
            return True

        desc_cat = ""
        if not existe_directo:
            df_filtrado = self.df_catalogo[
                self.df_catalogo["codigo"].astype(str).apply(normalizar_codigo_catalogo) == codigo_norm
            ]
        else:
            df_filtrado = self.df_catalogo[
                self.df_catalogo["codigo"].astype(str).str.strip() == codigo
            ]

        if not df_filtrado.empty:
            fila = df_filtrado.iloc[0]
            desc_cat = f"{fila['nombre']} (Precio: {fila['precio']})"

        siguiente_codigo = buscar_siguiente_codigo_disponible(
            codigo,
            self.codigos_catalogo_set,
            self.codigos_catalogo_norm_set
        )

        decision = self._custom_dialog_codigo_existente(codigo, desc_cat, siguiente_codigo)

        if decision == "cancelar":
            return False
        elif decision == "reemplazar":
            return True
        elif decision == "siguiente":
            self.var_codigo_actual.set(siguiente_codigo)
            return True

        return False

    def _ir_a_paso2(self):
        if self.df_catalogo is None or self._catalogo_cargando:
            messagebox.showwarning("Listado pendiente", "Espera a que termine la comprobación o actualiza el listado.")
            return
        codigo = self.var_codigo_inicial.get().strip().upper()
        if not re.fullmatch(r"A[0-9]{6}", codigo):
            messagebox.showwarning("Revisa el código", "Usa A seguida de 6 números, por ejemplo A022767.")
            return
        self.var_codigo_actual.set(codigo)
        if not self.validar_codigo_inicial():
            return
        self.var_codigo_inicial.set(self.var_codigo_actual.get())
        self._mostrar_paso(2)

    def _procesar_y_ir_a_paso3(self):
        if not self._actualizar_pegado_articulos():
            messagebox.showwarning("Revisa las columnas", "Completa los datos marcados antes de continuar.")
            return
        exito = self.procesar_lista_paso2()
        if exito:
            self._ir_a_paso3()

    def _ir_a_paso3(self):
        self._refrescar_tabla()
        self._mostrar_paso(3)

    def _abrir_instrucciones(self):
        top = tk.Toplevel(self)
        top.title("Guía de ingreso masivo")
        top.configure(background=UI["background"])
        top.geometry("720x430")
        try:
            top.update_idletasks()
            x = self.winfo_rootx() + max(0, (self.winfo_width() - top.winfo_width()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - top.winfo_height()) // 2)
            top.geometry(f"+{x}+{y}")
        except Exception:
            pass

        body = ttk.Frame(top, padding=20)
        body.pack(fill="both", expand=True)
        _page_heading(body, "Cómo preparar el ingreso masivo", "Sigue los tres pasos antes de guardar el archivo.")
        steps = (
            ("1. Confirmar listado", "Actualiza el listado de Tivendo y revisa la fecha. Se continúa después del mayor A + 6 números activo, excluyendo NO DISPONIBLE. La categoría es opcional y queda vacía."),
            ("2. Pegar artículos", "Copia de Excel nombre, precio y barra interna. La cuarta columna, código de proveedor, es opcional. Usa Pegar tabla de Excel o pega las columnas por separado. El ejemplo es para practicar y no se exporta."),
            ("3. Revisar y guardar", "Corrige con doble clic y guarda el Excel. Después impórtalo en el ingreso masivo de Tivendo. Guardarlo aquí todavía no crea artículos. Se necesitan al menos dos filas."),
        )
        for title, detail in steps:
            ttk.Label(body, text=title, style="Section.TLabel").pack(anchor="w", pady=(4, 0))
            ttk.Label(body, text=detail, style="Muted.TLabel", wraplength=650,
                      justify="left").pack(anchor="w", pady=(2, 10))
        ttk.Button(body, text="Cerrar", command=top.destroy,
                   style="Primary.TButton").pack(anchor="e")

    def generar_excel(self):
        if self._modo_ejemplo:
            messagebox.showinfo("Modo práctica", "Vuelve a Pegar artículos, limpia el ejemplo y pega los datos reales para guardar un Excel.")
            return
        if self._errores_preview_articulos():
            messagebox.showwarning("Revisa los datos", "Corrige las filas marcadas en rojo antes de guardar el Excel.")
            return
        if self.df_import.empty:
            messagebox.showwarning("Atención", "No hay artículos para generar el archivo.")
            return

        nombre_defecto = self.var_nombre_archivo_salida.get().strip() or "ingreso_masivo_articulos.xlsx"

        ruta = filedialog.asksaveasfilename(
            title="Guardar archivo de ingreso masivo",
            defaultextension=".xlsx",
            initialfile=nombre_defecto,
            filetypes=[("Excel", "*.xlsx")]
        )
        if not ruta:
            return

        try:
            # Usar directamente las columnas del DataFrame — idénticas al orden de ingreso
            columnas_orden = list(self.df_import.columns)
            df_salida = self.df_import[columnas_orden].copy()

            df_salida["Código"] = df_salida["Código"].astype(str).str.strip()
            mask_codigo_valido = df_salida["Código"].str.len() > 0
            mask_codigo_valido &= df_salida["Código"].str.lower() != "nan"
            df_salida = df_salida[mask_codigo_valido].copy()

            df_salida = df_salida.dropna(how="all")
            df_salida = df_salida.reset_index(drop=True)

            if len(df_salida) < 2:
                messagebox.showwarning(
                    "Atención",
                    "Tivendo exige un mínimo de 2 artículos para el ingreso masivo.\n\n"
                    f"Actualmente tienes {len(df_salida)} artículos válidos en la lista."
                )
                return

            df_salida["Precio"] = pd.to_numeric(df_salida["Precio"], errors="coerce")

            for col in ["Código barra interno", "Código barra externo", "Id Categoría"]:
                try:
                    df_salida[col] = pd.to_numeric(df_salida[col], errors="ignore")
                except Exception:
                    pass

            with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
                df_salida.to_excel(writer, index=False)

            messagebox.showinfo("Excel listo para importar", f"Se guardaron {len(df_salida)} artículos en:\n{ruta}\n\nSiguiente: importa este Excel en el ingreso masivo de artículos de Tivendo.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el archivo.\n\nDetalle: {e}")

    def _errores_preview_articulos(self):
        errors = set()
        for index, row in self.df_import.iterrows():
            if (not str(row["Nombre"]).strip() or not str(row["Código barra interno"]).strip()
                    or not re.fullmatch(r"[0-9]+", str(row["Precio"]).strip())
                    or not re.fullmatch(r"A[0-9]{6}", str(row["Código"]))):
                errors.add(index)
        return errors

    def _refrescar_tabla(self):
        if not self.tree:
            return
        total = len(self.df_import)
        errors = self._errores_preview_articulos()
        ready = total >= 2 and not errors and not self._modo_ejemplo
        summary = ("PRÁCTICA · No se exporta. Vuelve y pega tus datos reales." if self._modo_ejemplo else
                   f"{total} artículo(s) · " + (f"{len(errors)} fila(s) por corregir" if errors else
                   "Listo para guardar" if total >= 2 else "Se necesitan al menos 2 para guardar"))
        if total:
            summary += f" · {self.df_import.iloc[0]['Código']} → {self.df_import.iloc[-1]['Código']}"
            summary += " · " + ("Categoría: " + self.var_empresa_nombre.get() if self.var_empresa_nombre.get() else "Sin categoría")
        self.lbl_resumen_ingreso.config(
            text=summary,
            style="Success.TLabel" if ready else "Warning.TLabel",
        )
        self.btn_generar_articulos.config(state="normal" if ready else "disabled")
        self.tree.delete(*self.tree.get_children())
        ins = self.tree.insert
        for idx, row_vals in enumerate(self.df_import.itertuples(index=False, name=None)):
            tag = "error_fila" if idx in errors else "fila_par" if idx % 2 == 0 else "fila_impar"
            ins("", "end", values=row_vals, tags=(tag,))
        self._ajustar_anchos_columnas()

    def _start_async_catalogo_load(self, ruta):
        """Carga el catálogo en un hilo para no congelar la apertura."""
        self._catalogo_job += 1
        job = self._catalogo_job
        self._catalogo_cargando = True
        self.btn_actualizar_catalogo.config(state="disabled")
        self._actualizar_estado_codigo()
        try:
            self.master.config(cursor="watch")
        except Exception:
            pass

        def worker():
            err = None
            result = None
            try:
                result = self._parse_catalogo_for_sets(ruta)
            except Exception as e:
                err = str(e)

            def apply():
                if not self.winfo_exists() or job != self._catalogo_job:
                    return
                try:
                    self.master.config(cursor="")
                except Exception:
                    pass

                if err:
                    self._catalogo_cargando = False
                    self.btn_actualizar_catalogo.config(state="normal")
                    self.lbl_catalogo_estado.config(text="No se pudo comprobar el listado")
                    self.lbl_ultimo_articulo.config(text=err, style="Card.Warning.TLabel")
                    self._actualizar_estado_codigo()
                    return

                try:
                    df_catalogo, set_cod, set_norm = result
                    self._aplicar_catalogo(ruta, df_catalogo)
                except Exception:
                    pass

            try:
                self.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _parse_catalogo_for_sets(self, ruta):
        """Lee el catálogo y devuelve (df_catalogo, codigos_set, codigos_norm_set). No toca la UI."""
        df_catalogo = leer_catalogo_articulos(ruta)

        cod_series = df_catalogo["codigo"].astype(str).str.strip()
        codigos_set = set(cod_series)
        codigos_norm_set = set(cod_series.map(normalizar_codigo_catalogo))
        return df_catalogo, codigos_set, codigos_norm_set

    def agregar_articulo(self, refrescar=True):
        codigo = self.var_codigo_actual.get().strip()
        nombre = self.var_nombre.get().strip().upper()
        precio = self.var_precio.get().strip()
        cod_int = self.var_cod_barra_int.get().strip()
        cod_ext = self.var_cod_barra_ext.get().strip()
        empresa_nombre = self.var_empresa_nombre.get()

        if not codigo:
            messagebox.showwarning("Atención", "Debes ingresar el código identificador inicial (Paso 1).")
            return
        if not re.fullmatch(r"A[0-9]{6}", codigo):
            messagebox.showwarning("Código fuera de secuencia", "El código debe tener A + 6 números. Revisa el código inicial y la cantidad de artículos.")
            return
        if not nombre:
            messagebox.showwarning("Atención", "Debes ingresar el Nombre del artículo.")
            return
        if not precio:
            messagebox.showwarning("Atención", "Debes ingresar el Precio.")
            return
        if not cod_int:
            messagebox.showwarning("Atención", "Debes ingresar el Código de barra interno.")
            return

        if self.var_usar_mismo_codigo.get():
            cod_ext = cod_int

        solo_digitos = _RE_NO_DIGITS.sub("", precio)  # precio ya es str.strip() desde arriba
        if not solo_digitos:
            messagebox.showwarning("Atención", f"El precio '{precio}' no es válido.")
            return

        precio_int = int(solo_digitos)  # garantizado solo dígitos por _RE_NO_DIGITS

        if self.df_catalogo is not None and (self.codigos_catalogo_set or self.codigos_catalogo_norm_set):
            codigo_norm = normalizar_codigo_catalogo(codigo)
            existe_directo = codigo in self.codigos_catalogo_set
            existe_normalizado = codigo_norm in self.codigos_catalogo_norm_set

            if existe_directo or existe_normalizado:
                    desc_cat = ""
                    if not existe_directo:
                        df_filtrado = self.df_catalogo[
                            self.df_catalogo["codigo"].astype(str).apply(normalizar_codigo_catalogo) == codigo_norm
                        ]
                    else:
                        df_filtrado = self.df_catalogo[
                            self.df_catalogo["codigo"].astype(str).str.strip() == codigo
                        ]

                    if not df_filtrado.empty:
                        fila = df_filtrado.iloc[0]
                        desc_cat = f"{fila['nombre']} (Precio: {fila['precio']})"

                    siguiente_codigo = buscar_siguiente_codigo_disponible(
                        codigo,
                        self.codigos_catalogo_set,
                        self.codigos_catalogo_norm_set
                    )

                    decision = self._custom_dialog_codigo_existente(codigo, desc_cat, siguiente_codigo)
                    if decision == "cancelar":
                        return
                    elif decision == "siguiente":
                        codigo = siguiente_codigo
                        self.var_codigo_actual.set(codigo)
                    # decision == "reemplazar" → continuar con el código actual

        item_code = (cod_ext if cod_ext else cod_int).strip()

        if item_code:
            nombre_final = f"{nombre} - {item_code}"
            cod_barra_externo_final = f"MH{item_code}"
        else:
            nombre_final = nombre
            cod_barra_externo_final = ""

        id_categoria = self.empresas_name_to_id.get(empresa_nombre, "")

        nueva_fila = {
            "Código": codigo,
            "Nombre": nombre_final,
            "Unidad": "UN",
            "Precio": precio_int,
            "Código barra interno": cod_int,
            "Código barra externo": cod_barra_externo_final,
            "Descripción": nombre_final,
            "Es Servicio": "No",
            "Es Exento": "No",
            "Impuesto Específico": "",
            "Id Categoría": id_categoria,
            "Disponible venta": "Si",
            "Activo": "Si",
            "Utilidad": "",
            "Tipo Utilidad": "",
            "Palabras Clave": "",
        }

        self.df_import = pd.concat(
            [self.df_import, pd.DataFrame([nueva_fila])],
            ignore_index=True
        )
        if refrescar:
            self._refrescar_tabla()

        nuevo_codigo = buscar_siguiente_codigo_disponible(
            codigo, self.codigos_catalogo_set, self.codigos_catalogo_norm_set)
        self.var_codigo_actual.set(nuevo_codigo)

        self.limpiar_campos()

    def _back_home(self):
        """Vuelve al menú principal y cierra esta vista de ingreso masivo."""
        self.destroy()
        if callable(self.go_home_cb):
            self.go_home_cb()

    def limpiar_campos(self):
        """Limpia los campos de entrada del PASO 1 (uso manual).
        No toca los textos del PASO 2 para no interferir con el ingreso masivo.
        """
        self.var_nombre.set("")
        self.var_precio.set("")
        self.var_cod_barra_int.set("")
        self.var_cod_barra_ext.set("")

    def procesar_lista_paso2(self) -> bool:
        if not self._actualizar_pegado_articulos():
            messagebox.showwarning("Revisa las columnas", "Completa los datos marcados en rojo antes de revisar los artículos.")
            return False
        codigo_inicial = self.var_codigo_inicial.get().strip()
        if not codigo_inicial:
            messagebox.showwarning(
                "Atención",
                "Debes ingresar primero el código identificador inicial en el PASO 1 antes de procesar la lista."
            )
            return False

        lineas_nombre = [l.strip() for l in self.text_nombre.get("1.0", "end").splitlines()]
        lineas_precio = [l.strip() for l in self.text_precio.get("1.0", "end").splitlines()]
        lineas_codint = [l.strip() for l in self.text_codint.get("1.0", "end").splitlines()]
        lineas_codext = [l.strip() for l in self.text_codext.get("1.0", "end").splitlines()]

        # Reiniciamos la tabla interna para que, si el usuario vuelve desde la vista previa
        # y presiona nuevamente 'Siguiente', no se dupliquen las filas. Se vuelve a construir
        # todo desde los textos actuales del PASO 2.
        self.df_import = self.df_import.head(0).copy()
        max_filas = max(len(lineas_nombre), len(lineas_precio), len(lineas_codint), len(lineas_codext))
        if max_filas == 0:
            messagebox.showwarning("Atención", "No hay líneas para procesar en el Paso 2.")
            return False

        total_filas = 0
        agregados_ok = 0

        self.var_codigo_actual.set(codigo_inicial)

        for i in range(max_filas):
            fila_num = i + 1

            nombre = lineas_nombre[i] if i < len(lineas_nombre) else ""
            precio = lineas_precio[i] if i < len(lineas_precio) else ""
            cod_int = lineas_codint[i] if i < len(lineas_codint) else ""
            cod_ext = lineas_codext[i] if i < len(lineas_codext) else ""

            if not nombre and not precio and not cod_int and not cod_ext:
                continue

            total_filas += 1

            errores = []
            if not nombre:
                errores.append("Nombre vacío")
            if not precio:
                errores.append("Precio vacío")
            if not cod_int:
                errores.append("Código barra interno vacío")

            if errores:
                messagebox.showerror(
                    "Error en datos",
                    f"Fila {fila_num}: {', '.join(errores)}.\n\n"
                    "Corrige estos datos antes de continuar."
                )
                return False

            solo_digitos = _RE_NO_DIGITS.sub("", str(precio).strip())
            if not solo_digitos:
                messagebox.showerror(
                    "Error en datos",
                    f"Fila {fila_num}: el precio '{precio}' no es válido.\n\n"
                    "Corrige el valor del precio antes de continuar."
                )
                return False

            self.var_nombre.set(nombre)
            self.var_precio.set(str(precio))
            self.var_cod_barra_int.set(str(cod_int))

            cod_int_str = str(cod_int).strip()
            cod_ext_str = str(cod_ext).strip() if cod_ext else ""

            if cod_ext_str and cod_ext_str != cod_int_str:
                self.var_usar_mismo_codigo.set(False)
                self.var_cod_barra_ext.set(cod_ext_str)
            else:
                self.var_usar_mismo_codigo.set(True)
                self.var_cod_barra_ext.set("")

            filas_antes = len(self.df_import)
            self.agregar_articulo(refrescar=False)
            filas_despues = len(self.df_import)

            if filas_despues > filas_antes:
                agregados_ok += 1
            else:
                messagebox.showerror(
                    "Error al agregar artículo",
                    f"Fila {fila_num}: el artículo no se pudo agregar.\n\n"
                    "Revisa los mensajes anteriores (por ejemplo, cancelaste el código existente)\n"
                    "y corrige los datos antes de continuar."
                )
                return False

        if agregados_ok == 0:
            messagebox.showwarning(
                "Atención",
                "No se agregó ningún artículo desde la lista.\n"
                "Revisa los datos ingresados en el Paso 2."
            )
            return False

        self._refrescar_tabla()
        return True

    def limpiar_textos_paso2(self):
        self._modo_ejemplo = False
        self.text_nombre.delete("1.0", "end")
        self.text_precio.delete("1.0", "end")
        self.text_codint.delete("1.0", "end")
        self.text_codext.delete("1.0", "end")
        self._actualizar_pegado_articulos()

def main():
    app = RootApp()
    app.mainloop()

if __name__ == "__main__":
    main()


