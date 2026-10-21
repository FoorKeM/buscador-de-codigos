"""Pruebas sin ventanas, sin control de escritorio y sin conectarse a Tivendo."""
import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import buscador_codigos as app


REPORT = '''<table><tr><td>Código artículo</td><td>Rango 1</td><td>Precio Unitario 1</td><td>Rango 2</td><td>Precio Unitario 2</td></tr>
<tr><td>'A022766</td><td>(1 - 9,999)</td><td>1,290</td><td>(10 - 9,999)</td><td>990</td></tr>
<tr><td>'00123</td><td>(1 - 9,999)</td><td>0</td><td>(0)</td><td>0</td></tr></table>'''


class Widget:
    def __init__(self):
        self.options = {}
        self.visible = False
    def config(self, **kwargs):
        self.options.update(kwargs)
    configure = config
    def pack(self, **kwargs): self.visible = True
    def pack_forget(self): self.visible = False
    def grid(self, **kwargs): self.visible = True
    def grid_remove(self): self.visible = False
    def start(self, *args): pass
    def stop(self): pass


class Var:
    def __init__(self, value): self.value = value
    def get(self): return self.value


class Tree(Widget):
    def __init__(self):
        super().__init__()
        self.rows = {"1": {"Código": "A022766", "Nombre": "PALMERITAS", "CodigoBarraInterno": "00123",
            "Precio1": "1990", "RangoInicial1": "1", "RangoFinal1": "9999", "Precio2": "", "RangoInicial2": "",
            "RangoFinal2": "", "PrecioActual1": "1290", "PrecioActual2": "990"}}
        self.display = ("Código", "Nombre", "CodigoBarraInterno", "PrecioActual1", "Precio1")
        self.column = "#4"
    def get_children(self): return tuple(self.rows)
    def set(self, row, col, *value):
        if value: self.rows[row][col] = value[0]
        return self.rows[row][col]
    def __getitem__(self, key): return self.display
    def identify(self, *args): return "cell"
    def identify_column(self, *args): return self.column
    def identify_row(self, *args): return "1"
    def bbox(self, *args): return (0, 0, 100, 24)


def view_for_test(root):
    view = object.__new__(app.TivendoWindow)
    view.master = root
    view.winfo_exists = lambda: True
    view._precios_actualizando = False
    view._precios_confirmados = False
    view._modo_ejemplo_precios = False
    view.df_map = app.pd.DataFrame({"Identificador": ["A022766"]})
    view.tree = Tree()
    view.columns = ("Código", "Nombre", "CodigoBarraInterno", "Precio1", "RangoInicial1", "RangoFinal1",
                    "Precio2", "RangoInicial2", "RangoFinal2", "PrecioActual1", "PrecioActual2")
    view.enable_r2 = Var(False)
    view.export_only_valid = Var(True)
    view._edit_entry = None
    for name in ("lbl_estado_lista_precios", "lbl_archivo_lista_precios", "lbl_descarga_precios",
                 "btn_actualizar_precios", "btn_usar_guardados", "pb_precios", "btn_to_paste"):
        setattr(view, name, Widget())
    return view


class PriceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.old = self.directory / "anterior.xls"
        self.old.write_text(REPORT, encoding="utf-8")
        self.meta = mock.patch.object(app, "AUTO_LAST_LOAD_PATH", self.directory / "ultima.json")
        self.meta.start()
        app.save_auto_last_load(self.directory / "articulos.xlsx", self.directory / "packs.xlsx", self.old)

    def tearDown(self):
        self.meta.stop()
        self.tmp.cleanup()

    def root(self):
        return types.SimpleNamespace(ranges_path=self.old, ranges_df=None, ranges_index={}, start_view=None,
            _auto_load_busy=False, _ask_auto_credentials=mock.Mock(return_value=("prueba", "prueba")),
            after=lambda delay, callback: callback())

    def run_refresh(self, root, action, automatico=True, saved=None):
        success, error, progress = mock.Mock(), mock.Mock(), mock.Mock()
        saved = saved if saved is not None else {"usuario": "prueba", "password": "prueba"}
        with mock.patch.object(app.threading, "Thread", side_effect=lambda target, daemon: types.SimpleNamespace(start=target)), \
             mock.patch.object(app, "load_auto_credentials", return_value=saved), \
             mock.patch.object(app, "save_auto_credentials"), mock.patch.object(app, "_auto_log"), \
             mock.patch.object(app, "auto_download_solo_precios", action):
            app.RootApp._actualizar_solo_precios(root, success, error, progress, automatico=automatico)
        return success, error

    def test_informe_incluye_precios_unitarios_y_cero_real(self):
        _, index = app.load_price_ranges_data(self.old)
        self.assertEqual(app.precio_actual_catalogo("A022766", index), "1290")
        self.assertEqual(app.precio_actual_catalogo("A022766", index, rango=2), "990")
        self.assertEqual(app.precio_actual_catalogo("00123", index), "0")
        self.assertEqual(app.precio_actual_catalogo("A999999", index), "Sin dato")
        self.assertEqual(index["A022766"]["rango1"], "(1 - 9,999)")

    def test_cache_antigua_se_relee_para_incluir_precios(self):
        cache, metadata = self.directory / "cache.pkl", self.directory / "cache.json"
        app.pd.to_pickle((app.pd.DataFrame(), {"A022766": {"rango1": "anterior"}}), cache)
        metadata.write_text(json.dumps({"src_path": str(self.old), "src_mtime": self.old.stat().st_mtime}), encoding="utf-8")
        _, index = app._load_cached_side_data(self.old, cache, metadata, app.load_price_ranges_data)
        self.assertEqual(index["A022766"]["precio1"], "1290")
        self.assertEqual(json.loads(metadata.read_text())["schema_version"], 2)

    def test_actualiza_solo_precios_y_su_fecha(self):
        old_meta = app.load_auto_last_load()
        new = self.directory / "nueva.xls"
        new.write_text(REPORT.replace("1,290", "1,490"), encoding="utf-8")
        df, index = app.load_price_ranges_data(new)
        root = self.root()
        action = mock.AsyncMock(return_value=(new, df, index))
        success, error = self.run_refresh(root, action)
        success.assert_called_once_with(new, df, index)
        error.assert_not_called()
        self.assertEqual(root.ranges_path, new)
        self.assertEqual(root.ranges_index["A022766"]["precio1"], "1490")
        self.assertFalse(root._auto_load_busy)
        self.assertIsNone(root._price_refresh_subscribers)
        metadata = app.load_auto_last_load()
        for field in ("articulos", "packs", "articulos_downloaded_at", "downloaded_at"):
            self.assertEqual(metadata[field], old_meta[field])
        self.assertEqual(metadata["precios"], str(new))
        self.assertNotIn("sin fecha", app.price_download_label(new))
        self.assertIn("sin fecha", app.price_download_label(self.old))

    def test_fallo_conserva_ruta_fecha_y_precios_guardados(self):
        metadata = app.load_auto_last_load()
        root = self.root()
        success, error = self.run_refresh(root, mock.AsyncMock(side_effect=app.AutoDownloadError("Sin conexión\nCall log: detalle")))
        success.assert_not_called()
        self.assertEqual(error.call_args.args, ("Sin conexión",))
        self.assertEqual(root.ranges_path, self.old)
        self.assertEqual(root.ranges_index["A022766"]["precio1"], "1290")
        self.assertEqual(app.load_auto_last_load(), metadata)
        self.assertFalse(root._auto_load_busy)

    def test_automatico_sin_clave_no_abre_dialogo(self):
        root = self.root()
        download = mock.AsyncMock()
        _, error = self.run_refresh(root, download, saved={"usuario": "prueba", "password": ""})
        root._ask_auto_credentials.assert_not_called()
        download.assert_not_called()
        self.assertIn("Configura", error.call_args.args[0])
        self.assertEqual(root.ranges_index["A022766"]["precio1"], "1290")

    def test_boton_manual_utiliza_el_acceso_configurado(self):
        root = self.root()
        df, index = app.load_price_ranges_data(self.old)
        self.run_refresh(root, mock.AsyncMock(return_value=(self.old, df, index)), automatico=False)
        root._ask_auto_credentials.assert_called_once()

    def test_dos_entradas_comparten_descarga_en_curso(self):
        root = self.root()
        root._price_refresh_subscribers = []
        callbacks = mock.Mock(), mock.Mock(), mock.Mock()
        with mock.patch.object(app.threading, "Thread") as thread:
            app.RootApp._actualizar_solo_precios(root, *callbacks, automatico=True)
            thread.assert_not_called()
        self.assertEqual(root._price_refresh_subscribers, [callbacks])

    def test_entrada_dispara_actualizacion_automatica(self):
        view = view_for_test(self.root())
        view._actualizar_lista_precios = mock.Mock()
        view._actualizar_precios_al_entrar()
        view._actualizar_lista_precios.assert_called_once_with(automatico=True)

    def test_actualizacion_compara_sin_cambiar_el_precio_nuevo(self):
        root = self.root()
        df, root.ranges_index = app.load_price_ranges_data(self.old)
        view = view_for_test(root)
        view._lista_precios_actualizada(self.old, df, root.ranges_index)
        self.assertEqual(view.tree.set("1", "PrecioActual1"), "1290")
        self.assertEqual(view.tree.set("1", "Precio1"), "1990")
        self.assertTrue(view._precios_confirmados)
        self.assertEqual(view.btn_to_paste.options["state"], "normal")

    def test_fallo_requiere_elegir_usar_guardados(self):
        root = self.root()
        _, root.ranges_index = app.load_price_ranges_data(self.old)
        view = view_for_test(root)
        view._error_lista_precios("Tivendo no respondió")
        self.assertEqual(view.btn_to_paste.options["state"], "disabled")
        self.assertTrue(view.btn_usar_guardados.visible)
        view._usar_precios_guardados()
        self.assertEqual(view.btn_to_paste.options["state"], "normal")
        self.assertEqual(view.tree.set("1", "PrecioActual1"), "1290")

    def test_precio_anterior_es_solo_lectura_y_nuevo_se_puede_editar(self):
        view = view_for_test(self.root())
        with mock.patch.object(app.tk, "Entry") as entry:
            view._begin_edit_cell(types.SimpleNamespace(x=10, y=10))
            entry.assert_not_called()
            view.tree.column = "#5"
            view._begin_edit_cell(types.SimpleNamespace(x=10, y=10))
            entry.assert_called_once()
            self.assertEqual(view._edit_col, view.columns.index("Precio1"))

    def test_excel_solo_contiene_precios_nuevos_y_formato_original(self):
        view = view_for_test(self.root())
        target = self.directory / "salida.xlsx"
        with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(target)), \
             mock.patch.object(app.messagebox, "showinfo"):
            view._export()
        output = app.pd.read_excel(target, dtype=str).fillna("")
        self.assertEqual(output.columns.tolist(), ["Código", "RangoInicial1", "RangoFinal1", "Precio1", "RangoInicial2", "RangoFinal2", "Precio2"])
        self.assertEqual(output.iloc[0]["Precio1"], "1990")
        self.assertNotIn("PrecioActual1", output.columns)

    def test_callback_de_vista_cerrada_no_toca_widgets(self):
        view = view_for_test(self.root())
        view.winfo_exists = lambda: False
        view._terminar_actualizacion_precios = mock.Mock()
        view._lista_precios_actualizada(None, None, {})
        view._error_lista_precios("error")
        view._terminar_actualizacion_precios.assert_not_called()


