"""Empaqueta la v174 probada y verifica ambos lanzadores sin abrir ventanas."""
import hashlib
import json
import marshal
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from types import CodeType, ModuleType, SimpleNamespace
from unittest import mock

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
TAG = "v174"
EXE_SHA = "7c897e43ddddde7331fb25443cf1f84cff6eb0250ff5e27362b6e16d7249ee0d"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalized(code):
    return code.replace(co_filename="buscador_codigos.py", co_consts=tuple(
        normalized(value) if isinstance(value, CodeType) else value for value in code.co_consts))


def verify_executable(path):
    assert digest(path) == EXE_SHA, "El ejecutable cambió desde la prueba del usuario."
    packed = marshal.loads(CArchiveReader(str(path)).extract("buscador_codigos"))
    expected = compile((ROOT / "buscador_codigos.py").read_bytes(), "buscador_codigos.py", "exec", dont_inherit=True)
    assert normalized(packed) == normalized(expected), "El código empaquetado no coincide con la fuente."


def verify_launchers(package, manifest):
    for version, source in (
        ("1.0", subprocess.check_output(["git", "show", "d4e0a62:launcher.py"], cwd=ROOT).decode("utf-8")),
        ("1.1", (ROOT / "launcher.py").read_text(encoding="utf-8")),
    ):
        module = ModuleType("launcher_under_test")
        module.__file__ = str(ROOT / "launcher.py")
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        with tempfile.TemporaryDirectory(prefix="buscador-release-check-") as directory:
            scratch = Path(directory)
            candidate = scratch / package.name
            shutil.copyfile(package, candidate)
            with mock.patch.object(module, "VERSIONS_DIR", scratch / "versions"), \
                 mock.patch.object(module, "tempfile", SimpleNamespace(gettempdir=lambda: str(scratch))):
                exe = module._install_version(candidate, TAG)
                assert exe.name == f"BuscadorCodigos-{TAG}.exe"
                actual = {p.relative_to(exe.parent).as_posix(): digest(p)
                          for p in exe.parent.rglob("*") if p.is_file()}
                assert actual == manifest, "La instalación no conserva todos los archivos del paquete."
                verify_executable(exe)
                latest = {"tag": TAG, "url": f"https://example.com/{package.name}", "size": package.stat().st_size}
                with mock.patch.object(module, "_load_state", return_value={"tag": "v167"}), \
                     mock.patch.object(module, "_get_latest_release_info", return_value=latest), \
                     mock.patch.object(module, "_show_progress_and_install") as install, \
                     mock.patch.object(module, "_launch") as launch, \
                     mock.patch.object(module.tk, "Tk", side_effect=AssertionError("No debe abrir una ventana")):
                    module.main()
                    install.assert_called_once_with(latest, None)
                    launch.assert_not_called()
        print(f"Lanzador {version}: instala el ZIP completo y detecta v174 desde v167.", flush=True)


def main():
    folder = ROOT / "dist" / f"BuscadorCodigos-{TAG}"
    package = folder.with_suffix(".zip")
    exe = folder / f"BuscadorCodigos-{TAG}.exe"
    verify_executable(exe)
    required = [exe.name, "_internal/python312.dll", "_internal/playwright/driver/node.exe"]
    files = [exe] + sorted(p for p in (folder / "_internal").rglob("*") if p.is_file())
    manifest = {p.relative_to(folder).as_posix(): digest(p) for p in files}
    assert set(required).issubset(manifest)
    assert not any("credenciales" in name.lower() or name.endswith("buscador_prefs.json") for name in manifest)
    if not package.exists():
        with zipfile.ZipFile(package, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, path.relative_to(folder).as_posix())
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(manifest)
        for name, sha in manifest.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == sha, name
    verify_launchers(package, manifest)
    report = {"tag": TAG, "zip": str(package), "bytes": package.stat().st_size,
              "files": len(files), "zip_sha256": digest(package), "exe_sha256": EXE_SHA}
    (ROOT / "dist" / "validation-v174.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
