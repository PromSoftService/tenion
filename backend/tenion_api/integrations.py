from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr
import html
import json
import smtplib
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings


class MetaPlatformError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class MetaPlatformClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.mp_admin_base_url
        self.password = settings.mp_admin_password

    def create_user(self, username: str, password_hash: str) -> None:
        self._request(
            "POST",
            "/users",
            {"username": username, "passwordHash": password_hash, "active": False},
            expected_status=201,
        )

    def reset_disabled_user(self, username: str, password_hash: str) -> None:
        self._request(
            "POST",
            f"/users/{username}/disable",
            None,
            expected_status=200,
        )
        self._request(
            "POST",
            f"/users/{username}/set-password",
            {"passwordHash": password_hash},
            expected_status=200,
        )

    def enable_user(self, username: str) -> None:
        self._request(
            "POST",
            f"/users/{username}/enable",
            None,
            expected_status=200,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None,
        *,
        expected_status: int,
    ) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.password}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=10) as response:
                if response.status != expected_status:
                    raise MetaPlatformError(
                        "Unexpected MetaPlatform response", status=response.status
                    )
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as error:
            code = None
            message = "MetaPlatform rejected the request"
            try:
                response_payload = json.loads(error.read())
                detail = response_payload.get("detail", {})
                code = detail.get("code")
                message = detail.get("message", message)
            except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
                pass
            raise MetaPlatformError(message, status=error.code, code=code) from error
        except URLError as error:
            raise MetaPlatformError("MetaPlatform is unavailable") from error


class Mailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send_access(self, email: str, username: str, password: str) -> None:
        message = EmailMessage()
        message["Subject"] = "Доступ к MetaPlatform готов"
        message["From"] = formataddr(
            (self.settings.mail_from_name, self.settings.mail_from_address)
        )
        message["To"] = email
        message["Reply-To"] = self.settings.mail_reply_to
        message.set_content(self._plain_text(username, password))
        message.add_alternative(self._html_text(username, password), subtype="html")

        self._send(message)

    def send_contact(self, name: str, email: str, text: str, topic: str) -> None:
        topic_label = {
            "team": "Применение MetaPlatform",
            "pilot": "Пилот MetaPlatform",
        }[topic]
        message = EmailMessage()
        message["Subject"] = f"[Tenion] {topic_label}: {name}"
        message["From"] = formataddr(
            (self.settings.mail_from_name, self.settings.mail_from_address)
        )
        message["To"] = self.settings.contact_recipient
        message["Reply-To"] = email
        message.set_content(
            f"""Новая заявка с tenion.cloud

Тема: {topic_label}
Имя: {name}
Email: {email}

Сообщение:
{text}
"""
        )
        self._send(message)

    def _send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.settings.smtp_security == "ssl":
            with smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                context=context,
                timeout=15,
            ) as smtp:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(message)
            return

        with smtplib.SMTP(
            self.settings.smtp_host, self.settings.smtp_port, timeout=15
        ) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)

    @staticmethod
    def _plain_text(username: str, password: str) -> str:
        return f"""Здравствуйте!

Для вас создан доступ к MetaPlatform — системе автоматизированной разработки программного обеспечения АСУ ТП.

Открыть MetaPlatform:
https://app.tenion.cloud

Логин: {username}
Пароль: {password}

Сохраните эти данные и не передавайте их третьим лицам.

MetaPlatform сейчас предоставляется бесплатно в рамках раннего доступа. Если при работе возникнет вопрос или ошибка, просто ответьте на это письмо.

С уважением,
команда Tenion
PromSoftService
"""

    @staticmethod
    def _html_text(username: str, password: str) -> str:
        safe_username = html.escape(username)
        safe_password = html.escape(password)
        return f"""<!doctype html>
<html lang="ru">
<body style="margin:0;background:#f4f5f7;color:#15171b;font-family:Arial,sans-serif">
  <div style="max-width:620px;margin:0 auto;padding:36px 18px">
    <div style="background:#ffffff;border:1px solid #dfe1e6;border-radius:20px;padding:38px">
      <div style="margin-bottom:30px;font-size:15px;font-weight:700;letter-spacing:.12em">TENION <span style="color:#d92b52">/</span> MetaPlatform</div>
      <h1 style="margin:0 0 22px;font-size:30px;line-height:1.15">Доступ к MetaPlatform готов</h1>
      <p style="margin:0 0 24px;color:#666b75;line-height:1.65">Для вас создан доступ к системе автоматизированной разработки программного обеспечения АСУ ТП.</p>
      <div style="margin:0 0 26px;padding:22px;border-radius:14px;background:#f4f5f7">
        <div style="margin-bottom:10px;color:#666b75;font-size:13px">Логин</div>
        <div style="margin-bottom:18px;font-size:18px;font-weight:700">{safe_username}</div>
        <div style="margin-bottom:10px;color:#666b75;font-size:13px">Пароль</div>
        <div style="font-family:Consolas,monospace;font-size:20px;font-weight:700;letter-spacing:.04em">{safe_password}</div>
      </div>
      <a href="https://app.tenion.cloud" style="display:inline-block;padding:16px 22px;border-radius:12px;background:#15171b;color:#ffffff;text-decoration:none;font-weight:700">Открыть MetaPlatform&nbsp; ↗</a>
      <p style="margin:28px 0 0;color:#666b75;font-size:13px;line-height:1.6">Сохраните данные и не передавайте их третьим лицам. MetaPlatform сейчас предоставляется бесплатно в рамках раннего доступа.</p>
      <p style="margin:18px 0 0;color:#666b75;font-size:13px;line-height:1.6">Если при работе возникнет вопрос или ошибка, просто ответьте на это письмо.</p>
      <p style="margin:30px 0 0;font-size:13px;line-height:1.6">С уважением,<br>команда Tenion<br>PromSoftService</p>
    </div>
  </div>
</body>
</html>"""
