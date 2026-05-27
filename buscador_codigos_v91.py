#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Buscador + Convertidor con gestión de Proveedores integrada (v91)
- v91: motor de búsqueda mejorado — 5 mejoras.
    * Ranking de relevancia: resultados ordenados por score (exacto > empieza-con
      > token exacto > contiene en código > contiene en nombre > barcode).
    * Tolerancia a errores tipográficos: cuando no hay resultados, se sugieren
      códigos similares usando difflib (stdlib, sin dependencias nuevas).
    * Índice invertido en memoria: precalculado al cargar la base, acelera
      búsquedas de tokens exactos de O(n) a O(1).
    * Historial de búsquedas por sesión: botón "Historial" abre ventana con
      las últimas 20 búsquedas; doble-click reutiliza cualquiera.
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
import threading
import tempfile
import atexit
import unicodedata
import difflib
import numpy as np
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
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

STRIPE_COLOR = "#f5f5f5"  # gris suave para franjas en Tivendo
MAX_RESULTS  = 500        # máximo de filas mostradas en el buscador
TMP_DIR      = Path(tempfile.gettempdir())  # directorio temporal del sistema

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
    CACHE_DIR = Path(LOCAL_APPDATA) / "BuscadorCodigos" / ".cache"
else:
    CACHE_DIR = HERE / ".cache"
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
CACHE_DB_PATH = CACHE_DIR / "base_codigos_cache.pkl"
CACHE_DB_META = CACHE_DIR / "base_codigos_cache_meta.json"

# Limpieza automática de archivos temporales de BASE DE DATOS al salir
def _cleanup_tmp_bases():
    try:
        for f in TMP_DIR.glob("MH_TMP_BASE_*.xlsx"):
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass

atexit.register(_cleanup_tmp_bases)
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
    "Código": "codigo", "Nombre": "nombre", "Unidad": "unidad",
    "Código barra interno": "barcode_interno",
    "Código barra externo": "barcode_externo",
    "Descripción": "descripcion", "Id Categoría2": "empresa_id_raw",
}
_EXCEL_KEEP = ["codigo", "nombre", "barcode_interno", "barcode_externo", "empresa_id_raw"]

def _parse_excel_base(path) -> pd.DataFrame:
    """Lee la hoja BASE DE DATOS de un Excel y devuelve DataFrame normalizado."""
    with pd.ExcelFile(path, engine="openpyxl") as xf:
        base = xf.parse("BASE DE DATOS")
    base = base.rename(columns=_EXCEL_COL_RENAME)
    keep = [c for c in _EXCEL_KEEP if c in base.columns]
    return base[keep].fillna("").astype(str)


def _extract_id(val) -> str:
    """Extrae primer grupo de dígitos de val; usado para normalizar empresa_id."""
    m = _RE_DIGITS.search(str(val))
    return m.group(1) if m else ""

def _make_nf_row(code: str, pos: int) -> pd.DataFrame:
    """Crea una fila 'No encontrado' para el buscador."""
    return pd.DataFrame([{
        "codigo": code, "nombre": "No encontrado",
        "barcode_interno": "", "barcode_externo": "",
        "empresa_id": "", "__input": code, "__pos": pos, "__rank": 0
    }])

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

    for c in ["codigo", "nombre", "barcode_interno", "barcode_externo", "empresa_id"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].fillna("").astype(str)

    df["_codigo_lc"] = df["codigo"].str.lower().str.strip()
    # Código normalizado sólo en espacios (no se eliminan): colapsa espacios múltiples a uno
    df["_codigo_ws"] = df["codigo"].astype(str).str.strip().apply(lambda s: _ws_re.sub(" ", s))
    df["_nombre_lc"] = df["nombre"].map(_norm_lc)
    # Tokens multi-código por "/"
    try:
        df["_codigo_tokens"] = df["codigo"].apply(split_codes_by_slash)
        df["_codigo_tokens_norm"] = df["_codigo_tokens"].apply(to_normalized_tokens)
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
TARGET_ORDER = ["Código","Nombre","Unidad","Código barra interno","Código barra externo","Descripción","Id Categoría2"]

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

