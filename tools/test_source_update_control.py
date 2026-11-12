"""Reintentos y cancelación de las descargas con sesiones simuladas."""
import asyncio
import tempfile
import threading
import unittest
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import buscador_codigos as app


class SourceDownloadControlTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stored = self.directory / "downloads"
        self.stored.mkdir()
        self.browser = SimpleNamespace(close=mock.AsyncMock())
        self.cancel = threading.Event()
        self.messages = []
        self.finished = mock.Mock()
        self.started = mock.Mock()
        self.module = ModuleType("playwright.async_api")

        @asynccontextmanager
        async def playwright():
            yield object()

        self.module.async_playwright = playwright
        self.stack.enter_context(mock.patch.dict("sys.modules", {
            "playwright": ModuleType("playwright"), "playwright.async_api": self.module,
        }))
        self.stack.enter_context(mock.patch.object(app, "APP_DATA_DIR", self.directory))
        self.stack.enter_context(mock.patch.object(app, "AUTO_DOWNLOAD_DIR", self.stored))
        self.stack.enter_context(mock.patch.object(app, "_auto_log"))
        self.stack.enter_context(mock.patch.object(app, "_auto_pause", mock.AsyncMock()))
        self.stack.enter_context(mock.patch.object(app, "_auto_new_page",
            mock.AsyncMock(return_value=(self.browser, object(), object()))))
        self.stack.enter_context(mock.patch.object(app, "_auto_login_tivendo", mock.AsyncMock()))
        self.stack.enter_context(mock.patch.object(app, "_auto_ensure_mercado_house", mock.AsyncMock()))
        self.stack.enter_context(mock.patch.object(app, "_auto_open_pos", mock.AsyncMock()))
        self.stack.enter_context(mock.patch.object(app, "_auto_open_erp", mock.AsyncMock()))
        self.stack.enter_context(mock.patch.object(app, "leer_catalogo_articulos", return_value="catalogo"))
        self.stack.enter_context(mock.patch.object(app, "load_packs_data", return_value="packs"))
        self.stack.enter_context(mock.patch.object(app, "load_price_ranges_data", return_value="precios"))
        self.download = self.stack.enter_context(mock.patch.object(
            app, "_auto_download_from_pos", mock.AsyncMock(side_effect=self.write_export)))

    async def write_export(self, _page, _section, name, folder, **_):
        path = folder / name
        path.write_bytes(b"exportacion comprobada")
        return path

    def run_download(self, keys):
        async def run():
            return await asyncio.wait_for(app.auto_download_sources(
                "usuario", "clave", keys, self.messages.append,
                on_start=self.started, on_result=self.finished, cancel_event=self.cancel), timeout=3)
        return asyncio.run(run())

    def test_reintenta_y_solo_aplica_el_resultado_exitoso(self):
        attempts = 0

        async def flaky(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("Carga temporal")
            return await self.write_export(*args, **kwargs)

        self.download.side_effect = flaky
        loaded, errors = self.run_download(("articulos",))
        self.assertEqual(attempts, 3)
        self.assertEqual(errors, {})
        self.assertEqual(loaded["articulos"][1], "catalogo")
        self.started.assert_called_once_with("articulos")
        self.finished.assert_called_once_with("articulos", loaded["articulos"], None)
        retry_messages = [message for message in self.messages if "Falló. Reintentando" in message]
        self.assertEqual(len(retry_messages), 2)
        self.assertIn("2 de 3", retry_messages[0])
        self.assertIn("3 de 3", retry_messages[1])
        self.assertEqual(len(list(self.stored.iterdir())), 1)
        self.browser.close.assert_awaited_once()

    def test_se_detiene_en_tres_intentos_y_continua_con_el_siguiente(self):
        previous = self.stored / "articulos-anteriores.xlsx"
        previous.write_bytes(b"datos anteriores")

        async def fail_articles(page, section, name, folder, **kwargs):
            if section == "Listado de artículos":
                raise TimeoutError("Fallo persistente")
            return await self.write_export(page, section, name, folder, **kwargs)

        self.download.side_effect = fail_articles
        loaded, errors = self.run_download(("articulos", "packs"))
        self.assertEqual(self.download.await_count, 4)
        self.assertEqual(set(errors), {"articulos"})
        self.assertEqual(set(loaded), {"packs"})
        self.assertEqual(self.finished.call_count, 2)
        self.assertEqual(previous.read_bytes(), b"datos anteriores")
        self.assertEqual(list(self.directory.iterdir()), [self.stored])

    def test_cancelar_interrumpe_una_descarga_y_conserva_lo_ya_terminado(self):
        async def cancel_packs(*args, **kwargs):
            if args[1] == "Packs":
                self.cancel.set()
                await asyncio.Event().wait()
            return await self.write_export(*args, **kwargs)

        self.download.side_effect = cancel_packs
        loaded, errors = self.run_download(("articulos", "packs", "precios"))
        self.assertEqual(set(loaded), {"articulos"})
        self.assertEqual(errors, {})
        self.assertEqual(self.download.await_count, 2)
        self.finished.assert_called_once_with("articulos", loaded["articulos"], None)
        self.browser.close.assert_awaited_once()
        self.assertEqual(list(self.directory.iterdir()), [self.stored])

    def test_cancelar_durante_la_validacion_impide_guardar_el_archivo(self):
        def cancel_parsing(_path):
            self.cancel.set()
            return "catalogo"

        with mock.patch.object(app, "leer_catalogo_articulos", side_effect=cancel_parsing):
            loaded, errors = self.run_download(("articulos",))
        self.assertEqual((loaded, errors), ({}, {}))
        self.finished.assert_not_called()
        self.assertEqual(list(self.stored.iterdir()), [])

    def test_cancelar_entre_intentos_impide_otro_reintento(self):
        self.download.side_effect = TimeoutError("Carga temporal")

        async def cancel_wait(_seconds):
            self.cancel.set()
            await asyncio.sleep(0)

        with mock.patch.object(app, "_auto_pause", side_effect=cancel_wait):
            loaded, errors = self.run_download(("articulos",))
        self.assertEqual((loaded, errors), ({}, {}))
        self.download.assert_awaited_once()

    def test_cancelar_durante_el_login_cierra_la_sesion(self):
        async def wait_login(*_):
            self.cancel.set()
            await asyncio.Event().wait()

        with mock.patch.object(app, "_auto_login_tivendo", side_effect=wait_login):
            loaded, errors = self.run_download(("articulos",))
        self.assertEqual((loaded, errors), ({}, {}))
        self.download.assert_not_awaited()
        self.browser.close.assert_awaited_once()

    def test_reintenta_el_login_si_el_portal_falla_temporalmente(self):
        with mock.patch.object(app, "_auto_login_tivendo",
                mock.AsyncMock(side_effect=[TimeoutError("Portal lento"), None])) as login:
            loaded, errors = self.run_download(("articulos",))
        self.assertEqual(login.await_count, 2)
        self.assertEqual(set(loaded), {"articulos"})
        self.assertEqual(errors, {})
        self.assertTrue(any("Falló al iniciar sesión" in text for text in self.messages))

    def test_credenciales_incorrectas_se_informan_sin_repetir_el_login(self):
        with mock.patch.object(app, "_auto_login_tivendo",
                mock.AsyncMock(side_effect=app.TivendoLoginError("Credenciales incorrectas"))) as login:
            with self.assertRaises(app.TivendoLoginError):
                self.run_download(("articulos",))
        login.assert_awaited_once()
        self.download.assert_not_awaited()
        self.browser.close.assert_awaited_once()


class SourceCancellationUiTests(unittest.TestCase):
    def test_cancelar_desde_inicio_restaura_controles_y_marca_pendientes(self):
        root = object.__new__(app.RootApp)
        root._auto_load_busy = False
        root.start_view = mock.Mock()
        root.after = lambda _delay, callback: callback()
        root._aplicar_fuente = mock.Mock()
        root._refresh_start_sources = mock.Mock()
        article = (Path("articulos.xlsx"), "catalogo")

        def load(report, started, finished):
            started("articulos")
            finished("articulos", article, None)
            started("packs")
            root.start_view.begin_source_update.call_args.kwargs["on_cancel"]()
            self.assertTrue(root._source_cancel_event.is_set())
            report("Este mensaje tardío no debe ocultar la cancelación")
            return {"articulos": article}, {}

        with mock.patch.object(app.threading, "Thread",
                side_effect=lambda target, **_: SimpleNamespace(start=target)):
            root._run_source_job(("articulos", "packs", "precios"), load, batch=True, cancellable=True)
        root.start_view.show_source_cancelling.assert_called_once()
        root.start_view.report_source_update.assert_not_called()
        root._aplicar_fuente.assert_called_once_with("articulos", article)
        root.start_view.set_source_status.assert_any_call("packs", "Cancelado")
        root.start_view.set_source_status.assert_any_call("precios", "Cancelado")
        self.assertEqual(root.start_view.finish_source_update.call_args.args[0], "Actualización cancelada")
        self.assertFalse(root._auto_load_busy)
        self.assertIsNone(root._source_cancel_event)

    def test_el_boton_individual_o_general_vuelve_a_su_accion_original(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                view = object.__new__(app.StartView)
                view.btn_cargar_auto = mock.Mock()
                view.btn_buscar = mock.Mock()
                view.source_update_buttons = {"articulos": mock.Mock()}
                view.update_controls = [view.btn_cargar_auto, view.btn_buscar,
                                        view.source_update_buttons["articulos"]]
                for button in view.update_controls:
                    button.instate.return_value = False
                    button.cget.side_effect = {"text": "Actualizar", "command": "accion_original"}.__getitem__
                view.update_panel = mock.Mock()
                view.update_title = mock.Mock()
                view.update_status = mock.Mock()
                view.update_failures = mock.Mock()
                view.source_failure_details = {}
                view.update_bar = mock.Mock()
                view.article_loaded = True
                view.set_source_status = mock.Mock()
                view.refresh_source_selection_controls = mock.Mock()
                cancel = mock.Mock()
                view.begin_source_update("Actualizar", ("articulos",), batch=batch, on_cancel=cancel)
                button = view.btn_cargar_auto if batch else view.source_update_buttons["articulos"]
                button.config.assert_called_once_with(
                    text="Cancelar actualización", command=cancel, state="normal")
                view.show_source_cancelling()
                button.config.assert_called_with(text="Cancelando…", state="disabled")
                view.finish_source_update("Actualización cancelada", "Se detuvo")
                button.config.assert_called_with(text="Actualizar", command="accion_original")
                button.state.assert_called_with(("!disabled",))
                self.assertFalse(view.update_in_progress)


if __name__ == "__main__":
    unittest.main()
