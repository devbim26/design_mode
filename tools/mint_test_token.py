# -*- coding: utf-8 -*-
"""Утилита локальной проверки SSO: минт тестового JWT как у devbim.com.

Запуск (из корня, venv-питоном):
  venv\\Scripts\\python.exe tools\\mint_test_token.py --email a@b.io --role admin
Секрет: STUDIO_JWT_SECRET из .env (или --secret). Печатает токен и готовый URL.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import jwt  # PyJWT из venv

import studio_store


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sub", default="test-user")
    p.add_argument("--email", default="test@example.com")
    p.add_argument("--name", default="Test User")
    p.add_argument("--role", default="user", choices=["user", "admin"])
    p.add_argument("--ttl", type=int, default=300)
    p.add_argument("--secret", default=None)
    p.add_argument("--base", default="http://127.0.0.1:9090")
    a = p.parse_args()

    secret = a.secret or studio_store.env_or("STUDIO_JWT_SECRET")
    if not secret:
        sys.exit("Нет STUDIO_JWT_SECRET (в .env или --secret)")
    now = int(time.time())
    claims = {"sub": a.sub, "email": a.email, "name": a.name, "role": a.role,
              "iat": now, "exp": now + a.ttl, "jti": str(uuid.uuid4())}
    token = jwt.encode(claims, secret, algorithm="HS256")
    print(token)
    print(f"{a.base}/auth/sso?t={token}")


if __name__ == "__main__":
    main()
