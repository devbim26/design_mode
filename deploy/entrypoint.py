"""Initialize persistent configuration, then replace this process with InvokeAI."""
import os
from pathlib import Path
import sys

import yaml


def prepare() -> None:
    root = Path(os.environ.get("INVOKEAI_ROOT", "/data"))
    root.mkdir(parents=True, exist_ok=True)
    # Application modules give these files precedence over environment values.
    # Compose is the configuration source for this deployment.
    for candidate in (root / ".env", root.parent / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            raise ValueError(f"Unexpected {candidate}: use deploy/.env through Compose env_file")
    mode = os.environ.get("STUDIO_AUTH_MODE", "users").strip().lower()
    if mode not in {"users", "password", "sso"}:
        raise ValueError("STUDIO_AUTH_MODE must be users, password, or sso")
    if not os.environ.get("SITE_PASSWORD", "").strip():
        raise ValueError("SITE_PASSWORD is required")
    secret = os.environ.get("STUDIO_SESSION_SECRET", "").strip()
    if len(secret) < 32:
        raise ValueError("STUDIO_SESSION_SECRET must contain at least 32 characters")
    if mode == "sso" and len(os.environ.get("STUDIO_JWT_SECRET", "").strip()) < 32:
        raise ValueError("SSO requires STUDIO_JWT_SECRET with at least 32 characters")
    if mode == "password" and not os.environ.get("ADMIN_PASSWORD", "").strip():
        raise ValueError("password mode requires ADMIN_PASSWORD for model management")

    config_path = root / "invokeai.yaml"
    source = config_path if config_path.is_file() else Path(__file__).with_name("invokeai.yaml")
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Expected a YAML mapping in {source}")
    updated = dict(config)
    # Normalize migrated Windows configurations for the container, preserving
    # all other settings. Compose controls these four deployment-specific values.
    updated.update(
        host=os.environ.get("INVOKEAI_HOST", "0.0.0.0"),
        port=int(os.environ.get("INVOKEAI_PORT", "9090")),
        device=os.environ.get("INVOKEAI_DEVICE", "cpu"),
        precision=os.environ.get("INVOKEAI_PRECISION", "float32"),
    )
    if not config_path.is_file() or updated != config:
        config_path.write_text(yaml.safe_dump(updated, sort_keys=False), encoding="utf-8")
        print(f"Initialized container configuration: {config_path}", flush=True)
    for cache in ("HF_HOME", "MPLCONFIGDIR", "XDG_CACHE_HOME"):
        if os.environ.get(cache):
            Path(os.environ[cache]).mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    try:
        prepare()
        command = sys.argv[1:]
        if not command:
            raise ValueError("Missing container command")
    except (OSError, ValueError, yaml.YAMLError) as error:
        sys.exit(f"Container startup failed: {error}")
    os.execvp(command[0], command)
