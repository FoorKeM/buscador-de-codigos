"""Recuperación de descargas, sin iniciar interfaces ni sesiones reales."""
import asyncio
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import buscador_codigos as app
from tools.test_defontana_portal import open_with_clock


class Events:
    def __init__(self):
        self.listeners = {}
        self.close = mock.AsyncMock()
        self.is_closed = lambda: False

    def on(self, event, callback):
        self.listeners.setdefault(event, []).append(callback)

    def remove_listener(self, event, callback):
        self.listeners[event].remove(callback)

    def emit(self, event, value):
        for callback in self.listeners.get(event, [])[:]:
            callback(value)

    def assert_no_listeners(self, testcase):
        testcase.assertTrue(all(not callbacks for callbacks in self.listeners.values()))


class PriceExportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.page, self.popup = Events(), Events()
        self.export = mock.Mock(wait_for=mock.AsyncMock(), click=mock.AsyncMock())
        self.frame = mock.Mock()
        self.frame.locator.return_value.last = self.export
        self.download = SimpleNamespace(failure=mock.AsyncMock(return_value=None))
        self.log = mock.patch.object(app, "_auto_log")
        self.log.start()
        self.addCleanup(self.log.stop)

    async def run_export(self):
        return await app._auto_wait_price_export_download(self.page, self.frame)

    async def test_descarga_directa_se_escucha_antes_de_pulsar_exportar(self):
        self.export.click.side_effect = lambda **_: self.page.emit("download", self.download)
        self.assertIs(await self.run_export(), self.download)
        self.export.click.assert_awaited_once()
        self.page.assert_no_listeners(self)

    async def test_descarga_al_abrirse_popup_no_se_pierde(self):
        def click(**_):
            self.page.emit("popup", self.popup)
            self.popup.emit("download", self.download)

        self.export.click.side_effect = click
        with mock.patch.object(app, "_auto_wait_light", mock.AsyncMock()):
            self.assertIs(await self.run_export(), self.download)
        self.popup.close.assert_awaited_once()
        self.page.assert_no_listeners(self)
        self.popup.assert_no_listeners(self)

    async def test_confirmacion_popup_puede_descargar_en_cualquiera_de_las_dos_paginas(self):
        for origin in (self.page, self.popup):
            with self.subTest(origin=origin):
                self.export.click.side_effect = lambda **_: self.page.emit("popup", self.popup)

                async def confirm(_popup):
                    origin.emit("download", self.download)
                    return True

                with mock.patch.object(app, "_auto_wait_light", mock.AsyncMock()), \
                     mock.patch.object(app, "_auto_try_confirm_popup_download", side_effect=confirm):
                    self.assertIs(await self.run_export(), self.download)
                self.page.assert_no_listeners(self)
                self.popup.assert_no_listeners(self)

    async def test_cancelar_cierra_popup_y_retira_escuchas(self):
        opened = asyncio.Event()

        def click(**_):
            self.page.emit("popup", self.popup)
            opened.set()

        self.export.click.side_effect = click
        with mock.patch.object(app, "_auto_wait_light", mock.AsyncMock()), \
             mock.patch.object(app, "_auto_try_confirm_popup_download", mock.AsyncMock(return_value=False)):
            task = asyncio.create_task(self.run_export())
            await opened.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.popup.close.assert_awaited_once()
        self.page.assert_no_listeners(self)
        self.popup.assert_no_listeners(self)

    async def test_fallo_del_clic_retira_escuchas(self):
        self.export.click.side_effect = TimeoutError("Exportar bloqueado")
        with self.assertRaisesRegex(TimeoutError, "Exportar bloqueado"):
            await self.run_export()
        self.page.assert_no_listeners(self)

    async def test_popup_permanece_abierto_hasta_terminar_la_descarga(self):
        def click(**_):
            self.page.emit("popup", self.popup)
            self.popup.emit("download", self.download)

        async def finish():
            self.popup.close.assert_not_awaited()
            await asyncio.sleep(0)
            return None

        self.export.click.side_effect = click
        self.download.failure.side_effect = finish
        with mock.patch.object(app, "_auto_wait_light", mock.AsyncMock()):
            self.assertIs(await self.run_export(), self.download)
        self.popup.close.assert_awaited_once()

    async def test_descarga_interrumpida_no_se_devuelve_como_correcta(self):
        self.export.click.side_effect = lambda **_: self.page.emit("download", self.download)
        self.download.failure.return_value = "cancelada"
        with self.assertRaisesRegex(app.AutoDownloadError, "no completó la descarga"):
            await self.run_export()
        self.page.assert_no_listeners(self)

    async def test_error_de_espera_distingue_ausencia_de_descarga(self):
        with mock.patch.object(app.asyncio, "wait_for", mock.AsyncMock(side_effect=asyncio.TimeoutError)), \
             self.assertRaisesRegex(app.AutoDownloadError, "No comenzó la descarga"):
            await self.run_export()
        self.page.assert_no_listeners(self)


