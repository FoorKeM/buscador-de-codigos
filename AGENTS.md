# Buscador de Códigos — AGENTS.md

## What this project is

A single-file Python 3 desktop app (`buscador_codigos.py`) for a Chilean retail/wholesale business. It helps staff search product codes, manage suppliers, and do mass price changes or mass article ingestion for the **Tivendo** POS system. UI is built with `tkinter`/`ttk`. Data manipulation uses `pandas` + `openpyxl`.

**Active file:** `buscador_codigos.py` (~3400 lines). Historical versions are kept as GitHub tags/releases (`v90`, `v91`, etc.), not as active working files.

---

## High-level architecture

```
RootApp (Tk root window)
├── StartView          — main menu, four action buttons
├── SearchView         — product code search
├── ProvidersView      — CRUD for supplier list
├── TivendoWindow      — (Toplevel) 3-step mass price change wizard
├── TivendoIngresoMasivoArticulosWindow — (Toplevel) 3-step mass article ingestion wizard
└── AutoBuildDBWindow  — (Toplevel) progress dialog for Excel→DB transform
```

Views are swapped by destroying the current frame and creating the next one in the same root window. `RootApp` holds shared state (`listado_path`, last loaded df, window geometry).

---

## Key global constants & config

| Symbol | Value / Purpose |
|--------|----------------|
| `STRIPE_COLOR` | `"#f5f5f5"` — alternating row tint |
| `MAX_RESULTS` | `500` — search result cap |
| `TMP_DIR` | `LOCALAPPDATA/BuscadorCodigos/tmp/` |
| `CACHE_DIR` | `LOCALAPPDATA/BuscadorCodigos/.cache/` |
| `SEED_EMPRESAS` | Dict of 181 suppliers `{int_id: name}` used to seed `empresas.json` |
| `_RE_WS`, `_RE_NORM`, `_RE_NO_DIGITS` | Pre-compiled regexes for whitespace strip, unicode normalization, digit extraction |

---

## Data loading & cache

```
load_data(selected_path)
  1. Compute src_key = path + mtime
  2. Check in-memory dict _LOAD_DATA_CACHE[src_key]
  3. Check disk: CACHE_DIR/base_codigos_cache.pkl + _meta.json
  4. Otherwise: read Excel/CSV with pandas, normalize columns, save to disk
```

Normalized columns added to every DataFrame:
- `_codigo_lc` — lowercase code
- `_codigo_ws` — whitespace-stripped code
- `_nombre_lc` — lowercase name
- `_codigo_tokens` — tokenized code list
- `_codigo_tokens_norm` — unicode-normalized tokens

---

## Search logic

`_build_search_mask(df, q_raw, q_ws, q_norm, exact, by_barras) → bool Series`

- **exact=True**: matches full code equality
- **exact=False**: substring match across code, tokens, name; optional barcode columns
- Returns boolean mask applied to df to get result rows

---

## Shared helper

`_filter_combobox_choices(term, choices, combo, result_var)` — live-filters a `ttk.Combobox` as user types. Used in SearchView (empresa filter) and TivendoIngresoMasivoArticulosWindow (empresa selector).

---

## Views in detail

### StartView
Main menu. Four buttons: Buscar Código, Administrar proveedores, CAMBIOS MASIVOS TIVENDO, INGRESO MASIVO TIVENDO. All buttons except "cargar listado" are disabled until a listado is loaded.

### SearchView
- Multi-code text input (one per line or comma-separated)
- Checkboxes: exact match, by barcode
- Empresa combobox with live search
- Results in `ttk.Treeview`
- Copy operations: barcodes, names, not-found codes
- CSV export
- Right-click context menu on rows

### ProvidersView
CRUD treeview backed by `empresas.json`. Reads/writes the file on every change.

### AutoBuildDBWindow (Toplevel)
Progress dialog. Runs `transform_export(path, progress_cb)` in a background thread. Saves result to `TMP_DIR/MH_TMP_BASE_<stem>.xlsx`.

### TivendoWindow (Toplevel) — 3-step wizard
- **Step A**: select listado, loads async in thread
- **Step B**: paste barcodes + new prices (two text areas)
- **Step C**: preview treeview with editable Precio column, range assignment, Excel export for Tivendo import
- Uses pre-computed `_df_preview_norm` dict for O(1) row filtering

### TivendoIngresoMasivoArticulosWindow (Toplevel) — 3-step wizard
- **Step 1**: set initial identifier code (e.g. `A020267`) + supplier selection
- **Step 2**: paste 4 columns: Nombre, Precio, CodBarraInt, CodBarraExt
- **Step 3**: preview treeview + generate Excel
- Validates codes against loaded catalog; if code exists shows replace/skip dialog
- Auto-increments identifier codes: `A020267 → A020268`

Key helpers for this window:
- `incrementar_codigo_identificador(codigo)` — bumps trailing digits preserving prefix
- `normalizar_codigo_catalogo(df)` — strips/lowercases catalog codes for lookup
- `buscar_siguiente_codigo_disponible(base, df_catalog)` — finds first unused increment
- `procesar_lista_paso2()` — iterates pasted rows, validates each, calls `agregar_articulo()`, shows error on first failure
- `limpiar_textos_paso2()` — clears all four text areas

---

## Persistence files

| File | Location | Purpose |
|------|----------|---------|
| `empresas.json` | app directory | Supplier dict `{"1": "Name", ...}` |
| `buscador_prefs.json` | app directory | `last_dir`, `geometry`, `exact`, `by_barras`, `empresa_display` |
| `base_codigos_cache.pkl` | `CACHE_DIR` | Pickled DataFrame cache |
| `base_codigos_cache_meta.json` | `CACHE_DIR` | Cache metadata (src_key, mtime) |

---

## Threading pattern

Heavy I/O (Excel load, DB build) runs in `threading.Thread(daemon=True)`. Progress or completion is communicated back to the UI via `root.after(0, callback)` — never touch tkinter widgets from the worker thread directly.

---

## Entry point

```python
def main():
    app = RootApp()
    app.mainloop()

if __name__ == "__main__":
    main()
```

---

## What NOT to do

- Do not read the entire source file on every session — this AGENTS.md is the reference.
- Do not create a new `buscador_codigos_vNN.py` file for each change. Keep active development in `buscador_codigos.py`; publish stable snapshots through GitHub tags/releases.
- Do not flatten the cache structure; both `.pkl` and `_meta.json` must stay in sync.
- `ConvertView` is a legacy class still in the file but not wired to any menu button — ignore it unless specifically asked.
