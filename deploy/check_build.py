"""Fail the Docker build for missing integrations or invalid patched JavaScript."""
import compileall
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from package_layout import site_packages


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    package = site_packages(root / "venv") / "invokeai"
    dist = package / "frontend" / "web" / "dist"
    assert not (root / ".env").exists(), "Build must not contain a generated .env"
    api_app = (package / "app" / "api_app.py").read_text(encoding="utf-8")
    for router in ("imagerouter", "ifc", "pdf", "design_code", "threed"):
        assert f"app.include_router({router}." in api_app, f"Missing router: {router}"
    assert "app.add_middleware(site_auth.SiteAuthMiddleware)" in api_app
    assert "devbim-studio-sso" in (package / "app" / "api" / "sockets.py").read_text(encoding="utf-8")
    for asset in ("ifcviewer.html", "pdfviewer.html", "design_code_viewer.html"):
        assert (dist / asset).is_file(), f"Missing viewer: {asset}"
    assert compileall.compile_dir(package / "app", quiet=1), "Invalid Python syntax"
    bundles = list((dist / "assets").glob("index-*.js")) + list((dist / "assets").glob("App-*.js"))
    assert bundles, "Missing frontend bundles"
    bundles += list(dist.glob("devbim-*.js"))
    # Parse as modules; do not execute browser code inside Node.
    for bundle in bundles:
        with bundle.open("rb") as source:
            subprocess.run(["node", "--input-type=module", "--check"], stdin=source, check=True)
    print(f"Docker build checks OK ({len(bundles)} JavaScript files)")


if __name__ == "__main__":
    main()
