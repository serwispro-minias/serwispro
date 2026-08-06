"""Flask-WTF forms for service orders."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, HiddenField, SelectField, StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class ServiceOrderForm(FlaskForm):
    customer_id = SelectField("Klient", coerce=int, validators=[DataRequired()])
    device_id = SelectField("Urządzenie", coerce=int, validators=[DataRequired()])
    order_number = StringField("Numer zlecenia", validators=[DataRequired(), Length(max=50)])
    status = SelectField("Status", validators=[DataRequired()])
    priority = SelectField("Priorytet", validators=[DataRequired()])
    intake_date = DateField("Data przyjęcia", validators=[DataRequired()], format="%Y-%m-%d")
    planned_finish_date = DateField("Planowana data zakończenia", validators=[Optional()], format="%Y-%m-%d")
    finished_at = DateField("Data zakończenia", validators=[Optional()], format="%Y-%m-%d")
    warranty_repair = BooleanField("Naprawa gwarancyjna")
    issue_description = TextAreaField("Opis usterki", validators=[DataRequired(), Length(max=10000)])
    diagnosis = TextAreaField("Diagnoza", validators=[Optional(), Length(max=10000)])
    repair_description = TextAreaField("Opis naprawy", validators=[Optional(), Length(max=10000)])
    technician_notes = TextAreaField("Notatki technika", validators=[Optional(), Length(max=10000)])
    customer_notes = TextAreaField("Uwagi klienta", validators=[Optional(), Length(max=10000)])
    estimated_cost = DecimalField("Szacowany koszt", validators=[Optional()], places=2)
    final_cost = DecimalField("Końcowy koszt", validators=[Optional()], places=2)
    external_reference = StringField("Numer zewnętrzny", validators=[Optional(), Length(max=120)])
    submit = SubmitField("Zapisz")


class ServiceOrderSearchForm(FlaskForm):
    query = StringField("Szukaj", validators=[Optional(), Length(max=255)])
    status = SelectField("Status", validators=[Optional()])
    submit = SubmitField("Filtruj")
