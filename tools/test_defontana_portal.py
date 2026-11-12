"""Selección de módulos y navegación, con páginas simuladas."""
import asyncio
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from itertools import product
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import buscador_codigos as app


def page_at(url, ready=0):
    page = mock.Mock(url=url)
    page.is_closed.return_value = False
    page.get_by_text.return_value.filter.return_value.count = mock.AsyncMock(return_value=ready)
    return page


async def open_with_clock(action):
    loop = asyncio.get_running_loop()
    start = loop.time()
    elapsed = 0

    async def pause(_seconds):
        nonlocal elapsed
        elapsed += 2

    with mock.patch.object(loop, "time", side_effect=lambda: start + elapsed), \
         mock.patch.object(app, "_auto_pause", side_effect=pause), \
         mock.patch.object(app, "_auto_log"):
        return await action()


class PortalSelectionTests(unittest.TestCase):
    def setUp(self):
        playwright = ModuleType("playwright.async_api")
        playwright.TimeoutError = TimeoutError
        self.modules = mock.patch.dict(sys.modules, {"playwright.async_api": playwright})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.log = mock.patch.object(app, "_auto_log")
        self.log.start()
        self.addCleanup(self.log.stop)

    def test_busca_el_nombre_en_recientes_sin_cambiar_a_todos(self):
        for name, aliases in (
            ("Punto de Ventas", ["Punto de Ventas", "Punto de Venta"]),
            ("ERP Digital", ["ERP Digital"]),
        ):
            with self.subTest(module=name):
                page = mock.Mock(wait_for_function=mock.AsyncMock())
                page.locator.return_value.click = mock.AsyncMock()
                asyncio.run(app._auto_click_portal_module(page, name))
                self.assertEqual(page.wait_for_function.call_args.kwargs["arg"], aliases)
                page.get_by_text.assert_not_called()
                page.locator.return_value.click.assert_awaited_once()

    def test_busca_en_todos_si_no_aparece_en_recientes(self):
        page = mock.Mock(wait_for_function=mock.AsyncMock(side_effect=[TimeoutError(), None]))
        tab = page.get_by_text.return_value.filter.return_value.first
        tab.click = mock.AsyncMock()
        page.locator.return_value.click = mock.AsyncMock()
        asyncio.run(app._auto_click_portal_module(page, "Punto de Ventas"))
        page.get_by_text.assert_called_once_with("Todos", exact=True)
        tab.click.assert_awaited_once()
        self.assertEqual(page.wait_for_function.await_count, 2)
        page.locator.return_value.click.assert_awaited_once()

    def test_modulo_ausente_da_error_sin_pulsar_otra_tarjeta(self):
        page = mock.Mock(wait_for_function=mock.AsyncMock(side_effect=TimeoutError()))
        page.get_by_text.return_value.filter.return_value.first.click = mock.AsyncMock()
        page.locator.return_value.click = mock.AsyncMock()
        with self.assertRaisesRegex(app.AutoDownloadError, "ERP Digital.*Todos"):
            asyncio.run(app._auto_click_portal_module(page, "ERP Digital"))
        page.locator.return_value.click.assert_not_awaited()


class PortalNavigationTests(unittest.TestCase):
    def test_reutiliza_la_pestana_abierta_en_un_intento_anterior(self):
        portal = page_at("https://portal.defontana.com/dashboard")
        pos = page_at("https://tivendoapp.defontana.com/", ready=1)
        context = SimpleNamespace(pages=[portal, pos])
        with mock.patch.object(app, "_auto_click_portal_module", mock.AsyncMock()) as click:
            result = asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, portal)))
        self.assertIs(result, pos)
        click.assert_not_awaited()

    def test_espera_el_modulo_abierto_sin_confundirlo_con_el_portal_ni_abrir_duplicados(self):
        portal = page_at("https://portal.defontana.com/dashboard")
        pos = page_at("https://tivendoapp.defontana.com/")
        pos.get_by_text.return_value.filter.return_value.count.side_effect = [0, 0, 1]
        context = SimpleNamespace(pages=[portal, pos])
        with mock.patch.object(app, "_auto_click_portal_module", mock.AsyncMock()) as click:
            result = asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, portal)))
        self.assertIs(result, pos)
        click.assert_not_awaited()

    def test_una_pestana_de_login_anterior_no_bloquea_reabrir_el_modulo(self):
        portal = page_at("https://portal.defontana.com/dashboard")
        expired = page_at("https://tivendoapp.defontana.com/login", ready=1)
        pos = page_at("https://tivendoapp.defontana.com/#/inicio", ready=1)
        context = SimpleNamespace(pages=[portal, expired])

        async def select(_page, _name):
            context.pages.append(pos)

        with mock.patch.object(app, "_auto_click_portal_module", side_effect=select) as click:
            result = asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, portal)))
        self.assertIs(result, pos)
        click.assert_awaited_once_with(portal, "Punto de Ventas")

    def test_pos_abre_en_la_misma_pestana_o_en_una_nueva(self):
        for new_tab in (False, True):
            with self.subTest(new_tab=new_tab):
                portal = page_at("https://portal.defontana.com/dashboard", ready=1)
                pos = page_at("https://tivendoapp.defontana.com/", ready=1) if new_tab else portal
                context = SimpleNamespace(pages=[portal])

                async def select(_page, name):
                    self.assertEqual(name, "Punto de Ventas")
                    pos.url = "https://tivendoapp.defontana.com/"
                    if new_tab:
                        context.pages.append(pos)

                with mock.patch.object(app, "_auto_click_portal_module", side_effect=select) as click:
                    result = asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, portal)))
                self.assertIs(result, pos)
                click.assert_awaited_once_with(portal, "Punto de Ventas")

    def test_reintenta_si_el_clic_no_abre_el_modulo(self):
        portal = page_at("https://portal.defontana.com/dashboard", ready=1)
        context = SimpleNamespace(pages=[portal])
        attempts = 0

        async def select(_page, _name):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                portal.url = "https://tivendoapp.defontana.com/"

        with mock.patch.object(app, "_auto_click_portal_module", side_effect=select):
            result = asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, portal)))
        self.assertIs(result, portal)
        self.assertEqual(attempts, 2)

    def test_un_texto_articulos_en_el_portal_no_confirma_punto_de_ventas(self):
        portal = page_at("https://portal.defontana.com/dashboard", ready=1)
        context = SimpleNamespace(pages=[portal])
        with mock.patch.object(app, "_auto_click_portal_module", mock.AsyncMock()), \
             self.assertRaisesRegex(app.AutoDownloadError, "Punto de Ventas"):
            asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, portal)))

    def test_tampoco_confirma_punto_de_ventas_si_abre_erp(self):
        portal = page_at("https://portal.defontana.com/dashboard", ready=1)
        erp = page_at(app.ERP_DASHBOARD_URL, ready=1)
        context = SimpleNamespace(pages=[portal])

        async def select(_page, _name):
            if erp not in context.pages:
                context.pages.append(erp)

        with mock.patch.object(app, "_auto_click_portal_module", side_effect=select), \
             self.assertRaisesRegex(app.AutoDownloadError, "Punto de Ventas"):
            asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, portal)))

    def test_el_host_correcto_sin_menu_visible_no_basta(self):
        pos = page_at("https://tivendoapp.defontana.com/login")
        context = SimpleNamespace(pages=[pos])
        with mock.patch.object(app, "_auto_click_portal_module", mock.AsyncMock()), \
             self.assertRaisesRegex(app.AutoDownloadError, "Punto de Ventas"):
            asyncio.run(open_with_clock(lambda: app._auto_open_pos(context, pos)))


