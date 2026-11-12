"""Editor del acceso utilizado por el Buscador, sin abrir Tk ni acceder a servicios."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import buscador_codigos as app


class CredentialStorageTests(unittest.TestCase):
    def test_conserva_el_formato_anterior_y_la_clave_con_espacios(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(app, "AUTO_CREDENTIALS_PATH", Path(directory) / "credenciales_auto.json"):
            app.AUTO_CREDENTIALS_PATH.write_text(json.dumps(
                {"usuario": "anterior@example.com", "password": "clave anterior"}), encoding="utf-8")
            self.assertEqual(app.load_auto_credentials()["usuario"], "anterior@example.com")
            self.assertTrue(app.save_auto_credentials("nuevo@example.com", " clave con espacios "))
            self.assertEqual(app.load_auto_credentials(),
                             {"usuario": "nuevo@example.com", "password": " clave con espacios "})
            previous = app.AUTO_CREDENTIALS_PATH.read_bytes()
            with mock.patch.object(app.os, "replace", side_effect=OSError("Disco no disponible")):
                self.assertFalse(app.save_auto_credentials("sin guardar@example.com", "otra clave"))
            self.assertEqual(app.AUTO_CREDENTIALS_PATH.read_bytes(), previous)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)


class CredentialEditorTests(unittest.TestCase):
    def make_root(self):
        root = object.__new__(app.RootApp)
        root._credentials_window = None
        root._auto_load_busy = False
        root.winfo_rootx = mock.Mock(return_value=100)
        root.winfo_rooty = mock.Mock(return_value=100)
        root.winfo_width = mock.Mock(return_value=1120)
        root.winfo_height = mock.Mock(return_value=720)
        return root

    def test_la_tuerca_permite_editar_y_se_bloquea_durante_una_actualizacion(self):
        root = self.make_root()
        root._ask_auto_credentials = mock.Mock()
        root._open_settings()
        root._ask_auto_credentials.assert_called_once_with(force_prompt=True)
        root._auto_load_busy = True
        root._open_settings()
        self.assertEqual(root._ask_auto_credentials.call_count, 1)

    def test_el_acceso_guardado_se_utiliza_sin_abrir_un_editor(self):
        root = self.make_root()
        with mock.patch.object(app, "load_auto_credentials",
                return_value={"usuario": "cuenta@example.com", "password": "guardada"}), \
             mock.patch.object(app.tk, "Toplevel") as window:
            self.assertEqual(root._ask_auto_credentials(), ("cuenta@example.com", "guardada"))
        window.assert_not_called()

    def test_el_editor_guarda_y_se_cierra_o_permita_cancelar(self):
        for accept in (True, False):
            with self.subTest(accept=accept):
                root = self.make_root()
                buttons = []
                dialog = mock.Mock()
                dialog.winfo_width.return_value = 500
                dialog.winfo_height.return_value = 400

                def button(*args, **kwargs):
                    buttons.append(kwargs)
                    return mock.Mock()

                def wait(_dialog):
                    label = "Guardar" if accept else "Cancelar"
                    next(item["command"] for item in buttons if item["text"] == label)()

                root.wait_window = wait
                with mock.patch.object(app, "load_auto_credentials",
                        return_value={"usuario": "cuenta@example.com", "password": " clave "}), \
                     mock.patch.object(app, "save_auto_credentials", return_value=True) as save, \
                     mock.patch.object(app.tk, "Toplevel", return_value=dialog), \
                     mock.patch.object(app.tk, "StringVar",
                         side_effect=lambda value: mock.Mock(get=mock.Mock(return_value=value))), \
                     mock.patch.object(app.ttk, "Frame"), mock.patch.object(app.ttk, "Label"), \
                     mock.patch.object(app.ttk, "Entry") as entry, \
                     mock.patch.object(app.ttk, "Button", side_effect=button):
                    result = root._ask_auto_credentials(force_prompt=True)
                if accept:
                    save.assert_called_once_with("cuenta@example.com", " clave ")
                    self.assertEqual(result, ("cuenta@example.com", " clave "))
                else:
                    save.assert_not_called()
                    self.assertIsNone(result)
                dialog.destroy.assert_called_once()
                self.assertIsNone(root._credentials_window)
                self.assertEqual(entry.call_args_list[1].kwargs["show"], "*")



if __name__ == "__main__":
    unittest.main()
