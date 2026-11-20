"""Acceso central de Defontana: sin red, contraseñas reales ni ventanas."""
import asyncio
import unittest
from unittest import mock

import buscador_codigos as app
from tools.test_defontana_portal import open_with_clock


def form_page(url=app.DEFONTANA_LOGIN_URL):
    page = mock.Mock(url=url, goto=mock.AsyncMock(), wait_for_function=mock.AsyncMock())
    user = mock.Mock(fill=mock.AsyncMock(), wait_for=mock.AsyncMock())
    secret = mock.Mock(fill=mock.AsyncMock(), wait_for=mock.AsyncMock())
    confirm = mock.Mock(click=mock.AsyncMock(), wait_for=mock.AsyncMock())
    page.get_by_label.return_value.or_.return_value.filter.return_value.first = user
    page.locator.return_value.filter.return_value.first = secret
    page.get_by_role.return_value.filter.return_value.first = confirm
    return page, user, secret, confirm


class DefontanaLoginTests(unittest.TestCase):
    def setUp(self):
        self.log = mock.patch.object(app, "_auto_log")
        self.log.start()
        self.addCleanup(self.log.stop)

    def test_abre_solo_el_portal_y_envia_una_vez_con_confirmar(self):
        page, user, secret, confirm = form_page()
        with mock.patch.object(app, "_auto_wait_defontana_login", mock.AsyncMock()) as ready:
            asyncio.run(app._auto_login_defontana(page, "prueba@example.invalid", "clave-ficticia"))
        page.goto.assert_awaited_once_with(
            "https://portal.defontana.com/login", wait_until="domcontentloaded", timeout=30000)
        user.fill.assert_awaited_once_with("prueba@example.invalid")
        secret.fill.assert_awaited_once_with("clave-ficticia")
        confirm.click.assert_awaited_once()
        ready.assert_awaited_once_with(page)
        self.assertEqual(page.get_by_role.call_args.kwargs["name"].pattern, "^Confirmar$")

    def test_sesion_existente_no_vuelve_a_enviar_credenciales(self):
        page, user, secret, confirm = form_page("https://portal.defontana.com/dashboard")
        with mock.patch.object(app, "_auto_wait_defontana_login", mock.AsyncMock()) as ready:
            asyncio.run(app._auto_login_defontana(page, "prueba", "ficticia"))
        ready.assert_awaited_once()
        user.fill.assert_not_awaited()
        secret.fill.assert_not_awaited()
        confirm.click.assert_not_awaited()

    def test_no_ingresa_datos_si_redirige_al_login_de_tivendo_o_a_otro_host(self):
        for url in ("https://tivendoapp.defontana.com/login", "https://erp.defontana.com/login",
                    "https://portal.defontana.com.example.invalid/login"):
            with self.subTest(url=url):
                page, user, secret, confirm = form_page(url)
                with self.assertRaisesRegex(app.AutoDownloadError, "No se enviaron credenciales"):
                    asyncio.run(app._auto_login_defontana(page, "prueba", "ficticia"))
                user.fill.assert_not_awaited()
                secret.fill.assert_not_awaited()
                confirm.click.assert_not_awaited()

    def test_clic_con_resultado_desconocido_no_repite_el_envio(self):
        page, _user, _secret, confirm = form_page()
        confirm.click.side_effect = TimeoutError("Confirmación sin respuesta")
        with self.assertRaises(app.DefontanaLoginUnconfirmed):
            asyncio.run(app._auto_retry("login", lambda: app._auto_login_defontana(page, "prueba", "ficticia")))
        confirm.click.assert_awaited_once()
        page.goto.assert_awaited_once()

    def test_tiempo_agotado_despues_de_confirmar_no_reenvia_ni_afirma_clave_incorrecta(self):
        page, _user, _secret, confirm = form_page()
        with mock.patch.object(app, "_auto_wait_defontana_login", mock.AsyncMock(side_effect=TimeoutError())), \
             self.assertRaises(app.DefontanaLoginUnconfirmed):
            asyncio.run(app._auto_retry("login", lambda: app._auto_login_defontana(page, "prueba", "ficticia")))
        confirm.click.assert_awaited_once()

    def test_cancelar_el_acceso_no_se_convierte_en_error_ni_en_reintento(self):
        page, _user, _secret, confirm = form_page()
        with mock.patch.object(app, "_auto_wait_defontana_login", mock.AsyncMock(side_effect=asyncio.CancelledError)), \
             self.assertRaises(asyncio.CancelledError):
            asyncio.run(app._auto_retry("login", lambda: app._auto_login_defontana(page, "prueba", "ficticia")))
        confirm.click.assert_awaited_once()


class PortalResultTests(unittest.TestCase):
    def page(self, url, *, ready=0, rejected=0, blocked=0):
        page = mock.Mock(url=url)
        locators = []
        for count in (ready, rejected, blocked):
            locator = mock.Mock()
            locator.filter.return_value.count = mock.AsyncMock(return_value=count)
            locators.append(locator)
        page.get_by_text.side_effect = locators
        return page

    def test_dashboard_con_modulos_confirma_el_acceso(self):
        page = self.page("https://portal.defontana.com/dashboard", ready=1)
        asyncio.run(open_with_clock(lambda: app._auto_wait_defontana_login(page)))

    def test_dashboard_sin_modulos_o_texto_correcto_en_host_incorrecto_no_confirma(self):
        for url, ready in (("https://portal.defontana.com/dashboard", 0),
                           ("https://tivendoapp.defontana.com/dashboard", 1)):
            with self.subTest(url=url), self.assertRaisesRegex(app.DefontanaLoginUnconfirmed, "no confirma"):
                page = self.page(url, ready=ready)
                asyncio.run(open_with_clock(lambda: app._auto_wait_defontana_login(page)))

    def test_rechazo_explicito_se_distingue_de_una_espera_agotada(self):
        page = self.page(app.DEFONTANA_LOGIN_URL, rejected=1)
        with self.assertRaises(app.TivendoLoginError):
            asyncio.run(open_with_clock(lambda: app._auto_wait_defontana_login(page)))

    def test_bloqueo_o_verificacion_no_borra_la_clave_como_si_fuera_incorrecta(self):
        page = self.page(app.DEFONTANA_LOGIN_URL, rejected=1, blocked=1)
        with self.assertRaises(app.DefontanaLoginUnconfirmed):
            asyncio.run(open_with_clock(lambda: app._auto_wait_defontana_login(page)))


if __name__ == "__main__":
    unittest.main()
