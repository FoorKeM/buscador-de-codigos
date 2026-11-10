"""Carga de Categorías con archivos temporales y sin navegador ni Tk."""
import asyncio
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import buscador_codigos as app


def write_categories(path, rows):
    app.pd.DataFrame(rows, columns=["codigo", "nombre", "codigoPadre", "nivel"]).to_excel(
        path, sheet_name="data", index=False)


class ProviderSyncTests(unittest.TestCase):
    def test_recuerda_la_seleccion_y_marcar_todas_la_restauran(self):
        view = object.__new__(app.StartView)
        view.btn_cargar_auto = mock.Mock()
        view.source_selection = {key: mock.Mock() for key in app.DATA_SOURCES}
        for key, choice in view.source_selection.items():
            choice.get.return_value = key in {"packs", "proveedores"}
            choice.set.side_effect = lambda value, choice=choice: setattr(choice.get, "return_value", value)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(app, "PREF_PATH", Path(directory) / "prefs.json"):
            app.save_prefs({"geometry": "1120x720"})
            view.save_source_selection()
            self.assertEqual(app.load_prefs(), {"geometry": "1120x720", "update_sources": ["packs", "proveedores"]})
            view.btn_cargar_auto.config.assert_called_with(text="Actualizar seleccionados", state="normal")
            view.mark_all_sources()
            self.assertEqual(app.load_prefs()["update_sources"], list(app.DATA_SOURCES))
            view.btn_cargar_auto.config.assert_called_with(text="Actualizar todos los datos", state="normal")

    def test_inicio_muestra_progreso_y_resultado_en_el_panel(self):
        for error in (None, ValueError("Excel inválido")):
            with self.subTest(error=error):
                root = object.__new__(app.RootApp)
                root._auto_load_busy = False
                root.start_view = mock.Mock()
                root.after = lambda _delay, callback: callback()
                root._aplicar_fuente = mock.Mock()
                root._refresh_start_sources = mock.Mock()

                def load(report, started, finished):
                    started("proveedores")
                    report("Buscando Categorías…")
                    if error:
                        finished("proveedores", None, error)
                        root.start_view.set_source_status.assert_called_with("proveedores", "Error")
                        return {}, {"proveedores": error}
                    data = {7: "Proveedor"}
                    finished("proveedores", data, None)
                    root._refresh_start_sources.assert_called_once_with(("proveedores",))
                    return {"proveedores": data}, {}

                with mock.patch.object(app.tk, "Toplevel") as toplevel, \
                     mock.patch.object(app.threading, "Thread", side_effect=lambda target, **_: SimpleNamespace(start=target)), \
                     mock.patch.object(app.messagebox, "showwarning") as warning, \
                     mock.patch.object(app.messagebox, "showinfo") as info:
                    root._run_source_job(("proveedores",), load)
                toplevel.assert_not_called()
                warning.assert_not_called()
                info.assert_not_called()
                root.start_view.begin_source_update.assert_called_once_with("Actualizar proveedores", ("proveedores",), batch=False)
                self.assertIn(mock.call("proveedores", "Actualizando"), root.start_view.set_source_status.call_args_list)
                root.start_view.report_source_update.assert_called_once_with("Buscando Categorías…")
                root.start_view.finish_source_update.assert_called_once()
                self.assertEqual(bool(root.start_view.finish_source_update.call_args.kwargs.get("warning")), bool(error))
                self.assertFalse(root._auto_load_busy)

    def test_erp_sigue_la_nueva_pestana_abierta_desde_el_portal(self):
        portal = mock.Mock(url="https://portal.defontana.com/dashboard")
        portal.is_closed.return_value = False
        erp = mock.Mock(url=app.ERP_DASHBOARD_URL)
        erp.is_closed.return_value = False
        erp.get_by_text.return_value.count = mock.AsyncMock(return_value=1)
        context = SimpleNamespace(pages=[portal], new_page=mock.AsyncMock())
        title = portal.get_by_text.return_value.filter.return_value.last
        title.is_visible = mock.AsyncMock(return_value=True)
        card = title.locator.return_value
        card.count = mock.AsyncMock(return_value=1)
        card.click = mock.AsyncMock(side_effect=lambda **_: context.pages.append(erp))
        with mock.patch.object(app, "_auto_pause", mock.AsyncMock()):
            self.assertIs(asyncio.run(app._auto_open_erp(context, portal)), erp)
        card.click.assert_awaited_once()
        context.new_page.assert_not_awaited()

    def test_erp_usa_ruta_directa_si_el_portal_no_avanza(self):
        portal = mock.Mock(url="https://portal.defontana.com/dashboard")
        portal.is_closed.return_value = False
        title = portal.get_by_text.return_value.filter.return_value.last
        title.is_visible = mock.AsyncMock(return_value=False)
        erp = mock.Mock(url=app.ERP_ARTICULOS_URL, goto=mock.AsyncMock())
        erp.is_closed.return_value = False
        erp.get_by_text.return_value.count = mock.AsyncMock(return_value=1)
        context = SimpleNamespace(pages=[portal])

        async def new_page():
            context.pages.append(erp)
            return erp

        context.new_page = new_page

        async def run():
            loop = asyncio.get_running_loop()
            start = loop.time()
            elapsed = 0

            async def pause(_):
                nonlocal elapsed
                elapsed += 6

            with mock.patch.object(loop, "time", side_effect=lambda: start + elapsed), \
                 mock.patch.object(app, "_auto_pause", side_effect=pause), \
                 mock.patch.object(app, "_auto_log"):
                return await app._auto_open_erp(context, portal, direct_url=app.ERP_ARTICULOS_URL)

        self.assertIs(asyncio.run(run()), erp)
        erp.goto.assert_awaited_once_with(app.ERP_ARTICULOS_URL, wait_until="commit", timeout=10000)

    def test_actualizacion_general_intenta_las_cuatro_fuentes_aunque_falle_una(self):
        module = ModuleType("playwright.async_api")

        @asynccontextmanager
        async def playwright():
            yield object()

        module.async_playwright = playwright
        browser = SimpleNamespace(close=mock.AsyncMock())
        pos = object()
        erp = object()
        events = []

        async def download_pos(_pos, section, filename, folder):
            self.assertIs(_pos, pos)
            if section == "Packs":
                raise ValueError("Packs inválidos")
            source = folder / filename
            source.write_bytes(b"articulos")
            return source

        async def download_prices(_erp, folder):
            self.assertIs(_erp, erp)
            source = folder / "precios.xls"
            source.write_bytes(b"precios")
            return source

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stored = root / "descargas"
            stored.mkdir()
            old_packs = stored / "packs.xlsx"
            old_packs.write_bytes(b"packs anteriores")
            with mock.patch.dict(sys.modules, {"playwright": ModuleType("playwright"), "playwright.async_api": module}), \
                 mock.patch.object(app, "APP_DATA_DIR", root), mock.patch.object(app, "AUTO_DOWNLOAD_DIR", stored), \
                 mock.patch.object(app, "_auto_new_page", mock.AsyncMock(return_value=(browser, object(), object()))), \
                 mock.patch.object(app, "_auto_login_tivendo", mock.AsyncMock()) as login, \
                 mock.patch.object(app, "_auto_ensure_mercado_house", mock.AsyncMock()), mock.patch.object(app, "_auto_log"), \
                 mock.patch.object(app, "_auto_open_pos", mock.AsyncMock(return_value=pos)), \
                 mock.patch.object(app, "_auto_open_erp", mock.AsyncMock(return_value=erp)), \
                 mock.patch.object(app, "_auto_download_from_pos", side_effect=download_pos), \
                 mock.patch.object(app, "_auto_download_price_ranges", side_effect=download_prices), \
                 mock.patch.object(app, "leer_catalogo_articulos", return_value="catalogo"), \
                 mock.patch.object(app, "load_price_ranges_data", return_value=(None, {})), \
                 mock.patch.object(app, "_auto_download_provider_categories", mock.AsyncMock(return_value={7: "Proveedor"})):
                loaded, errors = asyncio.run(app.auto_download_sources(
                    "test", "test", tuple(app.DATA_SOURCES),
                    on_start=lambda key: events.append((key, "inicio")),
                    on_result=lambda key, data, error: events.append((key, "error" if error else "listo"))))
            self.assertEqual(events, [("articulos", "inicio"), ("articulos", "listo"),
                                      ("packs", "inicio"), ("packs", "error"),
                                      ("precios", "inicio"), ("precios", "listo"),
                                      ("proveedores", "inicio"), ("proveedores", "listo")])
            self.assertEqual(set(loaded), {"articulos", "precios", "proveedores"})
            self.assertEqual(set(errors), {"packs"})
            self.assertEqual(loaded["proveedores"], {7: "Proveedor"})
            self.assertEqual(loaded["articulos"][0].read_bytes(), b"articulos")
            self.assertEqual(loaded["precios"][0].read_bytes(), b"precios")
            self.assertEqual(old_packs.read_bytes(), b"packs anteriores")
            self.assertEqual(list(root.iterdir()), [stored])
            login.assert_awaited_once()

    def test_importacion_reemplaza_por_id_y_conserva_la_lista_si_el_excel_es_invalido(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "categorias.xlsx"
            store = Path(directory) / "empresas.json"
            write_categories(path, [(7, "NUEVO NOMBRE", None, 1), (196, "NA", None, 1)])
            view = object.__new__(app.ProvidersView)
            view.data = {7: "Nombre anterior", 12: "Ya no existe"}
            view.winfo_exists = lambda: True
            view.after = lambda _delay, callback: callback()
            view.reload = mock.Mock()
            for name in ("btn_back", "btn_sync", "btn_import", "status"):
                setattr(view, name, mock.Mock())

            with mock.patch.object(app, "EMP_PATH", store), \
                 mock.patch.object(app.filedialog, "askopenfilename", return_value=str(path)), \
                 mock.patch.object(app.threading, "Thread", side_effect=lambda target, **_: SimpleNamespace(start=target)), \
                 mock.patch.object(app.messagebox, "showerror") as show_error:
                app.save_empresas(view.data)
                view._importar_proveedores()
                expected = {7: "NUEVO NOMBRE", 196: "NA"}
                self.assertEqual(app.load_empresas(), expected)
                self.assertEqual(view.data, expected)
                self.assertTrue(path.is_file())

                write_categories(path, [(7, "Uno", None, 1), (7, "Duplicado", None, 1)])
                view._importar_proveedores()
                show_error.assert_called_once()
                self.assertEqual(app.load_empresas(), expected)
                self.assertEqual(view.data, expected)
                view.reload.assert_called_once()

    def test_descarga_de_categorias_se_limpia_con_excel_valido_o_invalido(self):
        module = ModuleType("playwright.async_api")

        @asynccontextmanager
        async def playwright():
            yield object()

        module.async_playwright = playwright
        browser = SimpleNamespace(close=mock.AsyncMock())
        export = mock.Mock(click=mock.AsyncMock(), dispose=mock.AsyncMock())
        export.as_element.return_value = export
        inventory = mock.Mock()
        inventory.name = "main"
        inspection = mock.Mock(get_property=mock.AsyncMock(return_value=export), dispose=mock.AsyncMock())
        inventory.evaluate_handle = mock.AsyncMock(return_value=inspection)
        outer = mock.Mock()
        outer.name = ""
        erp = mock.Mock(url=app.ERP_DASHBOARD_URL, goto=mock.AsyncMock(), set_viewport_size=mock.AsyncMock(),
                        frames=[outer, inventory])
        erp.is_closed.return_value = False
        erp.locator.return_value.first.is_visible = mock.AsyncMock(return_value=False)
        erp.get_by_text.return_value.filter.return_value.first.is_visible = mock.AsyncMock(return_value=False)

        @asynccontextmanager
        async def expect_download(**_):
            yield SimpleNamespace(value=asyncio.sleep(0, result=download))

        erp.expect_download = expect_download
        for rows in ([(196, "ELEPHANT", None, 1)], []):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as directory:
                staging_root = Path(directory)
                downloads = []

                async def save_as(path):
                    downloads.append(Path(path))
                    write_categories(path, rows)

                download = SimpleNamespace(save_as=save_as)
                with mock.patch.dict(sys.modules, {"playwright": ModuleType("playwright"), "playwright.async_api": module}), \
                     mock.patch.object(app, "APP_DATA_DIR", staging_root), \
                     mock.patch.object(app, "_auto_log"), \
                     mock.patch.object(app, "_auto_new_page", mock.AsyncMock(return_value=(browser, object(), object()))), \
                     mock.patch.object(app, "_auto_login_tivendo", mock.AsyncMock()), \
                     mock.patch.object(app, "_auto_ensure_mercado_house", mock.AsyncMock()) as verify_company, \
                     mock.patch.object(app, "_auto_open_erp", mock.AsyncMock(return_value=erp)):
                    sync = app.auto_download_sources("test", "test", ("proveedores",))
                    loaded, errors = asyncio.run(sync)
                    if rows:
                        self.assertEqual(loaded["proveedores"], {196: "ELEPHANT"})
                    else:
                        self.assertIn("vacío", str(errors["proveedores"]))
                    self.assertTrue(verify_company.await_args.kwargs["require_confirmation"])
                erp.goto.assert_awaited_with(app.ERP_ARTICULOS_URL, wait_until="domcontentloaded", timeout=30000)
                self.assertEqual(len(downloads), 1)
                self.assertEqual(list(staging_root.iterdir()), [])
        self.assertEqual(browser.close.await_count, 2)
        self.assertEqual(export.click.await_count, 2)
        self.assertEqual(export.dispose.await_count, 2)
        inventory.evaluate_handle.assert_awaited_with(app._CATEGORY_EXPORT_CONTROL)
        outer.evaluate_handle.assert_not_called()

    def test_maestro_de_articulos_prioriza_el_enlace_del_menu(self):
        erp = mock.Mock(url=app.ERP_DASHBOARD_URL, wait_for_url=mock.AsyncMock(), goto=mock.AsyncMock())
        link = erp.locator.return_value.first
        link.is_visible = mock.AsyncMock(side_effect=[False, True])
        link.click = mock.AsyncMock()
        link.wait_for = mock.AsyncMock()
        inventory = erp.get_by_text.return_value.filter.return_value.first
        inventory.is_visible = mock.AsyncMock(return_value=True)
        inventory.click = mock.AsyncMock()

        asyncio.run(app._auto_open_article_master(erp))

        erp.get_by_text.assert_called_once_with("Inventario", exact=True)
        inventory.click.assert_awaited_once()
        link.wait_for.assert_awaited_once_with(state="visible", timeout=5000)
        link.click.assert_awaited_once()
        route = erp.wait_for_url.await_args.args[0]
        self.assertTrue(route(app.ERP_ARTICULOS_URL))
        self.assertFalse(route(app.ERP_DASHBOARD_URL))
        erp.goto.assert_not_awaited()

    def test_reintenta_abrir_el_maestro_una_vez_antes_de_descargar(self):
        export = mock.Mock(click=mock.AsyncMock(), dispose=mock.AsyncMock())
        download = mock.Mock(save_as=mock.AsyncMock())
        erp = mock.Mock(reload=mock.AsyncMock(), set_viewport_size=mock.AsyncMock())

        @asynccontextmanager
        async def expect_download(**_):
            yield SimpleNamespace(value=asyncio.sleep(0, result=download))

        erp.expect_download = expect_download
        with mock.patch.object(app, "_auto_open_article_master", mock.AsyncMock()) as open_master, \
             mock.patch.object(app, "_auto_find_category_export", side_effect=[app.ArticleMasterNotReady(), export]) as find, \
             mock.patch.object(app, "leer_proveedores_defontana", return_value={7: "Proveedor"}) as read:
            data = asyncio.run(app._auto_download_provider_categories(erp, Path("temporal"), mock.Mock()))

        self.assertEqual(data, {7: "Proveedor"})
        self.assertEqual(open_master.await_count, 2)
        self.assertEqual(find.await_count, 2)
        erp.reload.assert_awaited_once_with(wait_until="domcontentloaded", timeout=30000)
        export.click.assert_awaited_once()
        download.save_as.assert_awaited_once()
        read.assert_called_once()
