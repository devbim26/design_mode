"""Run preset checks against an isolated database during image builds."""
import json
from contextlib import closing
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import setup_style_presets as presets


def check(include_artifacts: bool = True) -> None:
    original_db = presets.DB
    try:
        with tempfile.TemporaryDirectory(prefix="devbim_presets_") as directory:
            presets.DB = Path(directory) / "invokeai.db"
            custom_data = {"positive_prompt": "user prompt", "negative_prompt": ""}
            with closing(sqlite3.connect(presets.DB)) as connection, connection:
                connection.execute(
                    "CREATE TABLE style_presets (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                    "preset_data TEXT NOT NULL, type TEXT NOT NULL)"
                )
                connection.executemany(
                    "INSERT INTO style_presets VALUES (?, ?, ?, ?)",
                    [
                        ("stock", "Photography", "{}", "default"),
                        ("custom", "Custom user preset", json.dumps(custom_data), "user"),
                    ],
                )
            # Exercise replacement and a second sync, preserving custom presets.
            presets.sync_db(presets.DB, presets.PRESETS)
            presets.sync_db(presets.DB, presets.PRESETS)
            with closing(sqlite3.connect(presets.DB)) as connection:
                rows = connection.execute(
                    "SELECT name, preset_data FROM style_presets WHERE type = 'default'"
                ).fetchall()
                assert {name: json.loads(data) for name, data in rows} == {
                    item["name"]: item["preset_data"] for item in presets.PRESETS
                }
                custom = connection.execute(
                    "SELECT name, preset_data, type FROM style_presets WHERE id = 'custom'"
                ).fetchone()
                assert custom == ("Custom user preset", json.dumps(custom_data), "user")
            if include_artifacts:
                # The existing test imports this same module, so it sees the
                # temporary DB while retaining checks of real installed assets.
                runpy.run_path(str(ROOT / "tests" / "test_style_presets.py"), run_name="__main__")
    finally:
        presets.DB = original_db
    print("Isolated style preset database checks OK")


if __name__ == "__main__":
    check(include_artifacts="--database-only" not in sys.argv)
