from __future__ import annotations

from pathlib import Path
import smtplib

import pytest
from argon2 import extract_parameters, Type

from tenion_api.config import Settings
from tenion_api.database import RegistrationDatabase
from tenion_api.service import (
    RegistrationIssue,
    RegistrationService,
    generate_password,
    normalize_email,
    normalize_username,
)


class FakeMetaPlatform:
    def __init__(self):
        self.actions: list[tuple[str, str]] = []

    def create_user(self, username: str, password_hash: str) -> None:
        assert password_hash.startswith("$argon2id$")
        self.actions.append(("create", username))

    def reset_disabled_user(self, username: str, password_hash: str) -> None:
        assert password_hash.startswith("$argon2id$")
        self.actions.append(("reset", username))

    def enable_user(self, username: str) -> None:
        self.actions.append(("enable", username))


class FakeMailer:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send_access(self, email: str, username: str, password: str) -> None:
        self.sent.append((email, username, password))


class FailingMailer(FakeMailer):
    def send_access(self, email: str, username: str, password: str) -> None:
        raise smtplib.SMTPException("delivery failed")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
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
    )


def test_registration_creates_disabled_user_sends_mail_and_enables(
    settings: Settings,
) -> None:
    database = RegistrationDatabase(settings.data_root / "tenion.db")
    database.initialize()
    mp = FakeMetaPlatform()
    mailer = FakeMailer()
    service = RegistrationService(settings, database, mp, mailer)

    service.register("Engineer@Example.com", "engineer-1", "192.0.2.10")

    assert mp.actions == [("create", "engineer-1"), ("enable", "engineer-1")]
    assert mailer.sent[0][0:2] == ("engineer@example.com", "engineer-1")
    assert len(mailer.sent[0][2]) == 12


def test_duplicate_email_is_rejected(settings: Settings) -> None:
    database = RegistrationDatabase(settings.data_root / "tenion.db")
    database.initialize()
    service = RegistrationService(settings, database, FakeMetaPlatform(), FakeMailer())
    service.register("engineer@example.com", "engineer", "192.0.2.10")

    with pytest.raises(RegistrationIssue) as caught:
        service.register("engineer@example.com", "engineer", "192.0.2.11")

    assert caught.value.code == "EMAIL_ALREADY_REGISTERED"


def test_failed_mail_can_be_retried_with_a_new_password(settings: Settings) -> None:
    database = RegistrationDatabase(settings.data_root / "tenion.db")
    database.initialize()
    mp = FakeMetaPlatform()
    failing = RegistrationService(settings, database, mp, FailingMailer())

    with pytest.raises(RegistrationIssue) as caught:
        failing.register("engineer@example.com", "engineer", "192.0.2.10")
    assert caught.value.code == "MAIL_UNAVAILABLE"

    mailer = FakeMailer()
    retry = RegistrationService(settings, database, mp, mailer)
    retry.register("engineer@example.com", "engineer", "192.0.2.10")

    assert mp.actions == [
        ("create", "engineer"),
        ("reset", "engineer"),
        ("enable", "engineer"),
    ]
    assert len(mailer.sent) == 1


@pytest.mark.parametrize("username", ["ab", "ivan space", "_ivan"])
def test_invalid_usernames(username: str) -> None:
    with pytest.raises(RegistrationIssue):
        normalize_username(username)


def test_username_is_normalized_to_lowercase() -> None:
    assert normalize_username("Ivan.Petrov") == "ivan.petrov"


@pytest.mark.parametrize("email", ["invalid", "a@b", "a b@example.com"])
def test_invalid_emails(email: str) -> None:
    with pytest.raises(RegistrationIssue):
        normalize_email(email)


def test_password_matches_metaplatform_policy() -> None:
    for _ in range(100):
        password = generate_password()
        assert len(password) == 12
        assert any(character.islower() for character in password)
        assert any(character.isupper() for character in password)
        assert any(character.isdigit() for character in password)


def test_hash_matches_metaplatform_argon2_policy(settings: Settings) -> None:
    database = RegistrationDatabase(settings.data_root / "tenion.db")
    service = RegistrationService(settings, database, FakeMetaPlatform(), FakeMailer())
    parameters = extract_parameters(service.password_hasher.hash("ValidPassword2"))

    assert parameters.type is Type.ID
    assert parameters.time_cost == 3
    assert parameters.memory_cost == 65536
    assert parameters.parallelism == 4
    assert parameters.hash_len == 32
    assert parameters.salt_len == 16
