"""Regresiones del ingreso masivo; usa datos temporales y no conecta a Tivendo."""

import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import buscador_codigos as app


def catalogo():
    return app.pd.DataFrame([
        ("A202822", "NO DISPONIBLE", "99999", "No"),
        ("A022764", "GALLETAS", "990", "Si"),
        ("A19119", "NO DISPONIBLE", "111", "No"),
        ("A022766", "PALMERITAS DULCEDIA 150gr", "1290", "Sí"),
        ("A099999", "NO DISPONIBLE.", "111", "Si"),
        ("A022765", "QUESO", "11160", "Si"),
        ("A999998", "OTRO INACTIVO", "111", "Inactivo"),
    ], columns=["codigo", "nombre", "precio", "activo"])


def exportar_catalogo(path):
    df = catalogo().rename(columns={"codigo": "Código", "nombre": "Nombre", "precio": "Precio", "activo": "Activo"})
    df["Código barra interno"] = [f"00{i}" for i in range(len(df))]
    # Encabezado en una fila distinta de la antigua posición fija.
    with app.pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, startrow=2, index=False)


class SecuenciaTests(unittest.TestCase):
    def test_continua_tras_maximo_valido_sin_rellenar_huecos(self):
        result = app.calcular_secuencia_articulos(catalogo())
        self.assertEqual(result["ultimo"], "A022766")
        self.assertEqual(result["siguiente"], "A022767")
        self.assertEqual(result["validos"], 3)

    def test_inactivos_excluidos_siguen_ocupando_codigos(self):
        df = app.pd.concat([catalogo(), app.pd.DataFrame([
            ("A022767", "NO DISPONIBLE", "0", "No")], columns=catalogo().columns)], ignore_index=True)
        self.assertEqual(app.calcular_secuencia_articulos(df)["siguiente"], "A022768")

    def test_sin_estado_o_sin_secuencia_no_inventa_codigo(self):
        self.assertEqual(app.calcular_secuencia_articulos(catalogo().drop(columns="activo"))["siguiente"], "")
        self.assertEqual(app.calcular_secuencia_articulos(catalogo().iloc[:1])["siguiente"], "")

    def test_catalogo_lee_encabezado_real_y_conserva_estado(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "listado.xlsx"
            exportar_catalogo(path)
            result = app.leer_catalogo_articulos(path)
            self.assertEqual(app.calcular_secuencia_articulos(result)["siguiente"], "A022767")
            self.assertEqual(result.loc[0, "activo"], "No")

    def test_tabla_excel_admite_encabezados_y_columna_opcional_vacia(self):
        rows = app.parsear_tabla_pegada("Nombre\tPrecio\tBarra\nGalletas\t1290\t00123", 4, {"nombre"})
        self.assertEqual(rows, [["Galletas", "1290", "00123", ""]])

    def test_fecha_solo_se_atribuye_al_archivo_correspondiente(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "ultima.json"
            articles = Path(directory) / "articulos.xlsx"
            with mock.patch.object(app, "AUTO_LAST_LOAD_PATH", metadata):
                app.save_auto_last_load(articles, Path(directory) / "packs.xlsx", Path(directory) / "precios.xlsx")
                old = app.load_auto_last_load()
                app.save_auto_articles_load(articles)
                new = app.load_auto_last_load()
                self.assertEqual(new["packs"], old["packs"])
                self.assertEqual(new["precios"], old["precios"])
                self.assertEqual(new["downloaded_at"], old["downloaded_at"])
                self.assertNotIn("sin fecha", app.article_download_label(articles))
                self.assertIn("sin fecha", app.article_download_label(Path(directory) / "otro.xlsx"))


class DescargaTests(unittest.TestCase):
    def test_descarga_solo_articulos_no_borra_packs_ni_precios(self):
        class Context:
            async def __aenter__(self):
                return object()
            async def __aexit__(self, *args):
                return False

        module = types.ModuleType("playwright.async_api")
        module.async_playwright = Context
        browser = types.SimpleNamespace(close=mock.AsyncMock())
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            downloads = data / "downloads"
            downloads.mkdir()
            packs = downloads / "packs.xlsx"
            prices = downloads / "precios.xlsx"
            packs.write_bytes(b"packs originales")
            prices.write_bytes(b"precios originales")

            async def download(page, name, fallback, staging):
                path = staging / "listado.xlsx"
                exportar_catalogo(path)
                return path

            with mock.patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.async_api": module}), \
                 mock.patch.object(app, "APP_DATA_DIR", data), \
                 mock.patch.object(app, "AUTO_DOWNLOAD_DIR", downloads), \
                 mock.patch.object(app, "_auto_log"), \
                 mock.patch.object(app, "_auto_new_page", mock.AsyncMock(return_value=(browser, object(), object()))), \
                 mock.patch.object(app, "_auto_login_tivendo", mock.AsyncMock()), \
                 mock.patch.object(app, "_auto_ensure_mercado_house", mock.AsyncMock()), \
                 mock.patch.object(app, "_auto_open_pos", mock.AsyncMock()), \
                 mock.patch.object(app, "_auto_download_from_pos", download):
                path, df = asyncio.run(app.auto_download_solo_articulos("prueba", "prueba"))
                self.assertTrue(path.is_file())
                self.assertEqual(app.calcular_secuencia_articulos(df)["siguiente"], "A022767")
                self.assertEqual(packs.read_bytes(), b"packs originales")
                self.assertEqual(prices.read_bytes(), b"precios originales")
                browser.close.assert_awaited_once()
                previous = path.read_bytes()

                async def invalid_download(page, name, fallback, staging):
                    source = staging / "listado.xlsx"
                    app.pd.DataFrame({"Contenido incorrecto": ["sin artículos"]}).to_excel(source, index=False)
                    return source

                with mock.patch.object(app, "_auto_download_from_pos", invalid_download):
                    with self.assertRaises(ValueError):
                        asyncio.run(app.auto_download_solo_articulos("prueba", "prueba"))
                self.assertEqual(path.read_bytes(), previous)
                self.assertEqual(packs.read_bytes(), b"packs originales")
                self.assertEqual(prices.read_bytes(), b"precios originales")


class InterfazTests(unittest.TestCase):
    def setUp(self):
        self.root = app.tk.Tk()
        self.root.geometry("1120x720+15000+15000")
        app._configure_ui(self.root)
        self.empresas = mock.patch.object(app, "load_empresas", return_value={7: "PROVEEDOR DE PRUEBA"})
        self.empresas.start()

    def tearDown(self):
        self.root.update_idletasks()
        self.root.destroy()
        self.empresas.stop()

    def articulos(self):
        view = app.TivendoIngresoMasivoArticulosWindow(self.root)
        view._aplicar_catalogo(Path("listado_prueba.xlsx"), catalogo())
        return view

    def assertVisible(self, widget):
        self.root.update()
        self.assertTrue(widget.winfo_ismapped(), str(widget))
        x, y = widget.winfo_rootx() - self.root.winfo_rootx(), widget.winfo_rooty() - self.root.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), self.root.winfo_width() + 1)
        self.assertLessEqual(y + widget.winfo_height(), self.root.winfo_height() + 1)

    def test_categoria_opcional_y_revisar_dos_veces_no_mueve_la_numeracion(self):
        view = self.articulos()
        self.assertEqual(view.var_empresa_nombre.get(), "")
        self.assertEqual(view.var_codigo_inicial.get(), "A022767")
        view._escribir_tabla_articulos([["GALLETAS", "1290", "00123", "G01"], ["JUGO", "1990", "00456", ""]])
        self.assertTrue(view.procesar_lista_paso2())
        first = view.df_import.copy()
        self.assertEqual(first["Código"].tolist(), ["A022767", "A022768"])
        self.assertEqual(first["Id Categoría"].tolist(), ["", ""])
        self.assertTrue(view.procesar_lista_paso2())
        app.pd.testing.assert_frame_equal(first, view.df_import)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ingreso.xlsx"
            with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(path)), mock.patch.object(app.messagebox, "showinfo"):
                view.generar_excel()
            output = app.pd.read_excel(path, dtype=str).fillna("")
            self.assertEqual(output.columns.tolist(), first.columns.tolist())
            self.assertEqual(output["Código"].tolist(), ["A022767", "A022768"])
            self.assertEqual(output["Nombre"].tolist(), ["GALLETAS - G01", "JUGO - 00456"])
            self.assertEqual(output["Código barra externo"].tolist(), ["MHG01", "MH00456"])
            self.assertEqual(output["Id Categoría"].tolist(), ["", ""])
        view.var_empresa_nombre.set("PROVEEDOR DE PRUEBA")
        self.assertTrue(view.procesar_lista_paso2())
        self.assertEqual(view.df_import["Id Categoría"].tolist(), [7, 7])

    def test_practica_no_se_puede_exportar(self):
        view = self.articulos()
        view._ejemplo_articulos()
        self.assertTrue(view.procesar_lista_paso2())
        with mock.patch.object(app.filedialog, "asksaveasfilename") as save, mock.patch.object(app.messagebox, "showinfo"):
            view.generar_excel()
            save.assert_not_called()

    def test_editar_precio_con_columnas_resumidas_modifica_el_precio(self):
        view = self.articulos()
        view._escribir_tabla_articulos([["GALLETAS", "1290", "00123", ""], ["JUGO", "1990", "00456", ""]])
        view.procesar_lista_paso2()
        view._mostrar_paso(3)
        self.root.update()
        row = view.tree.get_children()[0]
        x, y, width, height = view.tree.bbox(row, "Precio")
        view._on_tree_double_click(types.SimpleNamespace(x=x + width // 2, y=y + height // 2))
        view._tree_editor.delete(0, "end")
        view._tree_editor.insert(0, "2000")
        view._tree_editor.event_generate("<FocusOut>")
        self.root.update()
        self.assertEqual(str(view.df_import.iloc[0]["Precio"]), "2000")
        self.assertEqual(view.df_import.iloc[0]["Unidad"], "UN")

    def test_actualizar_listado_sincroniza_inicio_y_asistente(self):
        view = self.articulos()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nuevo_listado.xlsx"
            exportar_catalogo(path)
            df = app.leer_catalogo_articulos(path)
            self.root.start_view = None
            self.root.listado_path = Path("listado_anterior.xlsx")
            self.root.packs_path = Path("packs_anteriores.xlsx")
            self.root._ask_auto_credentials = lambda: ("usuario_prueba", "clave_prueba")
            completed = []

            def success(ruta, catalog):
                view._catalogo_actualizado(ruta, catalog)
                completed.append(ruta)
                self.root.quit()

            with mock.patch.object(app, "AUTO_LAST_LOAD_PATH", Path(directory) / "ultima.json"), \
                 mock.patch.object(app, "save_auto_credentials"), \
                 mock.patch.object(app, "auto_download_solo_articulos", mock.AsyncMock(return_value=(path, df))):
                timeout = self.root.after(3000, self.root.quit)
                app.RootApp._actualizar_solo_articulos(self.root, success)
                self.root.mainloop()
                self.root.after_cancel(timeout)
                self.assertEqual(completed, [path])
                self.assertEqual(self.root.listado_path, view.catalogo_path)
                self.assertEqual(self.root.auto_last_load_text, app.article_download_label(view.catalogo_path))
                self.assertEqual(self.root.packs_path, Path("packs_anteriores.xlsx"))
                self.assertEqual(view.var_codigo_inicial.get(), "A022767")

    def test_controles_esenciales_en_ambos_tamanos(self):
        view = self.articulos()
        view._escribir_tabla_articulos([["A", "10", "001", ""], ["B", "20", "002", ""]])
        view.procesar_lista_paso2()
        for size in ("1120x720", "960x620"):
            self.root.geometry(size + "+15000+15000")
            for step, controls in ((1, (view.btn_actualizar_catalogo, view.entry_codigo_inicial, view.combo_empresa, view.btn_paso2)),
                                   (2, (view.text_nombre, view.text_codext, view.btn_revisar_articulos)),
                                   (3, (view.tree, view.btn_generar_articulos))):
                view._mostrar_paso(step)
                for control in controls:
                    self.assertVisible(control)

    def test_precios_conserva_filas_vacias_y_exporta_formato_original(self):
        view = app.TivendoWindow(self.root)
        self.root.update()
        self.assertTrue(view.stepA.winfo_ismapped())
        view.df_map = app.pd.DataFrame({"Identificador": ["A022765", "A022766"],
                                      "CodigoBarraInterno": ["001", "002"], "Nombre": ["QUESO", "PALMERITAS"]})
        view._actualizar_estado_continuar()
        view._escribir_tabla_precios([["001", "1290"], ["", "1990"], ["002", "2990"]])
        self.assertFalse(view._actualizar_pegado_precios())
        self.assertIn("Fila 2", view.lbl_pegado_precios.cget("text"))
        self.assertEqual(view._read_pasted_lists()[0], ["001", "", "002"])
        view._escribir_tabla_precios([["001", "1290"], ["002", "2990"]])
        view._build_preview_from_paste()
        compact = ("Código", "Nombre", "CodigoBarraInterno", "RangoInicial1", "RangoFinal1", "Precio1", "RangoExistente")
        self.assertEqual(tuple(view.tree["displaycolumns"]), compact)
        view.var_opciones_rangos.set(True)
        view._toggle_opciones_rangos()
        self.assertEqual(tuple(view.tree["displaycolumns"]), compact)
        view.var_opciones_rangos.set(False)
        view._toggle_opciones_rangos()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "precios.xlsx"
            with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(path)), mock.patch.object(app.messagebox, "showinfo"):
                view._export()
            output = app.pd.read_excel(path, dtype=str).fillna("")
            self.assertEqual(output.columns.tolist(), ["Código", "RangoInicial1", "RangoFinal1", "Precio1", "RangoInicial2", "RangoFinal2", "Precio2"])
            self.assertEqual(output["Código"].tolist(), ["A022765", "A022766"])
            self.assertEqual(output["Precio1"].tolist(), ["1290", "2990"])
        for size in ("1120x720", "960x620"):
            self.root.geometry(size + "+15000+15000")
            for step, controls in ((view.stepA, (view.btn_to_paste,)),
                                   (view.stepB, (view.txt_cod, view.txt_prec, view.btn_revisar_precios)),
                                   (view.stepC, (view.tree, view.btn_exportar_precios))):
                view._show(step)
                for control in controls:
                    self.assertVisible(control)


if __name__ == "__main__":
    unittest.main(verbosity=2)
