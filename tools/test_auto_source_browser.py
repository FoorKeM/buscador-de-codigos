"""Descargas en Edge headless con páginas interceptadas: sin red ni credenciales.

Ejecutar con Playwright instalado: python -m tools.test_auto_source_browser
"""
import asyncio
import io
import tempfile
from pathlib import Path
from unittest import mock

from playwright.async_api import async_playwright

import buscador_codigos as app


async def main():
    workbook = io.BytesIO()
    app.pd.DataFrame({"codigo": [7], "nombre": ["Proveedor de prueba"],
                      "codigoPadre": [None], "nivel": [1]}).to_excel(workbook, sheet_name="data", index=False)
    xlsx = workbook.getvalue()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        try:
            for mode in ("direct", "popup-auto", "popup-confirm", "popup-origin"):
                context = await browser.new_context(accept_downloads=True)
                exports = []

                async def serve(route):
                    path = app.urlsplit(route.request.url).path
                    if path.endswith(".xlsx"):
                        exports.append(path)
                        await route.fulfill(status=200, headers={
                            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "Content-Disposition": 'attachment; filename="precios.xlsx"',
                        }, body=xlsx)
                        return
                    if path == "/price-frame":
                        action = ("location.href='/prices.xlsx'" if mode == "direct"
                                  else f"window.open('/{mode}', '_blank')")
                        body = f'''<label><input type="radio" name="lista">Todas</label>
                            <label><input type="radio" name="lista">Una en particular</label>
                            <select><option value="otra">OTRA LISTA</option></select>
                            <script>setTimeout(()=>document.querySelector('select').add(new Option('LISTA CONFIGURADA','correcta')),500)</script>
                            <button onclick="if(document.querySelector('select').value==='correcta'){{{action}}}">Exportar</button>'''
                    elif path == "/popup-auto":
                        body = "<script>setTimeout(()=>location.href='/prices.xlsx',100)</script>"
                    elif path == "/popup-confirm":
                        body = "<script>setTimeout(()=>document.body.innerHTML=`<button onclick=\"location.href='/prices.xlsx'\">Aceptar</button>`,400)</script>"
                    elif path == "/popup-origin":
                        body = '''<button onclick="window.opener.location.href='/prices.xlsx';window.close()">Aceptar</button>'''
                    else:
                        # Formulario deliberadamente tardío, dentro de un iframe.
                        body = '''<button onclick="document.getElementById('content').innerHTML='<iframe name=main src=/price-frame></iframe>'">Lista de Precios</button>
                            <div id=content></div>'''
                    await route.fulfill(content_type="text/html; charset=utf-8", body="<html><body>" + body + "</body></html>")

                await context.route("**/*", serve)
                page = await context.new_page()
                await page.goto("https://erp.defontana.com/informe")
                with tempfile.TemporaryDirectory() as directory, \
                     mock.patch.object(app, "_auto_active_price_list_name", return_value="LISTA CONFIGURADA"), \
                     mock.patch.object(app, "_auto_log"):
                    result = await app._auto_download_price_ranges(page, Path(directory))
                    assert result.read_bytes() == xlsx, mode
                assert exports == ["/prices.xlsx"], (mode, exports)
                report_pages = [p for p in context.pages if app.urlsplit(p.url).hostname == "erp.defontana.com"]
                assert report_pages == [page], (mode, [p.url for p in report_pages])
                await context.close()
                print(f"Precios: {mode}, lista correcta, una exportación, ventana temporal cerrada: OK")

            context = await browser.new_context(accept_downloads=True)

            async def categories(route):
                path = app.urlsplit(route.request.url).path
                if path.endswith(".xlsx"):
                    await route.fulfill(status=200, headers={
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "Content-Disposition": 'attachment; filename="categorias.xlsx"',
                    }, body=xlsx)
                elif path == "/supplier-frame":
                    await route.fulfill(content_type="text/html; charset=utf-8", body='''
                        <h1>Maestro de Artículos</h1><h2>Resultados</h2>
                        <select aria-label="Categorías"><option>Categorías</option></select>
                        <button>Limpiar</button>
                        <button onclick="location.href='/categories.xlsx'"><i>download</i>Categorías</button>''')
                else:
                    await route.fulfill(content_type="text/html; charset=utf-8", body='''
                        <p>ERP Digital</p><iframe name="main" src="/supplier-frame" style="width:100%;height:600px"></iframe>''')

            await context.route("**/*", categories)
            page = await context.new_page()
            await page.goto(app.ERP_ARTICULOS_URL)
            with tempfile.TemporaryDirectory() as directory, mock.patch.object(app, "_auto_log"):
                result = await app._auto_download_provider_categories(page, Path(directory), lambda _: None)
            assert result == {7: "Proveedor de prueba"}, result
            await context.close()
            print("Proveedores: Categorías en iframe junto a Limpiar, Excel validado: OK")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