class PriceDownloadTests(unittest.TestCase):
    def test_descarga_y_validacion_sin_alterar_otros_archivos(self):
        class Context:
            async def __aenter__(self): return object()
            async def __aexit__(self, *args): return False
        module = types.ModuleType("playwright.async_api")
        module.async_playwright = Context
        browser = types.SimpleNamespace(close=mock.AsyncMock())
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            articles = data / "articulos.xlsx"
            articles.write_bytes(b"articulos originales")
            old = data / "precios.xls"
            old.write_text(REPORT, encoding="utf-8")

            async def download(context, page, staging):
                source = staging / "lista.xls"
                source.write_text(REPORT, encoding="utf-8")
                return source

            with mock.patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.async_api": module}), \
                 mock.patch.object(app, "APP_DATA_DIR", data), mock.patch.object(app, "AUTO_DOWNLOAD_DIR", data), \
                 mock.patch.object(app, "_auto_log"), \
                 mock.patch.object(app, "_auto_new_page", mock.AsyncMock(return_value=(browser, object(), object()))), \
                 mock.patch.object(app, "_auto_login_tivendo", mock.AsyncMock()), \
                 mock.patch.object(app, "_auto_ensure_mercado_house", mock.AsyncMock()), \
                 mock.patch.object(app, "_auto_download_price_ranges", download), \
                 mock.patch.object(app, "_auto_download_from_pos", mock.AsyncMock()) as pos:
                path, _, index = asyncio.run(app.auto_download_solo_precios("prueba", "prueba"))
                self.assertEqual(index["A022766"]["precio1"], "1290")
                self.assertEqual(articles.read_bytes(), b"articulos originales")
                self.assertEqual(old.read_text(encoding="utf-8"), REPORT)
                pos.assert_not_called()
                previous = path.read_bytes()

                async def invalid(context, page, staging):
                    source = staging / "lista.xls"
                    source.write_text(REPORT.replace("Precio Unitario 1", "Otra columna"), encoding="utf-8")
                    return source
                with mock.patch.object(app, "_auto_download_price_ranges", invalid):
                    with self.assertRaises(app.AutoDownloadError):
                        asyncio.run(app.auto_download_solo_precios("prueba", "prueba"))
                self.assertEqual(path.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main(verbosity=2)
