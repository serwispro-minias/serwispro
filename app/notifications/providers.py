from __future__ import annotations

import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(slots=True)
class ProviderResult:
    ok: bool
    provider_name: str
    server_response: str | None = None
    error_message: str | None = None


class EmailProvider(ABC):
    @abstractmethod
    def send(self, *, recipient: str, subject: str | None, content: str, config: dict[str, str]) -> ProviderResult:
        raise NotImplementedError


class SmsProvider(ABC):
    @abstractmethod
    def send(self, *, recipient: str, content: str, config: dict[str, str]) -> ProviderResult:
        raise NotImplementedError


class SmtpEmailProvider(EmailProvider):
    """Generic SMTP provider independent from specific operators."""

    def send(self, *, recipient: str, subject: str | None, content: str, config: dict[str, str]) -> ProviderResult:
        host = (config.get("smtp_host") or "").strip()
        port = int((config.get("smtp_port") or "0").strip() or 0)
        login = (config.get("smtp_login") or "").strip()
        password = config.get("smtp_password") or ""
        default_sender = (config.get("default_sender_email") or "").strip()
        use_tls = str(config.get("smtp_use_tls") or "0") == "1"
        use_ssl = str(config.get("smtp_use_ssl") or "0") == "1"

        if not host or port <= 0:
            return ProviderResult(ok=False, provider_name="smtp", error_message="Brak konfiguracji SMTP host/port.")
        if not default_sender:
            return ProviderResult(ok=False, provider_name="smtp", error_message="Brak domyślnego adresu nadawcy.")

        message = EmailMessage()
        message["From"] = default_sender
        message["To"] = recipient
        message["Subject"] = subject or "Powiadomienie SerwisPRO"
        message.set_content(content)

        try:
            if use_ssl:
                with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                    if login:
                        server.login(login, password)
                    response = server.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    if use_tls:
                        server.starttls()
                    if login:
                        server.login(login, password)
                    response = server.send_message(message)
            return ProviderResult(ok=True, provider_name="smtp", server_response=str(response))
        except Exception as exc:  # pragma: no cover - network integration
            return ProviderResult(ok=False, provider_name="smtp", error_message=str(exc))


class GenericApiSmsProvider(SmsProvider):
    """Provider placeholder based on generic API configuration.

    Intentionally decoupled from any specific vendor; concrete providers can subclass this interface.
    """

    def send(self, *, recipient: str, content: str, config: dict[str, str]) -> ProviderResult:
        api_url = (config.get("sms_api_url") or "").strip()
        api_token = (config.get("sms_api_token") or "").strip()
        provider_name = (config.get("sms_provider_name") or "generic_api").strip() or "generic_api"

        if not api_url or not api_token:
            return ProviderResult(
                ok=False,
                provider_name=provider_name,
                error_message="Brak konfiguracji SMS API URL/TOKEN.",
            )

        # Generic placeholder behavior: do not bind to a vendor protocol yet.
        # A future adapter should implement actual HTTP transport and response mapping.
        return ProviderResult(
            ok=False,
            provider_name=provider_name,
            error_message="Wysyłka SMS nie jest jeszcze skonfigurowana dla wybranego dostawcy.",
        )


class ProviderFactory:
    def __init__(self, email_provider: EmailProvider | None = None, sms_provider: SmsProvider | None = None) -> None:
        self._email_provider = email_provider or SmtpEmailProvider()
        self._sms_provider = sms_provider or GenericApiSmsProvider()

    def email_provider(self) -> EmailProvider:
        return self._email_provider

    def sms_provider(self) -> SmsProvider:
        return self._sms_provider
