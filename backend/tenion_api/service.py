from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import smtplib

from argon2 import PasswordHasher, Type

from .config import Settings
from .database import RegistrationDatabase
from .integrations import Mailer, MetaPlatformClient, MetaPlatformError


USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


class RegistrationIssue(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int):
        super().__init__(message)
        self.code = code
        self.status = status


class RegistrationService:
    def __init__(
        self,
        settings: Settings,
        database: RegistrationDatabase,
        mp_client: MetaPlatformClient | None = None,
        mailer: Mailer | None = None,
    ):
        self.settings = settings
        self.database = database
        self.mp_client = mp_client or MetaPlatformClient(settings)
        self.mailer = mailer or Mailer(settings)
        self.password_hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )

    def register(self, email: str, username: str, client_ip: str) -> None:
        normalized_email = normalize_email(email)
        normalized_username = normalize_username(username)
        ip_hash = self._digest(client_ip)
        email_hash = self._digest(normalized_email)
        if not self.database.record_attempt_and_check_limit(ip_hash, email_hash):
            raise RegistrationIssue(
                "RATE_LIMITED",
                "Слишком много попыток. Попробуйте ещё раз немного позже.",
                status=429,
            )

        from .database import EmailAlreadyRegistered, UsernameAlreadyRegistered

        try:
            _, retry = self.database.begin_registration(
                normalized_email, normalized_username
            )
        except EmailAlreadyRegistered as error:
            raise RegistrationIssue(
                "EMAIL_ALREADY_REGISTERED",
                "Для этого email доступ уже создан. Откройте MetaPlatform или напишите в поддержку.",
                status=409,
            ) from error
        except UsernameAlreadyRegistered as error:
            raise RegistrationIssue(
                "USERNAME_TAKEN",
                "Этот логин уже занят. Выберите другой.",
                status=409,
            ) from error

        password = generate_password()
        password_hash = self.password_hasher.hash(password)

        try:
            if retry:
                self.mp_client.reset_disabled_user(normalized_username, password_hash)
            else:
                self.mp_client.create_user(normalized_username, password_hash)
        except MetaPlatformError as error:
            if not retry:
                self.database.discard_unsent(normalized_email)
            else:
                self.database.set_status(
                    normalized_email,
                    "mail_failed",
                    f"mp:{error.code or error.status or 'error'}",
                )
            if error.code == "USER_ALREADY_EXISTS":
                raise RegistrationIssue(
                    "USERNAME_TAKEN", "Этот логин уже занят. Выберите другой.", status=409
                ) from error
            raise RegistrationIssue(
                "SERVICE_UNAVAILABLE",
                "Не удалось создать доступ. Попробуйте ещё раз немного позже.",
                status=503,
            ) from error

        try:
            self.mailer.send_access(normalized_email, normalized_username, password)
        except (OSError, smtplib.SMTPException) as error:
            self.database.set_status(normalized_email, "mail_failed", "smtp:error")
            raise RegistrationIssue(
                "MAIL_UNAVAILABLE",
                "Не удалось отправить письмо. Попробуйте ещё раз немного позже.",
                status=503,
            ) from error

        try:
            self.mp_client.enable_user(normalized_username)
        except MetaPlatformError as error:
            self.database.set_status(
                normalized_email, "enable_failed", f"mp:{error.code or error.status or 'error'}"
            )
            raise RegistrationIssue(
                "SERVICE_UNAVAILABLE",
                "Письмо отправлено, но доступ пока не активирован. Мы исправим это как можно скорее.",
                status=503,
            ) from error

        self.database.set_status(normalized_email, "sent")

    def _digest(self, value: str) -> str:
        return hmac.new(
            self.settings.ip_hash_secret.encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise RegistrationIssue(
            "INVALID_USERNAME",
            "Логин: 3–64 символа, строчные латинские буквы, цифры, точка, дефис или подчёркивание.",
            status=422,
        )
    return username


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise RegistrationIssue(
            "INVALID_EMAIL", "Проверьте адрес электронной почты.", status=422
        )
    local, domain = email.rsplit("@", 1)
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise RegistrationIssue(
            "INVALID_EMAIL", "Проверьте адрес электронной почты.", status=422
        ) from error
    return f"{local}@{domain}"


def generate_password(length: int = 12) -> str:
    while True:
        password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(character.islower() for character in password)
            and any(character.isupper() for character in password)
            and any(character.isdigit() for character in password)
        ):
            return password
