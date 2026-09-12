from __future__ import annotations

import base64
import importlib
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

from tenion_api.admin import ADMIN_COOKIE_NAME, AdminService
from tenion_api.config import Settings
from tenion_api.database import RegistrationDatabase
from tenion_api.service import RegistrationIssue


class FakeAdminMetaPlatform:
    def __init__(self):
        self.users = [
            {
                "username": "engineer",
                "active": True,
                "passwordChangedAt": "2026-09-12T08:00:00Z",
                "lastLoginAt": "2026-09-12T09:00:00Z",
                "createdAt": "2026-09-12T07:00:00Z",
                "updatedAt": "2026-09-12T09:00:00Z",
            },
            {
                "username": "cli-user",
                "active": False,
                "passwordChangedAt": None,
                "lastLoginAt": None,
                "createdAt": "2026-09-11T07:00:00Z",
                "updatedAt": "2026-09-11T07:00:00Z",
            },
        ]
        self.deleted: list[str] = []

    def list_users(self) -> list[dict[str, object]]:
        return list(self.users)

    def delete_user(self, username: str) -> dict[str, object]:
        self.deleted.append(username)
        self.users = [user for user in self.users if user["username"] != username]
        return {
            "username": username,
            "deleted": True,
            "projectsDeleted": 2,
            "processRunsDeleted": 3,
            "artifactsDeleted": 1,
        }


@pytest.fixture
def admin_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_root=tmp_path,
        public_origin="https://tenion.cloud",
        mp_admin_base_url="http://127.0.0.1:8000/internal/v1",
        mp_admin_password="admin-secret",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_security="ssl",
        smtp_username="support@tenion.cloud",
        smtp_password="smtp-secret",
        mail_from_address="support@tenion.cloud",
        mail_from_name="MetaPlatform",
        mail_reply_to="support@tenion.cloud",
        ip_hash_secret="ip-hash-secret",
        admin_session_ttl_seconds=3600,
    )


def _database_with_registration(settings: Settings) -> RegistrationDatabase:
    database = RegistrationDatabase(settings.data_root / "tenion.db")
    database.initialize()
    database.begin_registration("engineer@example.com", "engineer")
    database.set_status("engineer@example.com", "sent")
    return database


def test_admin_session_and_login_rate_limit(admin_settings: Settings) -> None:
    database = RegistrationDatabase(admin_settings.data_root / "tenion.db")
    database.initialize()
    service = AdminService(admin_settings, database, FakeAdminMetaPlatform())

    for _ in range(5):
        with pytest.raises(RegistrationIssue) as caught:
            service.login("wrong", "192.0.2.10")
        assert caught.value.code == "INVALID_ADMIN_CREDENTIALS"

    with pytest.raises(RegistrationIssue) as limited:
        service.login("admin-secret", "192.0.2.10")
    assert limited.value.code == "ADMIN_RATE_LIMITED"

    token, csrf = service.login("admin-secret", "192.0.2.11")
    assert service.authenticate(token) == csrf
    service.require_csrf(csrf, csrf)
    service.logout(token)
    with pytest.raises(RegistrationIssue) as unauthorized:
        service.authenticate(token)
    assert unauthorized.value.code == "ADMIN_AUTH_REQUIRED"


def test_admin_list_joins_email_and_delete_cleans_registration(
    admin_settings: Settings,
) -> None:
    database = _database_with_registration(admin_settings)
    mp = FakeAdminMetaPlatform()
    service = AdminService(admin_settings, database, mp)

    users = service.list_users()
    assert users[0]["username"] == "cli-user"
    assert users[0]["email"] is None
    assert users[1]["email"] == "engineer@example.com"

    result = service.delete_user("ENGINEER")
    assert result["deleted"] is True
    assert result["registrationDeleted"] is True
    assert mp.deleted == ["engineer"]
    assert database.registration_emails_by_username() == {}


def test_admin_http_session_csrf_list_and_delete(
    admin_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = {
        "TENION_PUBLIC_ORIGIN": admin_settings.public_origin,
        "TENION_MP_ADMIN_BASE_URL": admin_settings.mp_admin_base_url,
        "TENION_MP_ADMIN_PASSWORD": admin_settings.mp_admin_password,
        "TENION_SMTP_HOST": admin_settings.smtp_host,
        "TENION_SMTP_PORT": str(admin_settings.smtp_port),
        "TENION_SMTP_SECURITY": admin_settings.smtp_security,
        "TENION_SMTP_USERNAME": admin_settings.smtp_username,
        "TENION_SMTP_PASSWORD_B64": base64.b64encode(
            admin_settings.smtp_password.encode()
        ).decode(),
        "TENION_MAIL_FROM_ADDRESS": admin_settings.mail_from_address,
        "TENION_MAIL_REPLY_TO": admin_settings.mail_reply_to,
        "TENION_IP_HASH_SECRET": admin_settings.ip_hash_secret,
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    sys.modules.pop("tenion_api.app", None)
    app_module = importlib.import_module("tenion_api.app")
    database = _database_with_registration(admin_settings)
    mp = FakeAdminMetaPlatform()
    monkeypatch.setattr(app_module, "settings", admin_settings)
    monkeypatch.setattr(app_module, "database", database)
    monkeypatch.setattr(
        app_module,
        "admin_service",
        AdminService(admin_settings, database, mp),
    )

    with TestClient(app_module.app, base_url="https://tenion.cloud") as client:
        assert client.get("/api/admin/users").status_code == 401
        invalid_origin = client.post(
            "/api/admin/session",
            headers={"Origin": "https://example.invalid"},
            json={"password": "admin-secret"},
        )
        assert invalid_origin.status_code == 403
        login = client.post(
            "/api/admin/session",
            headers={"Origin": "https://tenion.cloud"},
            json={"password": "admin-secret"},
        )
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "Secure" in login.headers["set-cookie"]
        assert "SameSite=strict" in login.headers["set-cookie"]
        csrf = login.json()["csrfToken"]

        listed = client.get("/api/admin/users")
        assert listed.status_code == 200
        assert listed.json()["users"][1]["email"] == "engineer@example.com"

        without_csrf = client.delete(
            "/api/admin/users/engineer",
            headers={"Origin": "https://tenion.cloud"},
        )
        assert without_csrf.status_code == 403
        deleted = client.delete(
            "/api/admin/users/engineer",
            headers={
                "Origin": "https://tenion.cloud",
                "X-Tenion-Admin-CSRF": csrf,
            },
        )
        assert deleted.status_code == 200
        assert deleted.json()["result"]["registrationDeleted"] is True
        assert mp.deleted == ["engineer"]

        logout = client.delete(
            "/api/admin/session",
            headers={
                "Origin": "https://tenion.cloud",
                "X-Tenion-Admin-CSRF": csrf,
            },
        )
        assert logout.status_code == 200
        assert ADMIN_COOKIE_NAME not in client.cookies
