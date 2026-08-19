from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.part_demand import PART_DEMAND_PRIORITY_CHOICES, PART_DEMAND_STATUS_CHOICES


class PartDemandForm(FlaskForm):
    service_order_id = IntegerField("Zlecenie", validators=[DataRequired(), NumberRange(min=1)])
    service_order_item_id = IntegerField("Pozycja zlecenia", validators=[Optional(), NumberRange(min=1)])
    inventory_item_id = SelectField("Część", coerce=int, validators=[DataRequired()])

    requested_quantity = DecimalField("Ilość wymagana", places=3, validators=[DataRequired(), NumberRange(min=0.001)])
    reserved_quantity = DecimalField("Ilość zarezerwowana", places=3, validators=[Optional(), NumberRange(min=0)])
    missing_quantity = DecimalField(
        "Ilość brakująca",
        places=3,
        validators=[Optional(), NumberRange(min=0)],
        render_kw={"readonly": True, "tabindex": "-1"},
    )

    status = SelectField("Status", choices=PART_DEMAND_STATUS_CHOICES, validators=[DataRequired()])
    priority = SelectField("Priorytet", choices=PART_DEMAND_PRIORITY_CHOICES, validators=[DataRequired()])
    expected_date = DateField("Planowany termin", validators=[Optional()])
    notes = TextAreaField("Notatki", validators=[Optional(), Length(max=10000)])

    submit = SubmitField("Zapisz")


class PartDemandFilterForm(FlaskForm):
    status = SelectField("Status", validators=[Optional()])
    priority = SelectField("Priorytet", validators=[Optional()])
    branch_id = SelectField("Magazyn", coerce=int, validators=[Optional()])
    order_id = IntegerField("Zlecenie", validators=[Optional(), NumberRange(min=1)])
    inventory_item_id = SelectField("Część", coerce=int, validators=[Optional()])
    expected_date_from = DateField("Data od", validators=[Optional()])
    expected_date_to = DateField("Data do", validators=[Optional()])
    q = StringField("Szukaj", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Filtruj")


class PartDemandStatusForm(FlaskForm):
    status = SelectField("Status", choices=PART_DEMAND_STATUS_CHOICES, validators=[DataRequired()])
    expected_date = DateField("Planowany termin", validators=[Optional()])
    notes = TextAreaField("Notatka", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Aktualizuj")


class PartDemandFulfillForm(FlaskForm):
    reserve_quantity = DecimalField("Ilość do przypisania", places=3, validators=[DataRequired(), NumberRange(min=0.001)])
    submit = SubmitField("Oznacz jako zrealizowane")
