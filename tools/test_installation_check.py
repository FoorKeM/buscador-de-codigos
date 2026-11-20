"""Comprobación de instalación sin abrir el programa ni leer cuentas guardadas."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

import buscador_codigos as app


class InstallationCheckTests(unittest.TestCase):
    def test_verifica_excel_y_portal_sin_ventanas_ni_cuentas(self):
        module = ModuleType("playwright.async_api")
        module.async_playwright = mock.Mock()
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.dict(sys.modules, {"playwright.async_api": module}), \
             mock.patch.object(app, "RootApp", side_effect=AssertionError("No debe abrir ventanas")), \
             mock.patch.object(app, "load_auto_credentials", side_effect=AssertionError("No debe leer credenciales")), \
             mock.patch.object(sys, "argv", ["buscador", "--check-installation", str(Path(directory) / "check.json")]):
            app.main()
            report = json.loads((Path(directory) / "check.json").read_text(encoding="utf-8"))
        self.assertEqual(report["version"], app.APP_VERSION)
        self.assertEqual(report["login_url"], "https://portal.defontana.com/login")
        self.assertEqual(report["excel"], "correcto")
        module.async_playwright.assert_not_called()

    def test_argumentos_incompletos_no_abren_la_interfaz(self):
        with mock.patch.object(sys, "argv", ["buscador", "--check-installation"]), \
             mock.patch.object(app, "RootApp") as window, self.assertRaises(SystemExit):
            app.main()
        window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
