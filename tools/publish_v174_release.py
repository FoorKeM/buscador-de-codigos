"""Publica el paquete ya validado; usa gh y el acceso guardado de Git en memoria."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.prepare_v174_release import ROOT, TAG, digest, normalized, verify_executable

REPO = "FoorKeM/buscador-de-codigos"
GH = Path(tempfile.gettempdir()) / "buscador-release-gh" / "gh.exe"
PACKAGE = ROOT / "dist" / f"BuscadorCodigos-{TAG}.zip"
NOTES = ROOT / "dist" / "release-notes-v174.md"
LAUNCHER = ROOT / "dist" / "release-assets-v174" / "BuscadorCodigos.exe"
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GH_PROMPT_DISABLED="1")
ENV.pop("GH_DEBUG", None)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, env=ENV, text=True,
                          capture_output=True, check=True).stdout.strip()


def gh(*args):
    return subprocess.run([str(GH), *args], cwd=ROOT, env=ENV, text=True,
                          encoding="utf-8", capture_output=True, check=True,
                          timeout=300).stdout.strip()


def api(path):
    return json.loads(gh("api", f"repos/{REPO}/{path}"))


def release():
    return next((item for item in api("releases?per_page=30") if item["tag_name"] == TAG), None)


def inspect():
    repo = json.loads(gh("api", f"repos/{REPO}"))
    latest = api("releases/latest")
    checks = api("commits/master/check-runs")["check_runs"]
    status = api("commits/master/status")
    assert repo["default_branch"] == "master" and repo["permissions"]["push"]
    assert latest["tag_name"] in ("v167", TAG), "Cambió la versión oficial; revisar antes de reemplazarla."
    assert all(c["status"] == "completed" and c["conclusion"] in ("success", "neutral", "skipped") for c in checks)
    assert all(s["state"] == "success" for s in status["statuses"])
    current = release()
    print(json.dumps({"repository": REPO, "default_branch": repo["default_branch"],
                      "latest": latest["tag_name"], "checks": len(checks), "statuses": len(status["statuses"]),
                      "v174": {"draft": current["draft"], "id": current["id"]} if current else None,
                      "assets": [{"name": a["name"], "size": a["size"]} for a in latest["assets"]]}, ensure_ascii=False), flush=True)


def prepare_launcher():
    """Conservar la descarga del mismo lanzador 1.1 ya distribuido en v167."""
    import marshal
    from PyInstaller.archive.readers import CArchiveReader
    previous = api("releases/tags/v167")
    asset = next(a for a in previous["assets"] if a["name"] == LAUNCHER.name)
    LAUNCHER.parent.mkdir(exist_ok=True)
    if not LAUNCHER.exists():
        gh("release", "download", "v167", "--repo", REPO, "--pattern", LAUNCHER.name, "--dir", str(LAUNCHER.parent))
    assert LAUNCHER.stat().st_size == asset["size"]
    if asset.get("digest"):
        assert "sha256:" + digest(LAUNCHER) == asset["digest"]
    packed = marshal.loads(CArchiveReader(str(LAUNCHER)).extract("launcher"))
    expected = compile((ROOT / "launcher.py").read_bytes(), "launcher.py", "exec", dont_inherit=True)
    assert normalized(packed) == normalized(expected), "El lanzador no coincide con la fuente estable."
    print("Lanzador habitual 1.1 de v167 verificado; se conserva la misma descarga independiente.", flush=True)


def verify_asset(item):
    report = json.loads((ROOT / "dist" / "validation-v174.json").read_text(encoding="utf-8"))
    assert digest(PACKAGE) == report["zip_sha256"]
    # Comprobar también los bytes recuperados de GitHub antes de publicar el borrador.
    with tempfile.TemporaryDirectory(prefix="buscador-release-download-") as folder:
        for path in (PACKAGE, LAUNCHER):
            asset = next(a for a in item["assets"] if a["name"] == path.name)
            assert asset["state"] == "uploaded" and asset["size"] == path.stat().st_size
            if asset.get("digest"):
                assert asset["digest"] == "sha256:" + digest(path)
            gh("release", "download", TAG, "--repo", REPO, "--pattern", path.name, "--dir", folder)
            assert digest(Path(folder) / path.name) == digest(path)
    print("Descargas de GitHub: ZIP y lanzador coinciden con los archivos validados.", flush=True)


def publish():
    inspect()
    prepare_launcher()
    sha = git("rev-parse", "HEAD")
    git("diff", "--exit-code", "HEAD", "--", "buscador_codigos.py", "launcher.py")
    verify_executable(ROOT / "dist" / "BuscadorCodigos-v174" / "BuscadorCodigos-v174.exe")
    git("fetch", "origin", "master")
    git("merge-base", "--is-ancestor", "origin/master", "HEAD")
    item = release()
    if item and not item["draft"]:
        verify()
        return
    git("push", "origin", "HEAD:refs/heads/master")
    remote_tag = git("ls-remote", "origin", "refs/tags/v174", "refs/tags/v174^{}")
    if remote_tag:
        assert sha in remote_tag, "El tag remoto v174 corresponde a otro commit."
    else:
        if git("tag", "--list", TAG):
            assert git("rev-list", "-n", "1", TAG) == sha
        else:
            git("tag", "-a", TAG, "-m", "v174: descargas recuperables y cancelación de actualizaciones", sha)
        git("push", "origin", "refs/tags/v174")
    if item is None:
        gh("release", "create", TAG, "--repo", REPO, "--verify-tag", "--target", sha,
           "--draft", "--title", "v174 · Actualizaciones más resistentes de los cuatro datos",
           "--notes-file", str(NOTES))
        item = release()
    assert item and item["draft"] and not item["prerelease"]
    for path in (PACKAGE, LAUNCHER):
        if not any(a["name"] == path.name for a in item["assets"]):
            print(f"Subiendo {path.name} ({path.stat().st_size:,} bytes) al borrador…", flush=True)
            gh("release", "upload", TAG, str(path), "--repo", REPO)
    verify_asset(release())
    gh("release", "edit", TAG, "--repo", REPO, "--draft=false", "--prerelease=false", "--latest",
       "--notes-file", str(NOTES))
    verify()


def verify():
    latest = api("releases/latest")
    assert latest["tag_name"] == TAG and not latest["draft"] and not latest["prerelease"]
    sha = git("rev-parse", "HEAD")
    assert api("commits/master")["sha"] == api(f"commits/{TAG}")["sha"] == sha
    verify_asset(latest)
    import launcher
    installed = launcher._get_latest_release_info()
    assert installed["tag"] == TAG and installed["size"] == PACKAGE.stat().st_size
    print(json.dumps({"published": latest["html_url"], "tag": TAG, "commit": sha,
                      "launcher_detects": installed["tag"], "asset": PACKAGE.name}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    credential = subprocess.run(["git", "credential", "fill"], cwd=ROOT, env=ENV,
        input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True)
    fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    if credential.returncode or not fields.get("password"):
        raise SystemExit("No hay acceso guardado de GitHub disponible para publicar sin abrir ventanas.")
    ENV["GH_TOKEN"] = fields["password"]
    {"inspect": inspect, "prepare-launcher": prepare_launcher, "publish": publish, "verify": verify}[sys.argv[1]]()