class PosExportNavigationTests(unittest.TestCase):
    def test_reabre_la_direccion_del_listado_si_el_primer_clic_no_completa_la_navegacion(self):
        for section, failure in product(("Listado de artículos", "Packs"), ("route", "export")):
            route = "#/packs" if section == "Packs" else "#/articulos"
            with self.subTest(section=section, failure=failure), tempfile.TemporaryDirectory() as directory:
                page = mock.Mock(url="https://tivendoapp.defontana.com/#/inicio",
                                 goto=mock.AsyncMock(), wait_for_url=mock.AsyncMock())
                link = mock.Mock(get_attribute=mock.AsyncMock(return_value=route),
                                 click=mock.AsyncMock())
                export = mock.Mock(click=mock.AsyncMock(), wait_for=mock.AsyncMock())
                if failure == "route":
                    page.wait_for_url.side_effect = TimeoutError("La aplicación volvió al inicio")
                else:
                    export.wait_for.side_effect = [TimeoutError("Pantalla incompleta"), None]
                button = mock.Mock()
                button.filter.return_value.first = export
                page.get_by_role.side_effect = lambda role, **_: link if role == "link" else button

                async def save(path):
                    Path(path).write_bytes(b"listado correcto")

                download = SimpleNamespace(suggested_filename="listado.xlsx", save_as=save)

                @asynccontextmanager
                async def expect_download(**_):
                    result = asyncio.get_running_loop().create_future()
                    result.set_result(download)
                    yield SimpleNamespace(value=result)

                page.expect_download = expect_download
                with mock.patch.object(app, "_auto_open_pos_section", mock.AsyncMock()), \
                     mock.patch.object(app, "_auto_log"):
                    result = asyncio.run(app._auto_download_from_pos(
                        page, section, "articulos.xlsx", Path(directory)))
                self.assertEqual(result.read_bytes(), b"listado correcto")
                page.goto.assert_awaited_once_with(
                    "https://tivendoapp.defontana.com/" + route,
                    wait_until="domcontentloaded", timeout=30000)
                export.click.assert_awaited_once()

    def test_un_fallo_informa_la_etapa_y_registra_la_ubicacion_sin_tokens(self):
        page = mock.Mock(url="https://tivendoapp.defontana.com/?token=secreto#/articulos?key=privada")
        page.get_by_role.return_value.all_text_contents = mock.AsyncMock(return_value=[])
        messages = []
        with mock.patch.object(app, "_auto_retry", mock.AsyncMock(side_effect=TimeoutError("Menú no disponible"))), \
             mock.patch.object(app, "_auto_log") as log, \
             self.assertRaisesRegex(app.AutoDownloadError, "Abrir el menú de Artículos"):
            asyncio.run(app._auto_download_from_pos(
                page, "Listado de artículos", "articulos.xlsx", Path("."), progress_cb=messages.append))
        self.assertIn("Abrir el menú de Artículos", messages[0])
        records = " ".join(call.args[0] for call in log.call_args_list)
        self.assertIn("#/articulos", records)
        self.assertNotIn("secreto", records)
        self.assertNotIn("privada", records)


if __name__ == "__main__":
    unittest.main()
