from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required")
    return value


def _smtp_password() -> str:
    encoded = _required("TENION_SMTP_PASSWORD_B64")
    try:
        value = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ConfigurationError("TENION_SMTP_PASSWORD_B64 is invalid") from error
    if not value:
        raise ConfigurationError("TENION_SMTP_PASSWORD_B64 is empty")
    return value


@dataclass(frozen=True)
class Settings:
    data_root: Path
    public_origin: str
    mp_admin_base_url: str
    mp_admin_password: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    smtp_password: str
    mail_from_address: str
    mail_from_name: str
    mail_reply_to: str
    ip_hash_secret: str

    @classmethod
    def from_environment(cls) -> "Settings":
        public_origin = _required("TENION_PUBLIC_ORIGIN").rstrip("/")
        parsed_origin = urlparse(public_origin)
        if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.netloc:
            raise ConfigurationError("TENION_PUBLIC_ORIGIN must be an absolute HTTP(S) origin")

        try:
            smtp_port = int(_required("TENION_SMTP_PORT"))
        except ValueError as error:
            raise ConfigurationError("TENION_SMTP_PORT must be an integer") from error
        if not 1 <= smtp_port <= 65535:
            raise ConfigurationError("TENION_SMTP_PORT is outside the valid range")

        smtp_security = os.environ.get("TENION_SMTP_SECURITY", "ssl").strip().lower()
        if smtp_security not in {"ssl", "starttls"}:
            raise ConfigurationError("TENION_SMTP_SECURITY must be ssl or starttls")

        return cls(
            data_root=Path(os.environ.get("TENION_DATA_ROOT", "/srv/tenion/data")).resolve(),
            public_origin=public_origin,
            mp_admin_base_url=_required("TENION_MP_ADMIN_BASE_URL").rstrip("/"),
            mp_admin_password=_required("TENION_MP_ADMIN_PASSWORD"),
            smtp_host=_required("TENION_SMTP_HOST"),
            smtp_port=smtp_port,
            smtp_security=smtp_security,
            smtp_username=_required("TENION_SMTP_USERNAME"),
            smtp_password=_smtp_password(),
            mail_from_address=_required("TENION_MAIL_FROM_ADDRESS"),
            mail_from_name=os.environ.get("TENION_MAIL_FROM_NAME", "MetaPlatform").strip() or "MetaPlatform",
            mail_reply_to=_required("TENION_MAIL_REPLY_TO"),
            ip_hash_secret=_required("TENION_IP_HASH_SECRET"),
        )
