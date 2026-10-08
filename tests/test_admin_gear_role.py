# -*- coding: utf-8 -*-
"""Тесты роль-гейта шестерёнки «Настройки» / «Model Manager» (devbim_admin.js):
админ — без пароля, пользователь — пункты скрыты, password-режим — прежний пароль.

Запуск: venv\\Scripts\\python.exe tests\\test_admin_gear_role.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
JS = BASE / "imagerouter" / "devbim_admin.js"


def test_js_syntax():
    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    r = subprocess.run([node, "--check", str(JS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    print("OK: node --check devbim_admin.js")


def test_role_gate_users_mode():
    s = JS.read_text(encoding="utf-8")
    # роль учитывается в режимах users И sso (раньше — только sso)
    assert "d.mode === 'users'" in s and "d.mode === 'sso'" in s, s[:200]
    assert "applyRole" in s and "warmRole" in s, s
    print("OK: роль из /api/v1/studio/me читается в режимах users и sso")


def test_admin_no_password():
    s = JS.read_text(encoding="utf-8")
    frag = s[s.find("function applyRole"):s.find("function warmRole")]
    assert "'admin'" in frag and "unlocked = true" in frag, frag
    assert "window.__devbimUnlocked = true" in frag, frag
    print("OK: админ разблокирован ролью сессии, без пароля")


def test_user_items_hidden():
    s = JS.read_text(encoding="utf-8")
    # пункты меню «Настройки» и «Model Manager» скрыты у role=user
    assert "hideAdminMenuItems" in s, s
    assert "HIDDEN_ITEMS = ['Model Manager']" in s, s
    assert 'data-devbim-admin-hidden' in s, s
    assert "MutationObserver" in s, s  # меню ленивое — прячем при каждом открытии
    # обёртка с одним пунктом тоже прячется (шестерёнка обёрнута в YTe)
    assert "querySelectorAll('[role=\"menuitem\"]').length === 1" in s, s
    # страховка от обходных путей — НЕ блокирующий alert (гейт может сработать
    # в фоне при загрузке — alert замораживал приложение), а всплывающее уведомление
    assert "notifyBlocked" in s and "devbim-admin-notice" in s, s
    assert "alert('" not in s, "блокирующий alert запрещён в гейте"
    print("OK: у пользователя пункты скрыты, обходной клик — алерт")


def test_password_mode_fallback():
    s = JS.read_text(encoding="utf-8")
    # password-режим (роль неизвестна) — прежний пароль ADMIN_PASSWORD
    assert "/api/v1/imagerouter/admin-auth" in s, s
    assert "askPassword" in s and "verifyPassword" in s, s
    # список локалей для перехвата клика по шестерёнке не потерян
    assert "'Настройки'" in s and "'Settings'" in s, s
    print("OK: password-режим — прежний гейт по паролю")


def main():
    test_js_syntax()
    test_role_gate_users_mode()
    test_admin_no_password()
    test_user_items_hidden()
    test_password_mode_fallback()
    print("Все проверки пройдены.")


if __name__ == "__main__":
    main()
