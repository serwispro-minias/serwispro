from __future__ import annotations

CHANNEL_EMAIL = "EMAIL"
CHANNEL_SMS = "SMS"

CHANNEL_CHOICES: list[tuple[str, str]] = [
    (CHANNEL_EMAIL, "E-mail"),
    (CHANNEL_SMS, "SMS"),
]

NOTIFICATION_STATUS_SENT = "SENT"
NOTIFICATION_STATUS_ERROR = "ERROR"
NOTIFICATION_STATUS_CANCELLED = "CANCELLED"

NOTIFICATION_STATUS_CHOICES: list[tuple[str, str]] = [
    (NOTIFICATION_STATUS_SENT, "Wysłano"),
    (NOTIFICATION_STATUS_ERROR, "Błąd"),
    (NOTIFICATION_STATUS_CANCELLED, "Anulowano"),
]

NOTIFICATION_STATUS_LABELS = dict(NOTIFICATION_STATUS_CHOICES)

EVENT_RECEIVED = "RECEIVED"
EVENT_DIAGNOSIS = "DIAGNOSIS"
EVENT_WAITING_CUSTOMER_DECISION = "WAITING_CUSTOMER_DECISION"
EVENT_PARTS_ORDER = "PARTS_ORDER"
EVENT_REPAIR_FINISHED = "REPAIR_FINISHED"
EVENT_READY_FOR_PICKUP = "READY_FOR_PICKUP"
EVENT_ISSUED = "ISSUED"

NOTIFICATION_EVENT_CHOICES: list[tuple[str, str]] = [
    (EVENT_RECEIVED, "Przyjęcie sprzętu"),
    (EVENT_DIAGNOSIS, "Rozpoczęcie diagnozy"),
    (EVENT_WAITING_CUSTOMER_DECISION, "Oczekiwanie na decyzję klienta"),
    (EVENT_PARTS_ORDER, "Zamówienie części"),
    (EVENT_REPAIR_FINISHED, "Zakończenie naprawy"),
    (EVENT_READY_FOR_PICKUP, "Sprzęt gotowy do odbioru"),
    (EVENT_ISSUED, "Wydanie sprzętu"),
]

NOTIFICATION_EVENT_LABELS = dict(NOTIFICATION_EVENT_CHOICES)

STATUS_TO_EVENT_KEY: dict[str, str] = {
    "RECEIVED": EVENT_RECEIVED,
    "DIAGNOSIS": EVENT_DIAGNOSIS,
    "WAITING_CUSTOMER_DECISION": EVENT_WAITING_CUSTOMER_DECISION,
    "WAITING_PARTS": EVENT_PARTS_ORDER,
    "IN_REPAIR": EVENT_REPAIR_FINISHED,
    "READY_FOR_PICKUP": EVENT_READY_FOR_PICKUP,
    "ISSUED": EVENT_ISSUED,
}

DEFAULT_TEMPLATE_VARIABLES: tuple[str, ...] = (
    "order_number",
    "customer_name",
    "device_name",
    "status",
    "pickup_amount",
    "company_name",
    "company_phone",
)

NOTIFICATION_CONFIG_KEYS: dict[str, str] = {
    "email_enabled": "notifications.email_enabled",
    "sms_enabled": "notifications.sms_enabled",
    "default_sender_email": "notifications.default_sender_email",
    "smtp_host": "notifications.smtp.host",
    "smtp_port": "notifications.smtp.port",
    "smtp_login": "notifications.smtp.login",
    "smtp_password": "notifications.smtp.password",
    "smtp_use_tls": "notifications.smtp.use_tls",
    "smtp_use_ssl": "notifications.smtp.use_ssl",
    "sms_provider_name": "notifications.sms.provider_name",
    "sms_api_url": "notifications.sms.api_url",
    "sms_api_token": "notifications.sms.api_token",
    "sms_sender": "notifications.sms.sender",
}
