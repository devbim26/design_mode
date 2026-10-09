"""Offline tests for Windows/Linux paths and persistent container startup."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from package_layout import site_packages

spec = importlib.util.spec_from_file_location("container_entrypoint", ROOT / "deploy" / "entrypoint.py")
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class PackageLayoutTests(unittest.TestCase):
    def test_windows_and_linux_environments(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            windows = base / "windows" / "Lib" / "site-packages"
            linux = base / "linux" / "lib" / "python3.11" / "site-packages"
            windows.mkdir(parents=True)
            linux.mkdir(parents=True)
            self.assertEqual(site_packages(base / "windows"), windows)
            self.assertEqual(site_packages(base / "linux"), linux)

    def test_active_environment_uses_sysconfig(self):
        with tempfile.TemporaryDirectory() as directory:
            venv = Path(directory)
            with patch("package_layout.sys.prefix", str(venv)), patch(
                "package_layout.sysconfig.get_path", return_value=str(venv / "actual-packages")
            ):
                self.assertEqual(site_packages(venv), venv / "actual-packages")

    def test_ambiguous_linux_environment_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            venv = Path(directory)
            for version in ("3.11", "3.12"):
                (venv / "lib" / f"python{version}" / "site-packages").mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                site_packages(venv)

    def test_threed_deploy_supports_both_layouts_and_is_idempotent(self):
        import setup_threed
        with tempfile.TemporaryDirectory() as directory:
            for name, layout in (("windows", Path("Lib/site-packages")),
                                 ("linux", Path("lib/python3.11/site-packages"))):
                venv = Path(directory) / name
                routers = venv / layout / "invokeai/app/api/routers"
                routers.mkdir(parents=True)
                (routers / "imagerouter.py").write_text("# installed", encoding="utf-8")
                self.assertTrue(setup_threed.deploy_files(venv))
                self.assertTrue((routers / "threed_build.py").is_file())
                self.assertFalse(setup_threed.deploy_files(venv))


class ContainerStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "data"
        self.saved_cwd = Path.cwd()
        os.chdir(self.temporary.name)
        self.environment = patch.dict(os.environ, {
            "INVOKEAI_ROOT": str(self.root),
            "STUDIO_AUTH_MODE": "users",
            "SITE_PASSWORD": "owner-password",
            "STUDIO_SESSION_SECRET": "s" * 64,
            "XDG_CACHE_HOME": str(self.root / "cache"),
        }, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        os.chdir(self.saved_cwd)
        self.temporary.cleanup()

    def test_first_start_and_restart_preserve_data_and_config(self):
        entrypoint.prepare()
        config_path = self.root / "invokeai.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["host"], "0.0.0.0")
        self.assertEqual(config["port"], 9090)
        self.assertEqual(config["device"], "cpu")
        config["allow_origins"] = ["https://example.com"]
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        db = self.root / "data" / "studio.sqlite"
        db.parent.mkdir()
        db.write_bytes(b"existing persistent data")
        before = config_path.read_bytes()
        entrypoint.prepare()
        self.assertEqual(config_path.read_bytes(), before)
        self.assertEqual(db.read_bytes(), b"existing persistent data")
        self.assertTrue((self.root / "cache").is_dir())
        self.assertNotIn("STUDIO_SESSION_SECRET", config_path.read_text(encoding="utf-8"))

    def test_migrated_config_preserves_settings_and_normalizes_binding(self):
        self.root.mkdir()
        config_path = self.root / "invokeai.yaml"
        config_path.write_text(
            "schema_version: 4.0.2\nhost: 127.0.0.1\nport: 9100\n"
            "allow_origins: [https://example.com]\ndevice: cuda\nprecision: float16\n",
            encoding="utf-8",
        )
        entrypoint.prepare()
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["allow_origins"], ["https://example.com"])
        self.assertEqual((config["host"], config["port"], config["device"]), ("0.0.0.0", 9090, "cpu"))

    def test_unsafe_configuration_is_rejected_before_creating_config(self):
        for updates in (
            {"STUDIO_AUTH_MODE": "unknown"},
            {"SITE_PASSWORD": ""},
            {"STUDIO_SESSION_SECRET": "short"},
            {"STUDIO_AUTH_MODE": "sso", "STUDIO_JWT_SECRET": ""},
            {"STUDIO_AUTH_MODE": "password", "ADMIN_PASSWORD": ""},
        ):
            with self.subTest(updates=updates), patch.dict(os.environ, updates):
                with self.assertRaises(ValueError):
                    entrypoint.prepare()
                self.assertFalse((self.root / "invokeai.yaml").exists())

    def test_conflicting_env_file_is_not_silently_used(self):
        self.root.mkdir()
        (self.root / ".env").write_text("SITE_PASSWORD=old-password\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            entrypoint.prepare()


if __name__ == "__main__":
    unittest.main()