def transform_export(df: pd.DataFrame, progress_cb=None) -> pd.DataFrame:
    if progress_cb: progress_cb(35, "Limpiando columnas…")
    drop_now = [c for c in DROP_COLUMNS if c in df.columns]
    if drop_now:
        df = df.drop(columns=drop_now, errors='ignore')

    needed = ["Código","Nombre","Unidad","Código barra interno","Código barra externo","Descripción","Id Categoría"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"No se encontraron columnas requeridas en el export: {missing}")

    if progress_cb: progress_cb(45, "Reordenando y renombrando…")
    out = df[needed].copy().rename(columns={"Id Categoría":"Id Categoría2"})

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
                   exact: bool, by_barras: bool,
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

    Returns:
        DataFrame con columna __score, ordenado score desc. Vacío si sin resultados.
    """
    q_ws_lc = q_ws.lower()
    q_name  = _norm_lc(q_ws)
    n       = len(df)
    scores  = np.zeros(n, dtype=np.int32)

    if exact:
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
        m_exact = (df["_codigo_ws"].str.lower() == q_ws_lc).values
        scores[m_exact] = 100

        m_starts = df["_codigo_lc"].str.startswith(q_ws_lc, na=False).values
        scores[m_starts & (scores < 80)] = 80

        if tok_index is not None and q_norm in tok_index:
            tok_mask = df.index.isin(tok_index[q_norm])
            scores[tok_mask & (scores < 60)] = 60
        else:
            for i, toks in enumerate(df["_codigo_tokens_norm"]):
                if scores[i] < 60 and any(tok == q_norm for tok in toks):
                    scores[i] = 60

        m_code = df["_codigo_lc"].str.contains(re.escape(q_ws_lc), na=False).values
        scores[m_code & (scores < 40)] = 40

        if len(q_norm) >= 3:
            for i, toks in enumerate(df["_codigo_tokens_norm"]):
                if scores[i] < 35 and any(q_norm in tok for tok in toks):
                    scores[i] = 35

        m_name = df["_nombre_lc"].str.contains(re.escape(q_name), na=False).values
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

class StartView(ttk.Frame):
    """Pantalla de inicio SIN vista previa de proveedores."""
    def __init__(
        self,
        master,
        on_choose_db,
        on_manage_prov,
        on_open_tivendo,
        on_open_ingreso_masivo,
        on_load_listado,
        listado_cargado: bool,
    ):
        super().__init__(master)
        self.master.title("Buscador de Códigos — MERCADO HOUSE")
        self.pack(fill="both", expand=True, padx=20, pady=20)

        title = ttk.Label(self, text="¿Qué deseas hacer?", font=("TkDefaultFont", 14, "bold"))
        title.pack(pady=(0, 12))

        btns = ttk.Frame(self)
        btns.pack(pady=8)

        # Guardamos referencias a los botones que dependen del listado
        self.btn_buscar = ttk.Button(btns, text="Buscar Código", command=on_choose_db)
        self.btn_buscar.pack(side="left", padx=8, ipadx=10, ipady=6)

        self.btn_prov = ttk.Button(btns, text="Administrar proveedores", command=on_manage_prov)
        self.btn_prov.pack(side="left", padx=8, ipadx=10, ipady=6)

        self.btn_tivendo = ttk.Button(btns, text="CAMBIOS MASIVOS DE PRECIOS", command=on_open_tivendo)
        self.btn_tivendo.pack(side="left", padx=8, ipadx=10, ipady=6)

        self.btn_ingreso = ttk.Button(btns, text="INGRESO MASIVO DE ARTICULOS", command=on_open_ingreso_masivo)
        self.btn_ingreso.pack(side="left", padx=8, ipadx=10, ipady=6)

        # Botón central para cargar el listado al inicio
        self.btn_cargar_listado = ttk.Button(
            self,
            text="Primero cargue el LISTADO DE ARTICULOS para usar el programa",
            command=on_load_listado,
        )
        self.btn_cargar_listado.pack(pady=(18, 8))

        # Etiqueta de estado + botones (delegado a set_listado_cargado)
        self.lbl_estado = ttk.Label(self, text="", foreground="#555")
        self.lbl_estado.pack(pady=(4, 0), anchor="w")
        self.set_listado_cargado(listado_cargado)

    @staticmethod
    def _estado_texto(cargado: bool) -> str:
        return ("Listado de artículos: CARGADO" if cargado
                else "Listado de artículos: NO cargado (los módulos que dependen de él están deshabilitados)")

    def set_listado_cargado(self, cargado: bool):
        """Habilita/deshabilita los botones que necesitan el listado de artículos
        y actualiza el texto de estado en pantalla."""
        state_dep = "normal" if cargado else "disabled"
        self.btn_buscar.config(state=state_dep)
        self.btn_tivendo.config(state=state_dep)
        self.btn_ingreso.config(state=state_dep)
        try:
            self.lbl_estado.config(text=self._estado_texto(cargado))
        except Exception:
            pass

class ProvidersView(ttk.Frame):
    """CRUD de proveedores (sin importar desde Excel)."""
    def __init__(self, master, go_home_cb):
        super().__init__(master)
        self.master.title("Administrar proveedores")
        self.pack(fill="both", expand=True, padx=12, pady=12)
        self.go_home_cb = go_home_cb
        self.data: Dict[int,str] = load_empresas()

        top = ttk.Frame(self); top.pack(fill="x")
        ttk.Button(top, text="⟵ Volver al inicio", command=self._back_home).pack(side="left")

        mid = ttk.Frame(self); mid.pack(fill="both", expand=True, pady=8)
        self.tree = ttk.Treeview(mid, columns=("id","nombre"), show="headings", selectmode="browse", height=20)
        self.tree.heading("id", text="Id"); self.tree.column("id", width=90, anchor="center")
        self.tree.heading("nombre", text="Nombre"); self.tree.column("nombre", width=520, anchor="w")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview); self.tree.configure(yscroll=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True); vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.LabelFrame(self, text="Editar / Agregar"); form.pack(fill="x", pady=6)
        row = ttk.Frame(form); row.pack(fill="x", pady=4, padx=8)
        ttk.Label(row, text="Id:").pack(side="left")
        self.ent_id = ttk.Entry(row, width=12); self.ent_id.pack(side="left", padx=(4,10))
        ttk.Label(row, text="Nombre:").pack(side="left")
        self.ent_nombre = ttk.Entry(row); self.ent_nombre.pack(side="left", fill="x", expand=True, padx=(4,10))

        actions = ttk.Frame(form); actions.pack(fill="x", pady=4, padx=8)
        ttk.Button(actions, text="Guardar / Actualizar", command=self.save_item).pack(side="left", padx=4)
        ttk.Button(actions, text="Nuevo", command=self.clear_form).pack(side="left", padx=4)
        ttk.Button(actions, text="Eliminar", command=self.delete_item).pack(side="left", padx=4)

        self.status = ttk.Label(self, text="", foreground="#666"); self.status.pack(fill="x", pady=(4,0))
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
    def __init__(self, master, go_home_cb, initial_db_path: Optional[Path]):
        super().__init__(master)
        self.master.title("Buscador de Códigos — MERCADO HOUSE (v91)")
        self.pack(fill="both", expand=True)
        self.go_home_cb = go_home_cb
        self.prefs = load_prefs()
        self.db_path: Optional[Path] = None  # inicializado explícitamente

        # Carga de datos
        try:
            self.df, self.empresas = load_data(initial_db_path)
            self.db_path = initial_db_path
        except Exception as e:
            messagebox.showerror("Error al cargar datos", str(e))
            self.destroy(); go_home_cb(); return

        self.last_results = pd.DataFrame()
        self._history: deque = deque(maxlen=20)

        # ===== Barra superior SOLO con "Volver" =====
        header = ttk.Frame(self, padding=(10,10,10,0))
        header.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(header, text="Volver al Menú", command=self._back_home).pack(side="left")

        # ===== Contenido del buscador =====
        content = ttk.Frame(self, padding=10)
        content.pack(side=tk.TOP, fill=tk.X)
        content.columnconfigure(0, weight=1)

        ttk.Label(content, text="Código(s) (pega varios: uno por línea o separados por coma/tab):").grid(row=0, column=0, sticky="w")
        area = ttk.Frame(content); area.grid(row=1, column=0, sticky="ew", pady=(4,0))
        area.columnconfigure(0, weight=1)
        self.txt_query = tk.Text(area, height=5, wrap="word")
        self.txt_query.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(area, orient="vertical", command=self.txt_query.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.txt_query.configure(yscrollcommand=vsb.set)

        opts = ttk.Frame(content); opts.grid(row=2, column=0, sticky="w", pady=(6,0))
        self.exact = tk.BooleanVar(value=bool(self.prefs.get("exact", True)))
        self.by_barras = tk.BooleanVar(value=bool(self.prefs.get("by_barras", False)))
        ttk.Checkbutton(opts, text="Coincidencia exacta (código)", variable=self.exact).pack(side="left")
        ttk.Checkbutton(opts, text="Buscar por códigos de barra", variable=self.by_barras).pack(side="left", padx=(12,0))

        row3 = ttk.Frame(content); row3.grid(row=3, column=0, sticky="w", pady=(8,0))
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
        self.cbo_emp.set(self.prefs.get("empresa_display", "— Cualquiera —"))
        self.cbo_emp.bind("<Key>", self.on_emp_key)

        btns = ttk.Frame(row3)
        btns.pack(side="left")
        ttk.Button(btns, text="Buscar por Proveedor", command=self.on_search).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Buscar general", command=lambda: self.on_search(force_general=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Limpiar", command=self.on_clear).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Historial", command=self._show_history).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Copiar cód.barra (internos)", command=self.copy_barcodes_internos).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Copiar cód.barra (externos)", command=self.copy_barcodes_externos).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Copiar nombres + cod.barra", command=self.copy_nombre_interno).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Copiar nombres", command=self.copy_nombres).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Copiar NO ENCONTRADOS", command=self.copy_not_found_inputs).pack(side=tk.LEFT, padx=4)

        cols = ("codigo","nombre","barcode_interno","barcode_externo","empresa","__input")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        for c, t in zip(cols, ["Código","Nombre","Cód. barra interno","Cód. barra externo","Empresa","Código buscado"]):
            self.tree.heading(c, text=t)
        self.tree.column("codigo", width=180, anchor="w")
        self.tree.column("nombre", width=420, anchor="w")
        self.tree.column("barcode_interno", width=180, anchor="w")
        self.tree.column("barcode_externo", width=180, anchor="w")
        self.tree.column("empresa", width=240, anchor="w")
        self.tree.column("__input", width=200, anchor="w")
        self.tree.tag_configure("dup_input", background="#FFF3CD")

        vsb2 = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb2 = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb2.set, xscroll=hsb2.set)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(8,10))
        vsb2.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")
        hsb2.pack(side=tk.BOTTOM, fill=tk.X)

        self.var_status = tk.StringVar(value=self.status_db_text)
        lbl_status = ttk.Label(self, textvariable=self.var_status, anchor="w", cursor="hand2")
        lbl_status.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        lbl_status.bind("<Button-1>", lambda e: self.on_change_db())  # click para cambiar BD

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copiar fila(s) seleccionada(s)", command=self.copy_selected_rows)
        self.menu.add_command(label="Eliminar de la lista", command=self.remove_selected_rows)
        self.tree.bind("<Button-3>", self.show_context_menu)

        self.bind_all("<Return>", lambda e: self.on_search())
        self.bind_all("<Control-s>", lambda e: self.export_csv())
        self.bind_all("<Control-l>", lambda e: self.on_clear())
        self.tree.bind("<Control-c>", lambda e: self.copy_selected_rows())
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
            if iid:
                if iid not in self.tree.selection():
                    self.tree.selection_set(iid)
                self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

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
        prefer = self.prefs.get("empresa_display", "— Cualquiera —")
        self.cbo_emp.set(prefer if prefer in self.cbo_emp["values"] else "— Cualquiera —")
        for x in self.tree.get_children(): self.tree.delete(x)
        self.var_status.set(self.status_db_text)
        self.last_results = pd.DataFrame()

    def _show_history(self):
        """Abre una ventana con el historial de búsquedas de la sesión."""
        if not self._history:
            messagebox.showinfo("Historial", "No hay búsquedas en el historial todavía.")
            return
        top = tk.Toplevel(self)
        top.title("Historial de búsquedas")
        top.resizable(False, False)
        ttk.Label(top, text="Doble clic para repetir la búsqueda:").pack(padx=12, pady=(10,4), anchor="w")
        lb = tk.Listbox(top, width=60, height=min(len(self._history), 15), selectmode="browse")
        lb.pack(padx=12, pady=(0,4), fill="both", expand=True)
        for entry in self._history:
            lb.insert("end", entry)
        def _use(event=None):
            sel = lb.curselection()
            if not sel:
                return
            query = lb.get(sel[0])
            top.destroy()
            self.txt_query.delete("1.0", "end")
            self.txt_query.insert("1.0", query)
            self.on_search()
        lb.bind("<Double-Button-1>", _use)
        ttk.Button(top, text="Usar seleccionado", command=_use).pack(pady=(0,10))
        top.grab_set()

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

    def populate(self, df, emp_id, not_found_count=0):
        """Rellena el Treeview con los resultados de búsqueda y actualiza la barra de estado."""
        for x in self.tree.get_children(): self.tree.delete(x)
        total = len(df)

        dup_inputs = set()
        if "__input" in df.columns:
            inp_series = df["__input"].fillna("").astype(str).str.strip()
            if not inp_series.empty:
                counts = inp_series[inp_series != ""].value_counts()
                dup_inputs = set(counts[counts > 1].index)

        # Extraer columnas como listas (mucho más rápido que iterrows)
        col_codigo    = df["codigo"].fillna("").astype(str).tolist() if "codigo" in df.columns else [""] * total
        col_nombre    = df["nombre"].fillna("").astype(str).tolist() if "nombre" in df.columns else [""] * total
        col_bi        = df["barcode_interno"].fillna("").astype(str).tolist() if "barcode_interno" in df.columns else [""] * total
        col_be        = df["barcode_externo"].fillna("").astype(str).tolist() if "barcode_externo" in df.columns else [""] * total
        col_eid       = df["empresa_id"].fillna("").astype(str).tolist() if "empresa_id" in df.columns else [""] * total
        col_inp       = df["__input"].fillna("").astype(str).tolist() if "__input" in df.columns else [""] * total

        ins = self.tree.insert
        disp = self._display_emp
        for cod, nom, bi, be, eid, inp in zip(col_codigo, col_nombre, col_bi, col_be, col_eid, col_inp):
            emp_txt = "" if nom == "No encontrado" else disp(eid)
            tags = ("dup_input",) if inp.strip() in dup_inputs else ()
            ins("", "end", values=(cod, nom, bi, be, emp_txt, inp), tags=tags)

        extra = ""
        if not_found_count: extra += f" | No encontrados: {not_found_count}"
        if dup_inputs: extra += f" | Duplicados (por código ingresado): {len(dup_inputs)}"
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
        tok_index = _LOAD_DATA_CACHE.get("index")

        if len(codes) == 1:
            q      = codes[0]
            q_ws   = _ws_re.sub(" ", q).strip()
            q_norm = normalize_code_token(q_ws)
            out    = _score_results(df, q, q_ws, q_norm, exact, by_barras, tok_index)
            if out.empty:
                suggs = _find_fuzzy_suggestions(q_norm, df)
                if suggs:
                    hint = "  ¿Quisiste decir: " + ", ".join(suggs) + "?"
                else:
                    hint = ""
                self.populate(_make_nf_row(q, 0), emp_id, not_found_count=1)
                self.var_status.set(f"{self.status_db_text} | No encontrado: {q}.{hint}")
                return
            out = out.drop(columns=["__score"])
            out["__input"] = q
            self._history.appendleft(q)
            self.populate(out.head(MAX_RESULTS), emp_id)
            return

        frames, nf = [], 0
        for i, code in enumerate(codes):
            code_ws = _ws_re.sub(" ", str(code)).strip()
            if not code_ws:
                continue
            code_norm = normalize_code_token(code_ws)
            sub = _score_results(df, code, code_ws, code_norm, exact, by_barras, tok_index)
            if sub.empty:
                frames.append(_make_nf_row(code, i))
                nf += 1
            else:
                sub["__input"] = code
                sub["__pos"]   = i
                frames.append(sub)

        if not frames:
            self.populate(
                pd.DataFrame(columns=["codigo","nombre","barcode_interno","barcode_externo","empresa_id","__input"]),
                emp_id, not_found_count=nf,
            )
            return

        out = (
            pd.concat(frames, ignore_index=True)
              .sort_values(["__pos", "__score"], ascending=[True, False])
        )
        drop_cols = [c for c in ("__score", "__pos") if c in out.columns]
        if drop_cols:
            out = out.drop(columns=drop_cols)
        raw_query = raw.strip()
        if raw_query:
            self._history.appendleft(raw_query)
        self.populate(out.head(MAX_RESULTS), emp_id, not_found_count=nf)

    # ---- Helper de portapapeles ----
    def _copy_to_clipboard(self, text: str, status_msg: str):
        """Copia texto al portapapeles y actualiza la barra de estado."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # necesario en algunos sistemas para que el clipboard se actualice
        self.var_status.set(status_msg)

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

