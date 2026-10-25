from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    HiddenField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, Regexp

from app.notifications.constants import CHANNEL_CHOICES, NOTIFICATION_EVENT_CHOICES


class NotificationConfigForm(FlaskForm):
    email_enabled = BooleanField("Włącz e-mail")
    sms_enabled = BooleanField("Włącz SMS")

    smtp_host = StringField("SMTP host", validators=[Optional(), Length(max=255)])
    smtp_port = StringField("SMTP port", validators=[Optional(), Length(max=10)])
    smtp_login = StringField("SMTP login", validators=[Optional(), Length(max=255)])
    smtp_password = StringField("SMTP hasło", validators=[Optional(), Length(max=255)])
    smtp_use_tls = BooleanField("SMTP TLS")
    smtp_use_ssl = BooleanField("SMTP SSL")
    default_sender_email = StringField("Domyślny adres nadawcy", validators=[Optional(), Email(), Length(max=255)])

    sms_provider_name = StringField("Nazwa dostawcy SMS", validators=[Optional(), Length(max=120)])
    sms_api_url = StringField("SMS API URL", validators=[Optional(), Length(max=500)])
    sms_api_token = StringField("SMS API token", validators=[Optional(), Length(max=500)])
    sms_sender = StringField("Nadawca SMS", validators=[Optional(), Length(max=60)])

    submit = SubmitField("Zapisz konfigurację")


class NotificationTemplateForm(FlaskForm):
    template_id = HiddenField()
    name = StringField("Nazwa szablonu", validators=[DataRequired(), Length(max=160)])
    event_key = SelectField("Zdarzenie", validators=[DataRequired()], choices=NOTIFICATION_EVENT_CHOICES)
    channel = SelectField("Kanał", validators=[DataRequired()], choices=CHANNEL_CHOICES)
    subject = StringField("Temat (e-mail)", validators=[Optional(), Length(max=255)])
    body = TextAreaField("Treść", validators=[DataRequired(), Length(max=10000)])
    is_enabled = BooleanField("Aktywny")

    submit = SubmitField("Zapisz szablon")


class ServiceOrderNumberingForm(FlaskForm):
    prefix = StringField(
        "Prefiks",
        validators=[DataRequired(), Length(min=1, max=20), Regexp(r"^[A-Za-z0-9-]+$")],
    )
    include_year = BooleanField("Uwzględniaj rok w numerze")
    digits = IntegerField("Liczba cyfr numeru kolejnego", validators=[DataRequired(), NumberRange(min=3, max=10)])
    submit = SubmitField("Zapisz numerację zleceń")
