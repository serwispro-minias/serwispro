from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.inventory_stock_operation import INVENTORY_OPERATION_TYPE_CHOICES


class InventoryPartForm(FlaskForm):
    code = StringField("Kod produktu", validators=[DataRequired(), Length(max=80)])
    category_id = SelectField("Kategoria", coerce=int, validators=[DataRequired(), NumberRange(min=1)])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=255)])
    barcode = StringField("Kod kreskowy", validators=[Optional(), Length(max=64)])
    current_stock = IntegerField("Ilość sztuk", validators=[NumberRange(min=0)])
    purchase_price_net = DecimalField("Cena zakupu netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    sale_price_net = DecimalField("Cena sprzedaży netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    vat_id = SelectField("VAT", coerce=int, validators=[DataRequired(), NumberRange(min=1)])
    is_active = SelectField("Aktywny", validators=[DataRequired()], choices=[("1", "Tak"), ("0", "Nie")])
    submit = SubmitField("Zapisz")


class InventoryOperationForm(FlaskForm):
    operation_type = SelectField("Typ operacji", validators=[DataRequired()], choices=[("ADJUSTMENT", "Jawna korekta stanu")])
    quantity = DecimalField("Stan po korekcie", validators=[NumberRange(min=0)], places=3)
    document_number = StringField("Numer dokumentu korekty", validators=[DataRequired(), Length(max=80)])
    comment = TextAreaField("Uzasadnienie korekty", validators=[DataRequired(), Length(max=3000)])
    submit = SubmitField("Zapisz operację")


class InventorySearchForm(FlaskForm):
    q = StringField("Szukaj", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Szukaj")
