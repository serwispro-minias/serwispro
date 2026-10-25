from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import Length, Optional


class DeviceForm(FlaskForm):
    """Form for creating and editing devices."""

    manufacturer = StringField("Producent", validators=[Optional(), Length(max=120)])
    model = StringField("Model", validators=[Optional(), Length(max=120)])
    device_type = StringField("Typ urządzenia", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Zapisz")
