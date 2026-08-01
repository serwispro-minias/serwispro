from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class DeviceForm(FlaskForm):
    """Form for creating and editing devices."""

    customer_id = SelectField("Klient", coerce=int, validators=[DataRequired()])
    manufacturer = StringField("Producent", validators=[Optional(), Length(max=120)])
    model = StringField("Model", validators=[Optional(), Length(max=120)])
    serial_number = StringField("Numer seryjny", validators=[Optional(), Length(max=120)])
    inventory_number = StringField("Numer inwentarzowy", validators=[Optional(), Length(max=120)])
    device_type = StringField("Typ urządzenia", validators=[Optional(), Length(max=80)])
    purchase_date = DateField("Data zakupu", validators=[Optional()])
    warranty_until = DateField("Gwarancja do", validators=[Optional()])
    password = StringField("Hasło", validators=[Optional(), Length(max=255)])
    condition_description = TextAreaField("Opis stanu", validators=[Optional(), Length(max=5000)])
    accessories = TextAreaField("Akcesoria", validators=[Optional(), Length(max=5000)])
    notes = TextAreaField("Uwagi", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Zapisz")
