from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class WorkflowStatusForm(FlaskForm):
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=120)])
    code = StringField("Kod", validators=[DataRequired(), Length(max=80)])
    description = TextAreaField("Opis", validators=[Optional(), Length(max=5000)])
    color = StringField("Klasa badge", validators=[DataRequired(), Length(max=40)], default="bg-secondary")
    icon = StringField("Ikona", validators=[DataRequired(), Length(max=80)], default="bi-circle")
    sort_order = IntegerField("Kolejność", validators=[DataRequired(), NumberRange(min=0)], default=0)
    is_initial = BooleanField("Status początkowy")
    is_closed = BooleanField("Status końcowy")
    submit = SubmitField("Dodaj status")


class WorkflowTransitionForm(FlaskForm):
    from_status_code = SelectField("Z statusu", validators=[DataRequired()])
    to_status_code = SelectField("Do statusu", validators=[DataRequired()])
    name = StringField("Nazwa przejścia", validators=[DataRequired(), Length(max=160)])
    requires_permission = StringField("Wymagana rola/permisja", validators=[Optional(), Length(max=120)])
    requires_estimate = BooleanField("Wymaga zaakceptowanego kosztorysu")
    requires_parts = BooleanField("Wymaga części")
    requires_payment = BooleanField("Wymaga finalnej kwoty")
    auto_email = BooleanField("Automatyczny e-mail")
    auto_sms = BooleanField("Automatyczny SMS")
    auto_notification = BooleanField("Zapisz automatyczną akcję", default=True)
    submit = SubmitField("Dodaj przejście")
