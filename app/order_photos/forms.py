from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, HiddenField, IntegerField, MultipleFileField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.service_order_photo_annotation import PHOTO_ANNOTATION_PRIORITY_CHOICES, PHOTO_ANNOTATION_TYPE_CHOICES
from app.models.service_order_photo import SERVICE_ORDER_PHOTO_TYPE_CHOICES


class ServiceOrderPhotoUploadForm(FlaskForm):
    photo_type = SelectField("Typ zdjęcia", validators=[DataRequired()], choices=SERVICE_ORDER_PHOTO_TYPE_CHOICES)
    title = StringField("Tytuł", validators=[Optional(), Length(max=255)])
    description = TextAreaField("Opis", validators=[Optional(), Length(max=5000)])
    taken_at = DateField("Data wykonania", validators=[Optional()], format="%Y-%m-%d")
    sort_order = IntegerField("Kolejność", validators=[Optional(), NumberRange(min=0, max=9999)])
    is_visible_for_customer = BooleanField("Widoczne dla klienta")
    main_photo_index = HiddenField("Zdjęcie główne", validators=[Optional(), Length(max=20)])
    files = MultipleFileField("Zdjęcia", validators=[DataRequired()])
    submit = SubmitField("Dodaj zdjęcia")


class ServiceOrderPhotoFilterForm(FlaskForm):
    photo_type = SelectField("Typ", validators=[Optional()], choices=[("", "Wszystkie")] + SERVICE_ORDER_PHOTO_TYPE_CHOICES)
    date_from = DateField("Data od", validators=[Optional()], format="%Y-%m-%d")
    date_to = DateField("Data do", validators=[Optional()], format="%Y-%m-%d")
    author_id = SelectField("Autor", coerce=int, validators=[Optional()])
    submit = SubmitField("Filtruj")


class ServiceOrderPhotoDeleteForm(FlaskForm):
    submit = SubmitField("Usuń")


class ServiceOrderPhotoProtocolSelectionForm(FlaskForm):
    photo_ids = HiddenField("Wybrane zdjęcia", validators=[Optional(), Length(max=4000)])
    photo_render_mode = SelectField(
        "Wariant zdjęcia",
        validators=[DataRequired()],
        choices=[("original", "Zdjecie oryginalne"), ("annotated", "Zdjecie z oznaczeniami")],
        default="original",
    )
    submit_intake = SubmitField("Drukuj w protokole przyjęcia")
    submit_release = SubmitField("Drukuj w protokole wydania")


class PhotoAnnotationCreateForm(FlaskForm):
    annotation_type = SelectField("Typ", validators=[DataRequired()], choices=PHOTO_ANNOTATION_TYPE_CHOICES)
    x = DecimalField("X", validators=[DataRequired(), NumberRange(min=0, max=1)])
    y = DecimalField("Y", validators=[DataRequired(), NumberRange(min=0, max=1)])
    width = DecimalField("Szerokosc", validators=[Optional(), NumberRange(min=0, max=2)], default=0)
    height = DecimalField("Wysokosc", validators=[Optional(), NumberRange(min=0, max=2)], default=0)
    rotation = DecimalField("Rotacja", validators=[Optional(), NumberRange(min=-360, max=360)], default=0)
    color = StringField("Kolor", validators=[DataRequired(), Length(max=16)])
    title = StringField("Tytul", validators=[Optional(), Length(max=255)])
    description = TextAreaField("Opis", validators=[Optional(), Length(max=5000)])
    priority = SelectField("Priorytet", validators=[DataRequired()], choices=PHOTO_ANNOTATION_PRIORITY_CHOICES, default="NORMAL")
    is_visible_for_customer = BooleanField("Widoczne dla klienta")
    points_json = HiddenField("Punkty", validators=[Optional(), Length(max=20000)])
    submit = SubmitField("Dodaj oznaczenie")


class PhotoAnnotationUpdateForm(PhotoAnnotationCreateForm):
    annotation_id = HiddenField("ID adnotacji", validators=[DataRequired()])
    submit = SubmitField("Zapisz oznaczenie")


class PhotoAnnotationDeleteForm(FlaskForm):
    annotation_id = HiddenField("ID adnotacji", validators=[DataRequired()])
    submit = SubmitField("Usun oznaczenie")
