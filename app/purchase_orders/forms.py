from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.purchase_order import PURCHASE_ORDER_STATUS_CHOICES


class PurchaseOrderForm(FlaskForm):
    supplier_id = SelectField("Dostawca", coerce=int, validators=[DataRequired(), NumberRange(min=1)])
    order_date = DateField("Data zamówienia", validators=[DataRequired()])
    expected_delivery_date = DateField("Przewidywana dostawa", validators=[Optional()])
    notes = TextAreaField("Uwagi", validators=[Optional(), Length(max=10000)])
    submit = SubmitField("Zapisz zamówienie")


class PurchaseOrderStatusForm(FlaskForm):
    status = SelectField("Status", choices=PURCHASE_ORDER_STATUS_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Zapisz status")


class PurchaseOrderFilterForm(FlaskForm):
    status = SelectField("Status", choices=[("", "Wszystkie")] + PURCHASE_ORDER_STATUS_CHOICES, validators=[Optional()])
    supplier_id = SelectField("Dostawca", coerce=int, validators=[Optional()])
    date_from = DateField("Data od", validators=[Optional()])
    date_to = DateField("Data do", validators=[Optional()])
    po_number = StringField("Numer PO", validators=[Optional(), Length(max=60)])
    part_id = SelectField("Część", coerce=int, validators=[Optional()])
    created_by = IntegerField("Użytkownik", validators=[Optional(), NumberRange(min=1)])
    submit = SubmitField("Filtruj")


class PurchaseOrderReceiveForm(FlaskForm):
    item_id = IntegerField(validators=[DataRequired(), NumberRange(min=1)])
    quantity = DecimalField("Ilość", places=3, validators=[DataRequired(), NumberRange(min=0.001)])
    submit = SubmitField("Przyjmij")