class ConvertView(ttk.Frame):
    """Convertidor Tivendo -> Excel con progreso; escribe LISTA desde empresas.json.

    LEGADO: esta clase no está conectada al menú principal (RootApp).
    La funcionalidad equivalente es AutoBuildDBWindow + transform_export.
    Se conserva por si se desea reactivar como vista independiente.
    """
    def __init__(self, master, go_home_cb, open_in_search_cb):
        super().__init__(master)
        self.master.title("Crear base de datos (Tivendo → Excel)")
        self.pack(fill="both", expand=True, padx=16, pady=16)
        self.go_home_cb = go_home_cb
        self.open_in_search_cb = open_in_search_cb
        self.selected_path: Optional[Path] = None
        self.last_output: Optional[Path] = None

        top = ttk.Frame(self); top.pack(fill="x")
        ttk.Button(top, text="⟵ Volver al inicio", command=self._back_home).pack(side="left")
        ttk.Label(top, text="Convertidor (BASE DE DATOS)").pack(side="left", padx=10)

        ttk.Button(self, text="Seleccionar export de Tivendo", command=self.select_file).pack(pady=(16,8))
        self.lbl_file = ttk.Label(self, text="Ningún archivo seleccionado", anchor="center"); self.lbl_file.pack(padx=12, fill="x")

        self.btn_convert = ttk.Button(self, text="Convertir", command=self.convert_action, state="disabled")
        self.btn_convert.pack(pady=(12,8))

        frm = ttk.Frame(self); frm.pack(padx=20, pady=(8,4), fill="x")
        self.progress = ttk.Progressbar(frm, mode="determinate", maximum=100); self.progress.pack(side="left", expand=True, fill="x")
        self.lbl_pct = ttk.Label(frm, text="0%"); self.lbl_pct.pack(side="left", padx=(8,0))
        self.status = ttk.Label(self, text="", anchor="center", foreground="#666"); self.status.pack(padx=12, fill="x")

        self.btn_open_in_search = ttk.Button(self, text="Abrir archivo generado en el Buscador", command=self._open_in_search, state="disabled")
        self.btn_open_in_search.pack(pady=(8,0))

    def _back_home(self):
        self.destroy(); self.go_home_cb()

    def select_file(self):
        fpath = filedialog.askopenfilename(
            title="Selecciona la Base de Datos",
            filetypes=[("Excel/CSV","*.xlsx *.xls *.xlsm *.csv"),("Todos","*.*")]
        )
        if not fpath: return
        self.selected_path = Path(fpath)
        self.lbl_file.config(text=self.selected_path.name)
        self.btn_convert.config(state="normal")
        self.status.config(text=""); self.btn_open_in_search.config(state="disabled")
        self.last_output = None
        try:
            prefs = load_prefs(); prefs["last_dir"] = str(self.selected_path.parent); save_prefs(prefs)
        except Exception:
            pass

    def set_progress(self, value: int, text: Optional[str] = None):
        value = max(0, min(100, int(value)))
        self.progress['value'] = value; self.lbl_pct.config(text=f"{value}%")
        if text is not None: self.status.config(text=text)
        self.update_idletasks()

    def convert_action(self):
        if not self.selected_path: return
        out_file = filedialog.asksaveasfilename(
            title="Guardar como", defaultextension=".xlsx",
            initialfile="BASE_ACTUALIZADA.xlsx", filetypes=[("Excel","*.xlsx")]
        )
        if not out_file: return

        self.btn_convert.config(state="disabled"); self.status.config(text="Preparando…"); self.set_progress(0, "Listo para convertir…")

        def work():
            try:
                self.after(0, lambda: self.set_progress(5, "Detectando encabezados…"))
                df = read_export_any(self.selected_path, progress_cb=lambda p,t: self.after(0, lambda: self.set_progress(p,t)))
                out_df = transform_export(df, progress_cb=lambda p,t: self.after(0, lambda: self.set_progress(p,t)))
                empresas = load_empresas(); lista_df = empresas_df_for_excel(empresas)
                self.after(0, lambda: self.set_progress(85, "Escribiendo Excel…"))
                with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
                    out_df.to_excel(writer, sheet_name="BASE DE DATOS", index=False)
                    lista_df.to_excel(writer, sheet_name="LISTA", index=False)
                self.last_output = Path(out_file)
                self.after(0, lambda: self.on_done(True, f"Archivo generado:\n{out_file}"))
            except Exception as e:
                self.after(0, lambda: self.on_done(False, f"Ocurrió un error:\n{e}"))

        threading.Thread(target=work, daemon=True).start()

    def on_done(self, success: bool, msg: str):
        self.set_progress(100 if success else 0, "Completado" if success else "Error")
        self.btn_convert.config(state="normal")
        if success:
            messagebox.showinfo("Listo", msg); self.btn_open_in_search.config(state="normal")
        else:
            messagebox.showerror("Error", msg)

    def _open_in_search(self):
        if self.last_output and self.last_output.exists():
            self.destroy(); self.open_in_search_cb(self.last_output)
        else:
            messagebox.showwarning("Atención", "No hay un archivo generado para abrir en el buscador.")

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
        self.listado_path = listado_path
        self.on_done = on_done  # callback Path|None

        self.grab_set()  # bloquear interacción con la ventana principal mientras trabaja

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(
            frm,
            text=f"Generando BASE DE DATOS desde:\n{listado_path.name}",
            justify="left"
        ).pack(anchor="w")

        frm_bar = ttk.Frame(frm)
        frm_bar.pack(fill="x", pady=(12, 4))

        self.progress = ttk.Progressbar(frm_bar, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)

        self.lbl_pct = ttk.Label(frm_bar, text="0%")
        self.lbl_pct.pack(side="left", padx=(8, 0))

        self.lbl_status = ttk.Label(frm, text="Preparando…", foreground="#555")
        self.lbl_status.pack(anchor="w", pady=(4, 0))

        # Ajuste tamaño aproximado
        self.update_idletasks()
        self.minsize(self.winfo_width(), self.winfo_height())

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
                # Reutilizamos la misma lógica que el ConvertView
                def cb(p, t):
                    self.after(0, lambda: self._set_progress(p, t or ""))

                self.after(0, lambda: self._set_progress(5, "Leyendo archivo de origen…"))
                df = read_export_any(self.listado_path, progress_cb=cb)
                out_df = transform_export(df, progress_cb=cb)
                empresas = load_empresas()
                lista_df = empresas_df_for_excel(empresas)

                # Nombre de salida en carpeta temporal del sistema
                out_file = TMP_DIR / f"MH_TMP_BASE_{self.listado_path.stem}.xlsx"

                self.after(0, lambda: self._set_progress(90, "Escribiendo archivo Excel…"))
                with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
                    out_df.to_excel(writer, sheet_name="BASE DE DATOS", index=False)
                    lista_df.to_excel(writer, sheet_name="LISTA", index=False)

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
        # Restaurar tamaño/posición si existe en prefs
        prefs = load_prefs()
        geom = prefs.get("geometry")
        try:
            self.geometry(geom if geom else "1180x780")
        except Exception:
            self.geometry("1180x780")
        self.minsize(1020, 660)

        # Ruta global del EXCEL "Listado de artículos" que usarán los módulos
        self.listado_path: Optional[Path] = None

        ensure_empresas_seed_applied()  # Sincroniza empresas.json con la semilla y conserva agregados
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # La selección del LISTADO DE ARTÍCULOS ahora se hace desde el menú principal
        self._show_start()

    def _on_close(self):
        try:
            prefs = load_prefs()
            prefs["geometry"] = self.geometry()
            save_prefs(prefs)
        except Exception:
            pass
        self.destroy()

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
            except Exception:
                pass
        if self.listado_path is not None:
            messagebox.showinfo(
                "Listado cargado",
                f"Se cargó correctamente el LISTADO DE ARTICULOS.\n\nArchivo:\n{self.listado_path.name}"
            )

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()
        self.start_view = None  # evitar referencia colgante a widget destruido

    def _show_start(self):
        self._clear()
        self.start_view = StartView(
            self,
            on_choose_db=self._choose_db_flow,
            on_manage_prov=self._manage_prov_flow,
            on_open_tivendo=self._tivendo_flow,
            on_open_ingreso_masivo=self._ingreso_masivo_flow,
            on_load_listado=self._choose_listado_inicial,
            listado_cargado=self.listado_path is not None,
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

        Optimización: si ya existe en la carpeta temporal un archivo
        MH_TMP_BASE_<nombre_listado>.xlsx generado previamente en esta sesión,
        se reutiliza en lugar de volver a crearlo.
        """
        if not self._require_listado():
            return

        # Intentar reutilizar una base temporal ya generada para este LISTADO
        try:
            candidate = TMP_DIR / f"MH_TMP_BASE_{self.listado_path.stem}.xlsx"
        except Exception:
            candidate = None

        if candidate is not None and candidate.exists():
            # Si ya existe, abrimos directamente el buscador con esa BD
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

    def _manage_prov_flow(self):
        self._clear()
        ProvidersView(self, go_home_cb=self._show_start)

    def _tivendo_flow(self):
        # Abre la herramienta de cambios masivos de precios en la ventana principal
        if not self._require_listado():
            return
        try:
            self._clear()
            TivendoWindow(self, listado_path=self.listado_path, go_home_cb=self._show_start)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la herramienta de Tivendo.\n{e}")

    def _ingreso_masivo_flow(self):
        # Abre la herramienta de ingreso masivo de artículos en la ventana principal
        if not self._require_listado():
            return
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
        SearchView(self, go_home_cb=self._show_start, initial_db_path=db_path)

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

class TivendoWindow(ttk.Frame):
    def __init__(self, master, listado_path: Optional[Path] = None, go_home_cb=None):
        super().__init__(master)
        self.master.title("Tivendo - Cambios masivos de precios (v91)")
        self.pack(fill="both", expand=True)
        self.go_home_cb = go_home_cb

        top = ttk.Frame(self)
        top.pack(fill="x")
        # Botón para volver al menú principal sin usar métodos adicionales
        ttk.Button(
            top,
            text="⟵ Volver al inicio",
            command=lambda: (self.destroy(), self.go_home_cb() if callable(self.go_home_cb) else None),
        ).pack(side="left", padx=5, pady=5)

        self.path_listado = None
        self.df_map = None
        self.df_preview = None     # DataFrame completo
        self.df_view = None        # DataFrame filtrado (None = sin filtro)
        self._df_preview_norm = {} # columnas normalizadas para filtro rápido

        self.enable_r2 = tk.BooleanVar(value=False)
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

        # Comenzamos directamente en el Paso 2 (pegar datos)
        self._show(self.stepB)

        # Carga diferida del listado (no bloquea la UI)
        if self.path_listado is not None:
            try:
                self._start_async_listado_load(self.path_listado)
            except Exception:
                pass

    def _build_stepA_select_listado(self):
        f = self.stepA = ttk.Frame(self, padding=16)
        ttk.Label(
            f,
            text="Paso 1: Listado de artículos ya cargado desde el menú principal",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            f,
            text="Se utilizará el LISTADO DE ARTÍCULOS que seleccionaste al inicio del programa.",
            foreground="#444",
        ).pack(anchor="w", pady=(4, 12))

        # Etiqueta informativa con el nombre del archivo detectado
        self.lbl_listado = ttk.Label(
            f,
            text="Listado aún no cargado",
            foreground="#666",
        )
        self.lbl_listado.pack(anchor="w", pady=(8, 12))

        # Botón para pasar al siguiente paso (pegar los datos)
        self.btn_to_paste = ttk.Button(
            f,
            text="Continuar →",
            state="disabled",
            command=lambda: self._show(self.stepB),
        )
        self.btn_to_paste.pack(anchor="e")

    def _start_async_listado_load(self, path: Path):
        """Carga el listado en un hilo para no congelar la apertura de la ventana."""
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
            try:
                result = self._parse_listado_for_map(path)
            except Exception as e:
                err = str(e)

            def apply():
                # detener progress
                try:
                    if hasattr(self, "_pb_listado"):
                        self._pb_listado.stop()
                except Exception:
                    pass

                if err:
                    try:
                        messagebox.showerror("Error", f"No se pudo cargar el listado.\n{err}")
                    except Exception:
                        pass
                    return

                try:
                    df_map, label_text = result
                    self.path_listado = Path(path)
                    self.df_map = df_map
                    self.lbl_listado.config(text=label_text)
                    self.btn_to_paste.config(state="normal")
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
        df_map = df_map.astype(str).apply(lambda s: s.str.strip())
        df_map = df_map.dropna(subset=["Identificador", "CodigoBarraInterno"])

        label_text = (
            f"OK: {path.name} | "
            f"Código='{ident_col}' | Barra='{barra_col}' | Nombre='{nombre_col}'"
        )
        return df_map, label_text

    def _build_stepB_paste(self):
        f = self.stepB = ttk.Frame(self, padding=16)
        ttk.Label(f, text="Paso 2: Pega 'Códigos de barra internos' y 'Precios' (uno por línea, mismo orden)",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w")

        cont = ttk.Frame(f); cont.pack(fill="both", expand=True, pady=12)
        left = ttk.Frame(cont); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = ttk.Frame(cont); right.pack(side="left", fill="both", expand=True, padx=(8,0))

        ttk.Label(left, text="Códigos de barra internos (uno por línea)").pack(anchor="w")
        self.txt_cod = tk.Text(left, height=20, wrap="none"); self.txt_cod.pack(fill="both", expand=True)

        ttk.Label(right, text="Precios (uno por línea)").pack(anchor="w")
        self.txt_prec = tk.Text(right, height=20, wrap="none"); self.txt_prec.pack(fill="both", expand=True)

        bar = ttk.Frame(f); bar.pack(fill="x")
        ttk.Button(bar, text="Limpiar", command=lambda:(self.txt_cod.delete("1.0","end"), self.txt_prec.delete("1.0","end"))).pack(side="left")
        ttk.Button(bar, text="← Volver", command=lambda:self._show(self.stepA)).pack(side="left", padx=8)
        ttk.Button(bar, text="Siguiente →", command=self._build_preview_from_paste).pack(side="right")

    def _read_pasted_lists(self):
        codes = [l.strip() for l in self.txt_cod.get("1.0","end").splitlines() if l.strip()]
        prices = [clean_price(l) for l in self.txt_prec.get("1.0","end").splitlines() if l.strip()]
        return codes, prices

    def _build_preview_from_paste(self):
        if self.df_map is None:
            messagebox.showwarning("Listado requerido", "Primero selecciona el Listado de artículos."); return
        codes, prices = self._read_pasted_lists()
        if not codes or not prices:
            messagebox.showwarning("Datos faltantes", "Pega al menos un código y un precio."); return
        if len(codes) != len(prices):
            messagebox.showwarning("Longitudes distintas", f"Hay {len(codes)} códigos y {len(prices)} precios. Deben tener la misma cantidad."); return

        df_in = pd.DataFrame({"CodigoBarraInterno": codes, "Precio1": prices})
        df = df_in.merge(self.df_map, on="CodigoBarraInterno", how="left")
        df["RangoInicial1"] = "1"; df["RangoFinal1"]  = "9999"
        df["Precio2"] = ""; df["RangoInicial2"] = ""; df["RangoFinal2"] = ""

        self.df_preview = df
        # Pre-computar columnas normalizadas para que _apply_filter sea O(1) por keystroke
        self._df_preview_norm = {
            "Identificador":     df["Identificador"].astype(str).map(_normalize_text) if "Identificador" in df.columns else pd.Series(dtype=str),
            "Nombre":            df["Nombre"].astype(str).map(_normalize_text)         if "Nombre"        in df.columns else pd.Series(dtype=str),
            "CodigoBarraInterno":df["CodigoBarraInterno"].astype(str).map(_normalize_text) if "CodigoBarraInterno" in df.columns else pd.Series(dtype=str),
        }
        self.df_view = None
        self._fill_preview_table()
        self._show(self.stepC)

    def _build_stepC_preview(self):
        f = self.stepC = ttk.Frame(self, padding=16)
        ttk.Label(f, text="Paso 3: Vista previa, asigna rangos y genera el archivo", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        # ---- Filtro rápido
        filter_bar = ttk.Frame(f); filter_bar.pack(fill="x", pady=(4,6))
        ttk.Label(filter_bar, text="Filtro rápido:").pack(side="left")
        self.var_filter = tk.StringVar(value="")
        self.ent_filter = ttk.Entry(filter_bar, width=40, textvariable=self.var_filter)
        self.ent_filter.pack(side="left", padx=6)
        ttk.Button(filter_bar, text="Aplicar filtro", command=self._apply_filter).pack(side="left", padx=(0,6))
        ttk.Button(filter_bar, text="Limpiar filtro", command=self._clear_filter).pack(side="left")
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
                "Precio2","RangoInicial2","RangoFinal2")
        self.columns = cols
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=22, selectmode="extended")
        widths = (140, 360, 170, 120, 120, 120, 120, 120, 120)
        for c,w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="left", fill="y")

        self.tree.tag_configure("nofound", background="#ffecec")
        self.tree.tag_configure("stripe0", background="")
        self.tree.tag_configure("stripe1", background=STRIPE_COLOR)

        side = ttk.Frame(body, padding=(12,0,0,0)); side.pack(side="left", fill="y")

        sw = ttk.Checkbutton(side, text="Habilitar Rango 2 (opcional)", variable=self.enable_r2, command=self._toggle_r2)
        sw.pack(anchor="w", pady=(0,6))

        ttk.Label(side, text="Rango 1 por defecto / masivo").pack(anchor="w", pady=(0,6))
        self.var_def_ri1 = tk.StringVar(value="1")
        self.var_def_rf1 = tk.StringVar(value="9999")
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
        ttk.Label(side, text="- Precio x kilo: usar 0,001 a 9999", foreground="#555").pack(anchor="w")
        ttk.Checkbutton(side, text="Exportar solo válidas (encontradas)", variable=self.export_only_valid).pack(anchor="w", pady=(10,0))

        self._setup_cell_editing()

        bottom = ttk.Frame(f); bottom.pack(fill="x", pady=(8,0))
        self.lbl_info = ttk.Label(bottom, text="", foreground="#555"); self.lbl_info.pack(side="left")
        ttk.Button(bottom, text="← Volver a pegar", command=lambda:self._show(self.stepB)).pack(side="right", padx=8)
        ttk.Button(bottom, text="Generar archivo...", command=self._export).pack(side="right")

        self._toggle_r2(initial=True)

    def _refocus_filter(self):
        try:
            self.ent_filter.focus_set()
        except Exception:
            pass

    def _toggle_r2(self, initial=False):
        if not self.enable_r2.get():
            for col in ("Precio2","RangoInicial2","RangoFinal2"):
                self.tree.column(col, width=2, stretch=False, anchor="w")
                self.tree.heading(col, text=col)
        else:
            self.tree.column("Precio2", width=120, stretch=True, anchor="w")
            self.tree.column("RangoInicial2", width=120, stretch=True, anchor="w")
            self.tree.column("RangoFinal2", width=120, stretch=True, anchor="w")
        if not initial: self.update_idletasks()

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
        rf1s  = _col("RangoFinal1", "9999")
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
            ins("", "end", values=(ident, nom, cbi, p1, ri1, rf1, p2, ri2, rf2), tags=(tag,))

        total = len(df)
        self.lbl_info.config(text=f"Filas visibles: {total} | No encontradas visibles: {no_count}")
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
            col_idx = int(col.replace("#","")) - 1
            editable = {3,4,5}
            if self.enable_r2.get(): editable.update({6,7,8})
            if col_idx not in editable: return
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

        out = ok[output_cols]
        path = filedialog.asksaveasfilename(title="Guardar archivo para importar", defaultextension=".xlsx",
                                            filetypes=[("Excel","*.xlsx")])
        if not path: return
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as wr:
                out.to_excel(wr, index=False, sheet_name="Precios")
        except Exception as e:
            messagebox.showerror("Error al guardar", f"No se pudo escribir el Excel.\n{e}"); return

        messagebox.showinfo("Listo", f"Archivo generado con rangos:\n{path}")

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
        self.master.title("Tivendo - Ingreso Masivo de Artículos (v91)")
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

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="⟵ Volver al inicio", command=self._back_home).pack(side="left", padx=5, pady=5)

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

    def _crear_paso1(self):
        lbl_titulo = ttk.Label(
            self.frame_paso1,
            text="PASO 1: Configura el código inicial y el proveedor.",
            font=("", 11, "bold"),
            wraplength=1150,
            justify="left",
        )
        lbl_titulo.pack(fill="x", padx=10, pady=(10, 5))

        frame_conf = ttk.LabelFrame(self.frame_paso1, text="Configuración general")
        frame_conf.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_conf, text="Código identificador inicial:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        self.entry_codigo_inicial = ttk.Entry(
            frame_conf, textvariable=self.var_codigo_actual, width=15
        )
        self.entry_codigo_inicial.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_conf, text="Proveedor (Id Categoría):").grid(
            row=0, column=2, padx=5, pady=5, sticky="e"
        )
        nombres_empresas = sorted(self.empresas_name_to_id.keys())
        # Guardamos la lista completa para poder filtrarla con el mini buscador
        self.empresas_choices_p1 = nombres_empresas

        self.combo_empresa = ttk.Combobox(
            frame_conf,
            textvariable=self.var_empresa_nombre,
            values=nombres_empresas,
            state="readonly",
            width=35,
        )
        self.combo_empresa.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        if nombres_empresas:
            self.combo_empresa.current(0)

        # Mini buscador de proveedor en vivo (para no recorrer toda la lista)
        self.var_empresa_search_p1 = tk.StringVar()
        entry_buscar = ttk.Entry(frame_conf, textvariable=self.var_empresa_search_p1, width=20)
        # Lo ubicamos a la derecha del combobox de proveedor
        entry_buscar.grid(row=0, column=4, padx=5, pady=5, sticky="w")
        entry_buscar.bind("<KeyRelease>", self._on_empresa_search_p1)

        btn_instrucciones = ttk.Button(
            frame_conf, text="Ver instrucciones", command=self._abrir_instrucciones
        )
        btn_instrucciones.grid(row=0, column=5, padx=10, pady=5, sticky="w")

        # Información sobre el catálogo utilizado para validar códigos
        frame_cat = ttk.LabelFrame(
            self.frame_paso1,
            text="Listado de artículos para validar códigos",
        )
        frame_cat.pack(fill="x", padx=10, pady=5)

        ttk.Label(
            frame_cat,
            text=(
                "Se está utilizando el LISTADO DE ARTÍCULOS cargado desde el menú principal "
                "para validar códigos ya existentes.\n"
                "Si necesitas cambiar ese archivo, vuelve al menú principal y selecciona otro listado."
            ),
            wraplength=1150,
            justify="left",
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")

        frame_nav = ttk.Frame(self.frame_paso1)
        frame_nav.pack(fill="x", padx=10, pady=10)

        btn_anterior_p1 = ttk.Button(frame_nav, text="← Anterior", state="disabled")
        btn_anterior_p1.pack(side="left")

        btn_siguiente = ttk.Button(frame_nav, text="Siguiente →", command=self._ir_a_paso2)
        btn_siguiente.pack(side="right")

    def _on_empresa_search_p1(self, event=None):
        """Filtra en vivo la lista de proveedores del PASO 1 según el mini buscador."""
        _filter_combobox_choices(
            self.var_empresa_search_p1.get().strip().lower(),
            self.empresas_choices_p1,
            self.combo_empresa,
            self.var_empresa_nombre,
        )

    def _crear_paso2(self):
        lbl_titulo = ttk.Label(
            self.frame_paso2,
            text=(
                "PASO 2: Ingreso masivo de artículos pegando columnas.\n"
                "Pega los datos directamente en los recuadros: Nombre, Precio, Código barra interno y externo."
            ),
            font=("", 11, "bold"),
            wraplength=1150,
            justify="left"
        )
        lbl_titulo.pack(fill="x", padx=10, pady=(10, 5))

        frame_cols = ttk.LabelFrame(self.frame_paso2, text="Ingreso masivo (uno por línea en cada columna)")
        frame_cols.pack(fill="both", expand=True, padx=10, pady=5)

        frame_cols.rowconfigure(0, weight=1)

        col1 = ttk.Frame(frame_cols)
        col1.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        frame_cols.columnconfigure(0, weight=3)

        ttk.Label(col1, text="Nombre (uno por línea)").pack(anchor="w")
        self.text_nombre = tk.Text(col1, wrap="none", height=20, width=40)
        self.text_nombre.pack(fill="both", expand=True, pady=2)
        scroll_y_nombre = ttk.Scrollbar(col1, orient="vertical", command=self.text_nombre.yview)
        scroll_y_nombre.pack(side="right", fill="y")
        scroll_x_nombre = ttk.Scrollbar(col1, orient="horizontal", command=self.text_nombre.xview)
        scroll_x_nombre.pack(side="bottom", fill="x")
        self.text_nombre.configure(yscrollcommand=scroll_y_nombre.set, xscrollcommand=scroll_x_nombre.set)

        col2 = ttk.Frame(frame_cols)
        col2.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        frame_cols.columnconfigure(1, weight=1)

        ttk.Label(col2, text="Precio (uno por línea)").pack(anchor="w")
        self.text_precio = tk.Text(col2, wrap="none", height=20, width=14)
        self.text_precio.pack(fill="both", expand=True, pady=2)
        scroll_y_precio = ttk.Scrollbar(col2, orient="vertical", command=self.text_precio.yview)
        scroll_y_precio.pack(side="right", fill="y")
        scroll_x_precio = ttk.Scrollbar(col2, orient="horizontal", command=self.text_precio.xview)
        scroll_x_precio.pack(side="bottom", fill="x")
        self.text_precio.configure(yscrollcommand=scroll_y_precio.set, xscrollcommand=scroll_x_precio.set)

        col3 = ttk.Frame(frame_cols)
        col3.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        frame_cols.columnconfigure(2, weight=1)

        ttk.Label(col3, text="Código barra interno (uno por línea)").pack(anchor="w")
        self.text_codint = tk.Text(col3, wrap="none", height=20, width=18)
        self.text_codint.pack(fill="both", expand=True, pady=2)
        scroll_y_codint = ttk.Scrollbar(col3, orient="vertical", command=self.text_codint.yview)
        scroll_y_codint.pack(side="right", fill="y")
        scroll_x_codint = ttk.Scrollbar(col3, orient="horizontal", command=self.text_codint.xview)
        scroll_x_codint.pack(side="bottom", fill="x")
        self.text_codint.configure(yscrollcommand=scroll_y_codint.set, xscrollcommand=scroll_x_codint.set)

        col4 = ttk.Frame(frame_cols)
        col4.grid(row=0, column=3, sticky="nsew", padx=5, pady=5)
        frame_cols.columnconfigure(3, weight=1)

        ttk.Label(col4, text="Código barra externo (uno por línea, opcional)").pack(anchor="w")
        self.text_codext = tk.Text(col4, wrap="none", height=20, width=18)
        self.text_codext.pack(fill="both", expand=True, pady=2)
        scroll_y_codext = ttk.Scrollbar(col4, orient="vertical", command=self.text_codext.yview)
        scroll_y_codext.pack(side="right", fill="y")
        scroll_x_codext = ttk.Scrollbar(col4, orient="horizontal", command=self.text_codext.xview)
        scroll_x_codext.pack(side="bottom", fill="x")
        self.text_codext.configure(yscrollcommand=scroll_y_codext.set, xscrollcommand=scroll_x_codext.set)

        frame_btns = ttk.Frame(self.frame_paso2)
        frame_btns.pack(fill="x", padx=10, pady=5)

        btn_limpiar = ttk.Button(frame_btns, text="Limpiar todo", command=self.limpiar_textos_paso2)
        btn_limpiar.pack(side="right", padx=5)

        frame_nav = ttk.Frame(self.frame_paso2)
        frame_nav.pack(fill="x", padx=10, pady=10)

        btn_anterior = ttk.Button(frame_nav, text="← Anterior", command=lambda: self._mostrar_paso(1))
        btn_anterior.pack(side="left")

        btn_siguiente = ttk.Button(frame_nav, text="Siguiente →", command=self._procesar_y_ir_a_paso3)
        btn_siguiente.pack(side="right")

    def _crear_paso3(self):
        lbl_titulo = ttk.Label(
            self.frame_paso3,
            text="PASO 3: Revisa la vista previa y genera el archivo de ingreso masivo.",
            font=("", 11, "bold"),
            wraplength=1150,
            justify="left"
        )
        lbl_titulo.pack(fill="x", padx=10, pady=(10, 5))

        frame_archivo = ttk.LabelFrame(self.frame_paso3, text="Configuración del archivo de salida")
        frame_archivo.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_archivo, text="Nombre archivo salida:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        ttk.Entry(frame_archivo, textvariable=self.var_nombre_archivo_salida, width=40).grid(
            row=0, column=1, padx=5, pady=5, sticky="w"
        )

        btn_generar = ttk.Button(
            frame_archivo,
            text="Generar Excel de ingreso masivo",
            command=self.generar_excel
        )
        btn_generar.grid(row=0, column=2, padx=10, pady=5, sticky="w")

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
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="w", stretch=False, width=120)

        # Colores alternados tipo Excel
        self.tree.tag_configure("fila_par", background="#F2F2F2")
        self.tree.tag_configure("fila_impar", background="#FFFFFF")

        # Doble click para editar celdas (menos la columna Código)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        self._refrescar_tabla()

        frame_nav = ttk.Frame(self.frame_paso3)
        frame_nav.pack(fill="x", padx=10, pady=10)

        btn_anterior = ttk.Button(frame_nav, text="← Anterior", command=self._ir_a_paso2)
        btn_anterior.pack(side="left")

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
        for col, max_len in max_lens.items():
            width = max(80, min(400, max_len * 7))
            self.tree.column(col, width=width, stretch=False, anchor="w")

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

        col_name = columnas[col_index]

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
            nuevo_valor = editor.get()
            # Actualizar Treeview
            valores_fila = list(self.tree.item(item_id, "values"))
            valores_fila[col_index] = nuevo_valor
            self.tree.item(item_id, values=valores_fila)
            # Actualizar DataFrame
            self.df_import.at[row_index, col_name] = nuevo_valor
            editor.destroy()
            self._tree_editor = None

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
        if not self.validar_codigo_inicial():
            return
        self._mostrar_paso(2)

    def _procesar_y_ir_a_paso3(self):
        exito = self.procesar_lista_paso2()
        if exito:
            self._ir_a_paso3()

    def _ir_a_paso3(self):
        self._refrescar_tabla()
        self._mostrar_paso(3)

    def _abrir_instrucciones(self):
        top = tk.Toplevel(self)
        top.title("Instrucciones - Flujo recomendado")
        top.geometry("750x450")

        texto = (
            "Flujo recomendado para el Ingreso Masivo de Artículos:\n\n"
            "1) PASO 1:\n"
            "   - Ingresa el CÓDIGO IDENTIFICADOR INICIAL (por ejemplo A020267).\n"
            "   - Selecciona el PROVEEDOR (Id Categoría).\n"
            "   - (Opcional) Carga un listado de artículos exportado desde Tivendo para validar si el código ya existe.\n"
            "   - Si el código ya existe, aparecerán 3 opciones: Cancelar, Reemplazar datos, o Continuar con el siguiente código disponible.\n\n"
            "2) PASO 2:\n"
            "   - Pega las columnas de NOMBRE, PRECIO, CÓDIGO BARRA INTERNO y, si quieres, CÓDIGO BARRA EXTERNO.\n"
            "   - Cada recuadro es una columna; cada línea es un artículo.\n"
            "   - Presiona 'Siguiente' para procesar la lista. Si hay algún error, se mostrará el detalle y NO avanzarás al Paso 3.\n\n"
            "3) PASO 3:\n"
            "   - Revisa la VISTA PREVIA.\n"
            "   - Define el nombre de archivo.\n"
            "   - Haz clic en 'Generar Excel de ingreso masivo'.\n"
            "   - Recuerda: Tivendo exige mínimo 2 artículos con código para aceptar el archivo.\n"
        )

        lbl = ttk.Label(top, text=texto, justify="left", wraplength=730)
        lbl.pack(fill="both", expand=True, padx=10, pady=10)

        btn_cerrar = ttk.Button(top, text="Cerrar", command=top.destroy)
        btn_cerrar.pack(pady=5)

    def generar_excel(self):
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
                    "Actualmente solo tienes 1 artículo en la lista."
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

            messagebox.showinfo("Éxito", f"Archivo de ingreso masivo generado:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el archivo.\n\nDetalle: {e}")

    def _refrescar_tabla(self):
        if not self.tree:
            return
        self.tree.delete(*self.tree.get_children())
        ins = self.tree.insert
        for idx, row_vals in enumerate(self.df_import.itertuples(index=False, name=None)):
            tag = "fila_par" if idx % 2 == 0 else "fila_impar"
            ins("", "end", values=row_vals, tags=(tag,))
        self._ajustar_anchos_columnas()

    def _start_async_catalogo_load(self, ruta):
        """Carga el catálogo en un hilo para no congelar la apertura."""
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
                try:
                    self.master.config(cursor="")
                except Exception:
                    pass

                if err:
                    # Si falla, no cerramos: solo dejamos que el usuario cargue manualmente
                    return

                try:
                    df_catalogo, set_cod, set_norm = result
                    self.df_catalogo = df_catalogo
                    self.codigos_catalogo_set = set_cod
                    self.codigos_catalogo_norm_set = set_norm
                except Exception:
                    pass

            try:
                self.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _parse_catalogo_for_sets(self, ruta):
        """Lee el catálogo y devuelve (df_catalogo, codigos_set, codigos_norm_set). No toca la UI."""
        ext = Path(ruta).suffix.lower()  # acepta str o Path
        if ext in [".xlsx", ".xls"]:
            df_raw = pd.read_excel(ruta, header=None)
        elif ext == ".csv":
            try:
                df_raw = pd.read_csv(ruta, header=None)
            except UnicodeDecodeError:
                df_raw = pd.read_csv(ruta, header=None, encoding="latin-1", sep=";")
        else:
            raise ValueError("Formato de archivo no soportado.")

        if df_raw.shape[0] < 6:
            raise ValueError("El archivo no tiene al menos 6 filas para usar como catálogo.")
        if df_raw.shape[1] < 4:
            raise ValueError(
                f"El archivo tiene solo {df_raw.shape[1]} columna(s); "
                "se necesitan al menos 4 (Código, Nombre, ?, Precio)."
            )

        df = df_raw.iloc[5:, [0, 1, 3]].copy()
        df.columns = ["codigo", "nombre", "precio"]
        df = df.dropna(subset=["codigo"])
        df = df.astype(str).apply(lambda s: s.str.strip())
        df_catalogo = df.reset_index(drop=True)

        cod_series = df_catalogo["codigo"].astype(str).str.strip()
        codigos_set = set(cod_series)
        codigos_norm_set = set(cod_series.map(normalizar_codigo_catalogo))
        return df_catalogo, codigos_set, codigos_norm_set

    def agregar_articulo(self):
        codigo = self.var_codigo_actual.get().strip()
        nombre = self.var_nombre.get().strip().upper()
        precio = self.var_precio.get().strip()
        cod_int = self.var_cod_barra_int.get().strip()
        cod_ext = self.var_cod_barra_ext.get().strip()
        empresa_nombre = self.var_empresa_nombre.get()

        if not codigo:
            messagebox.showwarning("Atención", "Debes ingresar el código identificador inicial (Paso 1).")
            return
        if not empresa_nombre:
            messagebox.showwarning("Atención", "Debes seleccionar un Proveedor (Id Categoría) en el Paso 1.")
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
        self._refrescar_tabla()

        nuevo_codigo = incrementar_codigo_identificador(codigo)
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
        codigo_inicial = self.var_codigo_actual.get().strip()
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
            self.agregar_articulo()
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

        messagebox.showinfo(
            "Importación masiva finalizada",
            f"Filas procesadas: {total_filas}\n"
            f"Artículos agregados correctamente: {agregados_ok}"
        )
        return True

    def limpiar_textos_paso2(self):
        self.text_nombre.delete("1.0", "end")
        self.text_precio.delete("1.0", "end")
        self.text_codint.delete("1.0", "end")
        self.text_codext.delete("1.0", "end")

def main():
    app = RootApp()
    app.mainloop()

if __name__ == "__main__":
    main()
