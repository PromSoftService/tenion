from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import secrets

from .config import Settings
from .database import RegistrationDatabase, timestamp, utc_now
from .integrations import MetaPlatformClient, MetaPlatformError
from .service import RegistrationIssue, normalize_username


ADMIN_COOKIE_NAME = "tenion_admin_session"


class AdminService:
    def __init__(
        self,
        settings: Settings,
        database: RegistrationDatabase,
        mp_client: MetaPlatformClient | None = None,
    ):
        self.settings = settings
        self.database = database
        self.mp_client = mp_client or MetaPlatformClient(settings)

    def login(self, password: str, client_ip: str) -> tuple[str, str]:
        ip_hash = self._digest(client_ip)
        if not self.database.admin_login_allowed(ip_hash):
            raise RegistrationIssue(
                "ADMIN_RATE_LIMITED",
                "Слишком много попыток входа. Попробуйте ещё раз через 15 минут.",
                status=429,
            )
        if not hmac.compare_digest(str(password), self.settings.mp_admin_password):
            self.database.record_admin_login_failure(ip_hash)
            raise RegistrationIssue(
                "INVALID_ADMIN_CREDENTIALS",
                "Неверный пароль.",
                status=401,
            )

        self.database.clear_admin_login_failures(ip_hash)
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        expires_at = timestamp(
            utc_now() + timedelta(seconds=self.settings.admin_session_ttl_seconds)
        )
        self.database.create_admin_session(
            self._digest(token), csrf_token, expires_at
        )
        return token, csrf_token

    def authenticate(self, token: str | None) -> str:
        if not token:
            raise self._unauthorized()
        session = self.database.get_admin_session(self._digest(token))
        if session is None:
            raise self._unauthorized()
        return session.csrf_token

    def logout(self, token: str | None) -> None:
        if token:
            self.database.delete_admin_session(self._digest(token))

    def require_csrf(self, expected: str, supplied: str | None) -> None:
        if not supplied or not hmac.compare_digest(expected, supplied):
            raise RegistrationIssue(
                "INVALID_CSRF_TOKEN", "Запрос отклонён.", status=403
            )

    def list_users(self) -> list[dict[str, object]]:
        try:
            users = self.mp_client.list_users()
        except MetaPlatformError as error:
            raise self._mp_issue(error) from error

        emails = self.database.registration_emails_by_username()
        result: list[dict[str, object]] = []
        for item in users:
            username = item.get("username")
            if not isinstance(username, str):
                raise RegistrationIssue(
                    "INVALID_METAPLATFORM_RESPONSE",
                    "MetaPlatform вернула некорректный список пользователей.",
                    status=503,
                )
            result.append(
                {
                    "username": username,
                    "email": emails.get(username),
                    "active": item.get("active") is True,
                    "passwordChangedAt": self._optional_string(
                        item.get("passwordChangedAt")
                    ),
                    "lastLoginAt": self._optional_string(item.get("lastLoginAt")),
                    "createdAt": self._optional_string(item.get("createdAt")),
                    "updatedAt": self._optional_string(item.get("updatedAt")),
                }
            )
        return sorted(result, key=lambda item: str(item["username"]))

    def delete_user(self, username: str) -> dict[str, object]:
        normalized_username = normalize_username(username)
        try:
            result = self.mp_client.delete_user(normalized_username)
        except MetaPlatformError as error:
            raise self._mp_issue(error) from error
        registration_deleted = self.database.delete_registration_by_username(
            normalized_username
        )
        return {**result, "registrationDeleted": registration_deleted}

    def _digest(self, value: str) -> str:
        return hmac.new(
            self.settings.ip_hash_secret.encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _unauthorized() -> RegistrationIssue:
        return RegistrationIssue(
            "ADMIN_AUTH_REQUIRED", "Требуется вход в админку.", status=401
        )

    @staticmethod
    def _mp_issue(error: MetaPlatformError) -> RegistrationIssue:
        if error.code == "USER_NOT_FOUND":
            return RegistrationIssue(
                "USER_NOT_FOUND", "Пользователь не найден.", status=404
            )
        if error.code == "LEGACY_USER_PROTECTED":
            return RegistrationIssue(
                "LEGACY_USER_PROTECTED",
                "Системного пользователя удалить нельзя.",
                status=409,
            )
        if error.code == "USER_DELETION_BLOCKED":
            return RegistrationIssue(
                "USER_DELETION_BLOCKED",
                "MetaPlatform не смогла безопасно остановить процессы пользователя. Пользователь оставлен заблокированным.",
                status=409,
            )
        return RegistrationIssue(
            "METAPLATFORM_UNAVAILABLE",
            "MetaPlatform временно недоступна. Попробуйте ещё раз.",
            status=503,
        )