class PriceReportTests(unittest.TestCase):
    def test_reutiliza_informe_visible_sin_volver_a_abrir_ventas(self):
        page = mock.Mock()
        page.locator.return_value.last.is_visible = mock.AsyncMock(return_value=True)
        with mock.patch.object(app, "_auto_click_classic_sales_report", mock.AsyncMock()) as sales, \
             mock.patch.object(app, "_auto_click_lista_precios_tab", mock.AsyncMock()), \
             mock.patch.object(app, "_auto_get_price_report_frame", mock.AsyncMock(return_value="formulario")):
            result = asyncio.run(app._auto_open_price_report(page, mock.Mock()))
        self.assertEqual(result, "formulario")
        sales.assert_not_awaited()
        page.reload.assert_not_called()

    def test_recarga_el_informe_incompleto_en_la_misma_sesion(self):
        page = mock.Mock(reload=mock.AsyncMock())
        page.locator.return_value.last.is_visible = mock.AsyncMock(return_value=True)
        with mock.patch.object(app, "_auto_click_lista_precios_tab", mock.AsyncMock()) as tab, \
             mock.patch.object(app, "_auto_get_price_report_frame", mock.AsyncMock(
                 side_effect=[app.AutoDownloadError("Iframe incompleto"), "formulario"])), \
             mock.patch.object(app, "_auto_navigation_diagnostic", mock.AsyncMock()):
            result = asyncio.run(app._auto_open_price_report(page, mock.Mock()))
        self.assertEqual(result, "formulario")
        page.reload.assert_awaited_once_with(wait_until="domcontentloaded", timeout=30000)
        self.assertEqual(tab.await_count, 2)

    def test_un_radio_ajeno_no_se_confunde_con_el_formulario(self):
        unrelated = mock.Mock()
        unrelated.locator.side_effect = lambda selector: SimpleNamespace(
            count=mock.AsyncMock(return_value=0 if selector == "select" else 1))
        page = SimpleNamespace(frames=[unrelated])
        with self.assertRaisesRegex(app.AutoDownloadError, "formulario de Lista de Precios"):
            asyncio.run(open_with_clock(lambda: app._auto_get_price_report_frame(page)))

    def test_lista_ausente_no_exporta_y_muestra_la_etapa(self):
        frame = mock.Mock(evaluate=mock.AsyncMock(side_effect=["ok-text", [{"v": "1", "t": "OTRA LISTA"}]]))
        select = frame.locator.return_value.first
        select.wait_for = mock.AsyncMock()
        select.locator.return_value.first.wait_for = mock.AsyncMock()
        page = mock.Mock()
        with mock.patch.object(app, "_auto_open_price_report", mock.AsyncMock(return_value=frame)), \
             mock.patch.object(app, "_auto_active_price_list_name", return_value="LISTA CONFIGURADA"), \
             mock.patch.object(app, "_auto_navigation_diagnostic", mock.AsyncMock()), \
             mock.patch.object(app, "_auto_wait_price_export_download", mock.AsyncMock()) as export, \
             mock.patch.object(app, "_auto_log"), \
             self.assertRaisesRegex(app.AutoDownloadError, "Seleccionar la lista.*LISTA CONFIGURADA"):
            asyncio.run(app._auto_download_price_ranges(page, Path(".")))
        export.assert_not_awaited()


class ProviderRecoveryTests(unittest.TestCase):
    def test_boton_ausente_recarga_y_descarga_una_sola_vez(self):
        page = mock.Mock(set_viewport_size=mock.AsyncMock(), reload=mock.AsyncMock())
        export = mock.Mock(click=mock.AsyncMock(), dispose=mock.AsyncMock())

        async def save(path):
            Path(path).write_bytes(b"fixture")

        @asynccontextmanager
        async def expect_download(**_):
            yield SimpleNamespace(value=asyncio.sleep(0, result=SimpleNamespace(save_as=save)))

        page.expect_download = expect_download
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(app, "_auto_open_article_master", mock.AsyncMock()), \
             mock.patch.object(app, "_auto_find_category_export", mock.AsyncMock(
                 side_effect=[app.AutoDownloadError("No apareció Categorías"), export])), \
             mock.patch.object(app, "_auto_navigation_diagnostic", mock.AsyncMock()), \
             mock.patch.object(app, "leer_proveedores_defontana", return_value={7: "Proveedor"}):
            result = asyncio.run(app._auto_download_provider_categories(page, Path(directory), mock.Mock()))
        self.assertEqual(result, {7: "Proveedor"})
        page.reload.assert_awaited_once()
        export.click.assert_awaited_once()
        export.dispose.assert_awaited_once()
        page.remove_listener.assert_called_once_with("requestfailed", app._auto_log_provider_navigation_failure)

    def test_cancelar_no_recarga_ni_descarga_y_retira_escucha(self):
        page = mock.Mock(set_viewport_size=mock.AsyncMock())
        with mock.patch.object(app, "_auto_open_article_master", mock.AsyncMock()), \
             mock.patch.object(app, "_auto_find_category_export", mock.AsyncMock(side_effect=asyncio.CancelledError)), \
             self.assertRaises(asyncio.CancelledError):
            asyncio.run(app._auto_download_provider_categories(page, Path("."), mock.Mock()))
        page.reload.assert_not_called()
        page.expect_download.assert_not_called()
        page.remove_listener.assert_called_once()


if __name__ == "__main__":
    unittest.main()
