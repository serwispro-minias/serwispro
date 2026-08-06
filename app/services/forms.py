from __future__ import annotations

from datetime import date, timedelta

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, HiddenField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class EstimateCreateForm(FlaskForm):
    valid_until = DateField("Ważny do", validators=[Optional()], default=lambda: date.today() + timedelta(days=14))
    notes = TextAreaField("Notatki", validators=[Optional(), Length(max=4000)])
    submit = SubmitField("Utwórz kosztorys")


class EstimateItemForm(FlaskForm):
    source_type = HiddenField(default="MANUAL")
    name = StringField("Nazwa pozycji", validators=[DataRequired(), Length(max=255)])
    description = TextAreaField("Opis", validators=[Optional(), Length(max=4000)])
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.001)], places=3)
    unit = StringField("Jednostka", validators=[Optional(), Length(max=40)])
    unit_net_price = DecimalField("Cena netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    discount_percent = DecimalField("Rabat %", validators=[Optional(), NumberRange(min=0)], places=2)
    vat_rate = DecimalField("VAT %", validators=[Optional(), NumberRange(min=0)], places=2)
    sort_order = DecimalField("Kolejność", validators=[Optional(), NumberRange(min=0)], places=0)
    submit = SubmitField("Dodaj pozycję")


class EstimateSendForm(FlaskForm):
    submit = SubmitField("Wyślij do klienta")


class EstimateStatusForm(FlaskForm):
    status = StringField("Status", validators=[DataRequired(), Length(max=20)])
    submit = SubmitField("Zmień status")


class EstimateReorderForm(FlaskForm):
    item_order = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Przestaw kolejność")
