"""Reproduce el menú de Tivendo que tapa 'Informes de Ventas'.

Ejecutar con Playwright y Microsoft Edge instalados:
    python tools/test_auto_sales_navigation.py
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from buscador_codigos import _auto_click_classic_sales_report


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        try:
            for overlay in (False, True):
                page = await browser.new_page()
                covering_menu = (
                    '<div style="position:absolute;left:0;top:0;width:300px;'
                    'height:100px;background:#eee">Menú superpuesto</div>'
                    if overlay else ""
                )
                await page.set_content(
                    '<a href="#/Ventas/Ventas/InformesDeVenta" '
                    'style="position:absolute;left:20px;top:20px;width:220px;height:40px">'
                    'Informes de Ventas</a>' + covering_menu
                )
                await _auto_click_classic_sales_report(page)
                assert page.url.endswith("#/Ventas/Ventas/InformesDeVenta"), page.url
                await page.close()
        finally:
            await browser.close()
    print("Navegación normal y con menú superpuesto: correcta")


if __name__ == "__main__":
    asyncio.run(main())
