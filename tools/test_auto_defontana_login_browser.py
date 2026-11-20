"""Prueba el login con páginas interceptadas; no contacta ningún servidor de acceso.

Usa exclusivamente credenciales ficticias y un perfil temporal de Edge headless.
Ejecutar: python -m tools.test_auto_defontana_login_browser
"""
import asyncio
import json
from unittest import mock
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

import buscador_codigos as app


FORM = '''<!doctype html><meta charset="utf-8"><h1>Inicio de sesión</h1>
<form id="access">
  <input type="hidden" name="tracking" value="no-es-el-correo">
  <label for="email">Dirección de correo electrónico</label>
  <input id="email" name="email" type="email" autocomplete="username">
  <label for="password">Contraseña</label><input id="password" type="password">
  <button type="submit"><span>Confirmar</span></button>
</form><p id="error" role="alert"></p>
<script>document.querySelector('form').onsubmit = async event => {
  event.preventDefault();
  const response = await fetch('/offline-session', {method:'POST',
    body:JSON.stringify({email:document.querySelector('#email').value,
                        password:document.querySelector('#password').value})});
  const mode = (await response.json()).mode;
  if(mode === 'success') location.href='/dashboard';
  if(mode === 'wrong-screen') location.href='/other';
  if(mode === 'rejected') document.querySelector('#error').textContent='Correo o contraseña incorrectos';
  if(mode === 'blocked') document.querySelector('#error').textContent='Cuenta bloqueada. Demasiados intentos';
  if(mode === 'challenge') document.querySelector('#error').textContent='Ingresa el código de verificación';
};</script>'''


async def main():
    real_wait = app._auto_wait_defontana_login

    async def wait_result(page):
        return await real_wait(page, timeout=3)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        try:
            for mode in ("success", "reused", "rejected", "blocked", "challenge", "pending", "wrong-screen"):
                context = await browser.new_context(offline=True, service_workers="block")
                submissions, unexpected, logs = [], [], []

                async def serve(route):
                    url = urlsplit(route.request.url)
                    if url.hostname != "portal.defontana.com":
                        unexpected.append(route.request.url)
                        await route.abort()
                    elif url.path == "/login":
                        if mode == "reused":
                            await route.fulfill(content_type="text/html; charset=utf-8", body='''
                                <script>setTimeout(()=>location.replace('/dashboard'),50)</script>''')
                        else:
                            await route.fulfill(content_type="text/html; charset=utf-8", body=FORM)
                    elif url.path == "/offline-session":
                        assert route.request.method == "POST"
                        submissions.append(route.request.post_data_json)
                        await route.fulfill(content_type="application/json", body=json.dumps({"mode": mode}))
                    elif url.path in ("/dashboard", "/other"):
                        await route.fulfill(content_type="text/html; charset=utf-8", body='''
                            <h1>Portal Defontana</h1><p>MERCADO HOUSE SPA</p>
                            <button>Módulos recientes</button><button>Todos</button>
                            <div>ERP Digital</div><div>Punto de Ventas</div>''')
                    else:
                        unexpected.append(route.request.url)
                        await route.abort()

                # Todas las solicitudes se contestan aquí o se abortan: no hay red real.
                await context.route("**/*", serve)
                page = await context.new_page()
                error = None
                with mock.patch.object(app, "_auto_wait_defontana_login", side_effect=wait_result), \
                     mock.patch.object(app, "_auto_log", side_effect=logs.append):
                    try:
                        await app._auto_retry("acceso simulado", lambda: app._auto_login_defontana(
                            page, "prueba@example.invalid", "clave-ficticia"), attempts=3)
                    except app.AutoDownloadError as exc:
                        error = exc
                if mode in ("success", "reused"):
                    assert error is None, (mode, str(error), page.url, await page.locator("body").inner_text())
                    assert urlsplit(page.url).path == "/dashboard"
                elif mode == "rejected":
                    assert isinstance(error, app.TivendoLoginError), (mode, error)
                else:
                    assert isinstance(error, app.DefontanaLoginUnconfirmed), (mode, error)
                assert len(submissions) == (0 if mode == "reused" else 1), (mode, len(submissions))
                assert not unexpected, unexpected
                if submissions:
                    assert submissions[0] == {"email": "prueba@example.invalid", "password": "clave-ficticia"}
                assert "clave-ficticia" not in " ".join(logs)
                assert "prueba@example.invalid" not in " ".join(logs)
                await context.close()
                print(f"Portal simulado: {mode}; envíos={len(submissions)}, sin red real: OK", flush=True)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
