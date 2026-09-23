from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


CATEGORY_KIND_CHOICES: list[tuple[str, str]] = [
    ("ANY", "Wszystkie"),
    ("PART", "Części"),
    ("MATERIAL", "Materiały"),
    ("SERVICE", "Usługi"),
]

MOVEMENT_TYPE_CHOICES: list[tuple[str, str]] = [
    ("RECEIPT", "Przyjęcie"),
    ("ISSUE", "Wydanie"),
    ("ADJUSTMENT", "Korekta"),
    ("RESERVATION", "Rezerwacja"),
    ("RELEASE", "Zwolnienie rezerwacji"),
    ("SALE", "Sprzedaż"),
    ("AUTO_ISSUE", "Automatyczne odpisanie"),
]


class CatalogSearchForm(FlaskForm):
    q = StringField("Szukaj", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Szukaj")


class CategoryForm(FlaskForm):
    code = StringField("Kod", validators=[DataRequired(), Length(max=60)])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=160)])
    is_active = BooleanField("Aktywna", default=True)
    submit = SubmitField("Zapisz")


class SupplierForm(FlaskForm):
    code = StringField("Kod", validators=[DataRequired(), Length(max=60)])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=180)])
    email = StringField("E-mail", validators=[Optional(), Email(), Length(max=120)])
    phone = StringField("Telefon", validators=[Optional(), Length(max=50)])
    tax_id = StringField("NIP", validators=[Optional(), Length(max=20)])
    contact_person = StringField("Osoba kontaktowa", validators=[Optional(), Length(max=180)])
    website = StringField("WWW", validators=[Optional(), Length(max=255)])
    is_active = BooleanField("Aktywny", default=True)
    submit = SubmitField("Zapisz")


class ManufacturerForm(FlaskForm):
    code = StringField("Kod", validators=[DataRequired(), Length(max=60)])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=180)])
    website = StringField("WWW", validators=[Optional(), Length(max=255)])
    notes = TextAreaField("Notatki", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Zapisz")


class VatRateForm(FlaskForm):
    code = StringField("Kod", validators=[DataRequired(), Length(max=20)])
    rate = DecimalField("Stawka (%)", validators=[DataRequired(), NumberRange(min=0)], places=2)
    is_default = BooleanField("Domyślna")
    is_active = BooleanField("Aktywna", default=True)
    submit = SubmitField("Zapisz")


class PartForm(FlaskForm):
    code = StringField("Kod", validators=[DataRequired(), Length(max=80)])
    category_id = SelectField("Kategoria", coerce=int, validators=[DataRequired(message="Kategoria jest wymagana.")])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=255)])
    barcode = StringField("Kod kreskowy", validators=[Optional(), Length(max=64)])
    current_stock = IntegerField("Ilość sztuk", validators=[DataRequired(), NumberRange(min=0)])
    purchase_price_net = DecimalField("Cena zakupu netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    vat_id = SelectField("VAT", coerce=int, validators=[DataRequired(message="Stawka VAT jest wymagana.")])
    sale_price_net = DecimalField("Cena sprzedaży netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    submit = SubmitField("Zapisz")


class MaterialForm(FlaskForm):
    code = StringField("Kod", validators=[DataRequired(), Length(max=80)])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=255)])
    category_id = SelectField("Kategoria", coerce=int, validators=[Optional()])
    manufacturer_id = SelectField("Producent", coerce=int, validators=[Optional()])
    unit = StringField("Jednostka", validators=[DataRequired(), Length(max=40)])
    current_stock = DecimalField("Stan", validators=[DataRequired(), NumberRange(min=0)], places=3)
    minimum_stock = DecimalField("Minimum", validators=[DataRequired(), NumberRange(min=0)], places=3)
    purchase_price_net = DecimalField("Cena zakupu netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    default_usage_qty = DecimalField("Domyślne zużycie", validators=[DataRequired(), NumberRange(min=0)], places=3)
    vat_rate = DecimalField("VAT (%)", validators=[DataRequired(), NumberRange(min=0)], places=2)
    location = StringField("Lokalizacja", validators=[Optional(), Length(max=120)])
    auto_issue_on_order = BooleanField("Automatyczne odpisanie")
    description = TextAreaField("Opis", validators=[Optional(), Length(max=10000)])
    submit = SubmitField("Zapisz")


class ServiceItemForm(FlaskForm):
    code = StringField("Kod", validators=[DataRequired(), Length(max=80)])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=255)])
    category_id = SelectField("Kategoria", coerce=int, validators=[Optional()])
    default_price_net = DecimalField("Cena netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    vat_rate = DecimalField("VAT (%)", validators=[DataRequired(), NumberRange(min=0)], places=2)
    standard_duration_minutes = IntegerField("Czas standardowy (min)", validators=[DataRequired(), NumberRange(min=0)])
    is_sellable = BooleanField("Aktywna sprzedaż")
    description = TextAreaField("Opis", validators=[Optional(), Length(max=10000)])
    submit = SubmitField("Zapisz")


class StockMovementForm(FlaskForm):
    movement_type = SelectField("Typ ruchu", validators=[DataRequired()], choices=MOVEMENT_TYPE_CHOICES)
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.001)], places=3)
    reference_type = StringField("Typ dokumentu", validators=[Optional(), Length(max=40)])
    reference_id = StringField("Numer dokumentu", validators=[Optional(), Length(max=80)])
    note = TextAreaField("Komentarz", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Zapisz ruch")


class PartReservationForm(FlaskForm):
    part_id = SelectField("Część", coerce=int, validators=[DataRequired()])
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.001)], places=3)
    submit = SubmitField("Zarezerwuj")


class MaterialUsageForm(FlaskForm):
    material_id = SelectField("Materiał", coerce=int, validators=[DataRequired()])
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.001)], places=3)
    submit = SubmitField("Odpisz")


class ServiceOrderLineForm(FlaskForm):
    service_item_id = SelectField("Usługa", coerce=int, validators=[DataRequired()])
    quantity = DecimalField("Ilość", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    submit = SubmitField("Dodaj usługę")


class AutoIssueMaterialsForm(FlaskForm):
    submit = SubmitField("Automatycznie odpisz materiały")
