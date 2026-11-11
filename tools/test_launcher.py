"""Comprueba la recuperación del lanzador sin abrir ventanas ni descargar archivos."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import launcher


class LauncherRecoveryTests(unittest.TestCase):
    def test_recupera_instalaciones_ausentes_y_reutiliza_las_completas(self):
        latest = {"tag": "v166", "url": "https://example.com/BuscadorCodigos-v166.zip", "size": 100}
        cases = (
            ("primera apertura", "", False, latest, True),
            ("carpeta borrada", "v166", False, latest, True),
            ("carpeta incompleta", "v166", False, latest, True),
            ("recuperacion mediante nueva version", "v162", False, latest, True),
            ("actualizacion disponible", "v162", True, latest, True),
            ("version instalada", "v166", True, latest, False),
            ("sin conexion", "v166", True, OSError("Sin conexion"), False),
        )
        for name, saved_tag, installed, response, download_expected in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as scratch:
                folder = Path(scratch)
                state = folder / "launcher_state.json"
                state.write_text(json.dumps({"tag": saved_tag}), encoding="utf-8")
                versions = folder / "versions"
                exe = versions / saved_tag / f"BuscadorCodigos-{saved_tag}.exe"
                if installed:
                    exe.parent.mkdir(parents=True)
                    exe.write_bytes(b"MZ")
                elif name == "carpeta incompleta":
                    (exe.parent / "_internal").mkdir(parents=True)

                with mock.patch.object(launcher, "STATE_PATH", state), \
                     mock.patch.object(launcher, "VERSIONS_DIR", versions), \
                     mock.patch.object(launcher, "_get_latest_release_info") as get_latest, \
                     mock.patch.object(launcher, "_show_progress_and_install") as install, \
                     mock.patch.object(launcher, "_launch") as launch, \
                     mock.patch.object(launcher.tk, "Tk", side_effect=AssertionError("No debe mostrar el error")):
                    if isinstance(response, Exception):
                        get_latest.side_effect = response
                    else:
                        get_latest.return_value = response
                    launcher.main()
                    if download_expected:
                        install.assert_called_once_with(latest, exe if installed else None)
                        launch.assert_not_called()
                    else:
                        install.assert_not_called()
                        launch.assert_called_once_with(exe)


if __name__ == "__main__":
    unittest.main()
