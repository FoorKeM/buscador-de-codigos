# Buscador de Códigos — AGENTS.md

## What this project is

A single-file Python 3 desktop app (`buscador_codigos.py`) for a Chilean retail/wholesale business. It helps staff search product codes, manage suppliers, and do mass price changes or mass article ingestion for the **Tivendo** POS system. UI is built with `tkinter`/`ttk`. Data manipulation uses `pandas` + `openpyxl`.

**Active file:** `buscador_codigos.py` (~3400 lines). Historical versions are kept as GitHub tags/releases (`v90`, `v91`, etc.), not as active working files.

---

## High-level architecture

```
RootApp (Tk root window)
├── StartView          — three tools and four data sources with individual/batch updates
├── SearchView         — product code search
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
Main menu with search and both bulk tools. «Datos cargados» lists articles, packs, prices/ranges and suppliers, with their own update date, file picker and download. The batch button uses one session and applies successful sources independently. Search requires a loaded article list.

The supplier row downloads the Categorías workbook from ERP Digital or imports the same workbook manually. Both validate the workbook and replace the supplier list in `empresas.json` by ID without merging the seed. Automatic downloads are temporary.

Automatic-download navigation must reuse an already-open page from the same
session once its expected host and visible work menu are ready, including pages
opened during a previous attempt. While that module loads, avoid reopening its
portal card. A login page is not a ready module and must not block reopening it.
POS export progress names the current step, and failed-source details remain
visible while other sources continue. Diagnostic log lines include timestamp,
app version and process ID. Log locations omit queries and OAuth fragments, and
diagnostics read control labels rather than credential fields.

The user confirmed the local v173 article fix worked on the first attempt.
Local v174 applies phase diagnostics and incomplete-screen recovery to prices
and suppliers as well. Packs shares the article helper; test both sections.
Prices reuse an open report, reload an incomplete form once, and wait for its
configured list options. Keep listening for downloads on the original page
while handling an export popup: confirmation may download on either page.
Register listeners before clicking Exportar, wait for the download to finish
before closing export popups, and remove listeners/cancel confirmation tasks
on success, error and cancellation.
Supplier recovery also reloads when the master is open but Categorías is
missing; do not reload after cancellation or replace data with an invalid Excel.
`tools.test_source_navigation` covers these cases without UI. The optional
`python -m tools.test_auto_source_browser` uses an isolated headless Edge and
intercepts all requests with synthetic pages/workbooks; it never signs in.
Local v174 validation: 107 headless unit tests passed, plus four synthetic price
export flows and the supplier iframe/Excel flow in headless Edge. The packaged
code matched the final source. A Defender custom scan recorded zero detections
for that distribution. The user subsequently confirmed all four real-account
updates worked correctly and authorized publishing v174. A custom scan alone
does not establish runtime Defender behavior. Executable SHA-256:
`7c897e43ddddde7331fb25443cf1f84cff6eb0250ff5e27362b6e16d7249ee0d`.

### SearchView
- Multi-code text input (one per line or comma-separated)
- Checkboxes: exact match, by barcode
- Empresa combobox with live search
- Results in `ttk.Treeview`
- Copy operations: barcodes, names, not-found codes
- CSV export
- Right-click context menu on rows

### AutoBuildDBWindow (Toplevel)
Progress dialog. Runs `transform_export(path, progress_cb)` in a background thread. Saves result to `TMP_DIR/MH_TMP_BASE_<stem>.xlsx`.

### TivendoWindow (Toplevel) — 3-step wizard
- **Step A**: select listado, loads async in thread
- **Step B**: independent multiline paste columns, with range 1 always visible/required. The block is horizontally centered, with moderate fixed barcode/price/quantity widths (24/14/8 characters). Columns use the available height and share one vertical scrollbar; no horizontal scrollbars. Only range 2 and price 2 are optional. Quantities max 1000. Enter moves to the next row and Ctrl+V pastes from the current row without shifting other rows or columns. Ctrl+A selects the whole column for replacement. Empty clipboard rows inside a block are preserved. There is no whole-table paste button/parser/fallback; multi-column clipboard content is rejected without changing existing data.
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
| `empresas.json` | app data directory (legacy app directory as fallback) | Supplier dict `{"1": "Name", ...}` |
| `buscador_prefs.json` | app directory | `last_dir`, `geometry`, `exact`, `by_barras`, `empresa_display` |
| `base_codigos_cache.pkl` | `CACHE_DIR` | Pickled DataFrame cache |
| `base_codigos_cache_meta.json` | `CACHE_DIR` | Cache metadata (src_key, mtime) |

---

## Launcher recovery and release checks

The launcher is a separate executable built from `launcher.py`. Its
`launcher_state.json` records a version tag. A saved tag does not prove that the
application executable still exists.

The 2026-11-11 incident exposed a launcher 1.0 defect. When the saved tag matched
the latest release but the local executable was absent, it skipped downloading
and showed «Sin versión disponible». This behavior was reproduced. The initial
cause of the affected users' missing files was not established.

- Launcher 1.1 downloads when the release tag changes **or** the local executable
  is missing. Preserve both conditions.
- Release v167 recovered existing launcher 1.0 installations by presenting a new
  release tag. This was tested with the original launcher from commit
  `d4e0a62`, including an absent installation and a directory containing only
  `_internal`.
- An application ZIP does not replace the user's launcher executable. Distinguish
  recovery through a newer release from upgrading the launcher itself.
- Before a launcher change, run `python -m unittest tools.test_launcher`. It
  covers first launch, missing or incomplete local installations, recovery through
  a newer release, normal updates, reuse of an installed version, and offline use.
  Use temporary directories and mocked UI so staff can keep working.
- Before publication, test the actual ZIP with the distributed launcher's
  installation function in a temporary directory. Check that the packaged code
  matches the release source and that the existing launcher detects the release.
- Upload and verify the complete application ZIP in a draft release before
  making it the latest public release. Prefer recovery through the usual access
  point over asking staff to delete configuration files.
- On 2026-11-12 Defender quarantined the local v170 executable as
  `Trojan:Win32/Bearfoos.A!ml`. This has not been confirmed as a false positive.
  The 566 PyInstaller package files matched the official 6.22.3 Windows wheel,
  and a Defender scan of v170's `_internal` directory reported no additional
  detections. Keep this distinct from an approval of the blocked executable.
  At the user's explicit request, local v171 was built with the UI changes.
  Its source matched the packaged code, all 96 automated tests passed, and a
  complete Defender custom scan reported zero detections for its distribution
  directory. The v171 executable's SHA-256 is
  `57c5b75f1c486be5fe4a5c2f4f016ad5e907e6fa89d7408b2c0152b6b42a4c91`.
  These results apply to that build and do not reclassify the v170 detection.
  The user subsequently reported Defender blocking v171 as well. Defender
  records include its executable and a process. The clean custom scan did not
  predict that later detection.
  Local v172 removes the separate credential-checking browser sessions, the
  Mercado House account setup, and automatic startup prompts. Its settings
  button edits the existing Tivendo access, which is used during data updates.
  It retains the article-navigation repair and retry/cancel controls.
  All 88 tests passed and a custom scan reported zero v172 detections. Its
  executable SHA-256 is
  `95d5ae2935169db06b5fb15486abea33196954221f2da45deba2ec513cf8f00a`.
  Runtime behavior with Defender remains to be confirmed by the user. Do not
  declare this incident resolved solely from another clean custom scan.
  Record the security review and scan results before declaring a replacement safe.

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
- The unused legacy `ConvertView` was removed in v145. Active conversion remains in `AutoBuildDBWindow` and `transform_export`.
