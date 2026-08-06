from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, HiddenField, IntegerField, MultipleFileField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.notifications.constants import CHANNEL_CHOICES
from app.models.service_order_action import SERVICE_ORDER_ACTION_TYPE_CHOICES
from app.models.service_order_timeline import SERVICE_ORDER_TIMELINE_TYPE_CHOICES


ORDER_TYPE_CHOICES: list[tuple[str, str]] = [
    ("STANDARD", "Naprawa standardowa"),
    ("WARRANTY", "Naprawa gwarancyjna"),
]


class OrderForm(FlaskForm):
    customer_id = SelectField("Klient", coerce=int, validators=[DataRequired()])
    device_id = SelectField("Urządzenie", coerce=int, validators=[DataRequired()])
    order_number = StringField("Numer zlecenia", validators=[DataRequired(), Length(max=50)])
    order_type = SelectField("Typ zlecenia", validators=[DataRequired()])
    intake_date = DateField("Data przyjęcia", validators=[DataRequired()], format="%Y-%m-%d")
    planned_finish_date = DateField("Termin realizacji", validators=[Optional()], format="%Y-%m-%d")
    status = SelectField("Status", validators=[DataRequired()])
    priority = SelectField("Priorytet", validators=[DataRequired()])
    issue_description = TextAreaField("Opis zgłoszenia", validators=[DataRequired(), Length(max=10000)])
    diagnosis = TextAreaField("Opis usterki", validators=[Optional(), Length(max=10000)])
    repair_description = TextAreaField("Stan urządzenia przy przyjęciu", validators=[Optional(), Length(max=10000)])
    customer_notes = TextAreaField("Akcesoria pozostawione z urządzeniem", validators=[Optional(), Length(max=10000)])
    external_reference = StringField("Hasło do urządzenia", validators=[Optional(), Length(max=120)])
    technician_notes = TextAreaField("Uwagi wewnętrzne", validators=[Optional(), Length(max=10000)])
    submit = SubmitField("Zapisz")


class OrderSearchForm(FlaskForm):
    order_number = StringField("Numer zlecenia", validators=[Optional(), Length(max=255)])
    device_serial_number = StringField("Numer seryjny urządzenia", validators=[Optional(), Length(max=255)])
    customer_id = SelectField("Klient", coerce=int, validators=[Optional()])
    status = SelectField("Status", validators=[Optional()])
    sort_by = SelectField("Sortowanie", validators=[Optional()])
    sort_dir = SelectField("Kierunek", validators=[Optional()])
    submit = SubmitField("Filtruj")


class OrderStatusChangeForm(FlaskForm):
    new_status = SelectField("Nowy status", validators=[DataRequired()])
    note = TextAreaField("Notatka", validators=[Optional(), Length(max=2000)])
    force_transition = BooleanField("Wymuś przejście (administrator)")
    submit = SubmitField("Zmień status")


class TimelineEntryForm(FlaskForm):
    entry_type = SelectField("Typ wpisu", validators=[DataRequired()], choices=SERVICE_ORDER_TIMELINE_TYPE_CHOICES)
    description = TextAreaField("Opis wykonanych czynności", validators=[DataRequired(), Length(max=20000)])
    parts_cost = DecimalField("Koszt części", validators=[Optional(), NumberRange(min=0)], places=2)
    labor_minutes = IntegerField("Czas pracy (minuty)", validators=[Optional(), NumberRange(min=0)])
    attachments = MultipleFileField("Załączniki (JPG, PNG, PDF)", validators=[Optional()])
    submit = SubmitField("Dodaj wpis")


class OrderPartUsageForm(FlaskForm):
    part_id = SelectField("Część", coerce=int, validators=[DataRequired()])
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.001)], places=3)
    unit_net_price = DecimalField("Cena netto", validators=[Optional(), NumberRange(min=0)], places=2)
    submit = SubmitField("Dodaj zużycie")


class OrderItemForm(FlaskForm):
    item_type = SelectField("Typ pozycji", validators=[DataRequired()])
    item_id = HiddenField("Wybrany element", validators=[DataRequired()])
    search_query = StringField("Szukaj", validators=[Optional(), Length(max=255)])
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.001)], places=3)
    unit_price_net = DecimalField("Cena netto", validators=[Optional(), NumberRange(min=0)], places=2)
    discount_percent = DecimalField("Rabat %", validators=[Optional(), NumberRange(min=0, max=100)], places=2)
    notes = TextAreaField("Uwagi", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Dodaj pozycję")


class OrderItemMovementForm(FlaskForm):
    item_id = HiddenField("Pozycja", validators=[DataRequired()])
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.001)], places=3)
    submit_use = SubmitField("Zużyj")
    submit_return = SubmitField("Zwróć")


class OrderNotificationForm(FlaskForm):
    channel = SelectField("Kanał", validators=[DataRequired()], choices=CHANNEL_CHOICES)
    recipient = StringField("Odbiorca", validators=[DataRequired(), Length(max=255)])
    subject = StringField("Temat", validators=[Optional(), Length(max=255)])
    content = TextAreaField("Treść", validators=[DataRequired(), Length(max=10000)])
    event_key = StringField("Zdarzenie", validators=[Optional(), Length(max=60)])
    template_id = StringField("ID szablonu", validators=[Optional(), Length(max=30)])
    submit = SubmitField("Wyślij")


class OrderActionForm(FlaskForm):
    action_date = DateField("Data", validators=[DataRequired()], format="%Y-%m-%d")
    technician_id = SelectField("Serwisant", coerce=int, validators=[Optional()])
    action_type = SelectField("Rodzaj czynności", validators=[DataRequired()], choices=SERVICE_ORDER_ACTION_TYPE_CHOICES)
    description = TextAreaField("Opis", validators=[DataRequired(), Length(max=20000)])
    work_time_minutes = IntegerField("Czas pracy (min)", validators=[Optional(), NumberRange(min=0)])
    cost = DecimalField("Koszt robocizny", validators=[Optional(), NumberRange(min=0)], places=2)
    is_visible_for_customer = SelectField(
        "Widoczne dla klienta",
        choices=[("1", "Tak"), ("0", "Nie")],
        validators=[DataRequired()],
    )
    submit = SubmitField("Zapisz")
