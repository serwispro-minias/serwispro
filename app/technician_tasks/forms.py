from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateTimeLocalField, FileField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.service_task import SERVICE_TASK_PRIORITY_CHOICES, SERVICE_TASK_STATUS_CHOICES, SERVICE_TASK_TYPE_CHOICES


class ServiceTaskForm(FlaskForm):
    parent_task_id = SelectField("Zadanie nadrzędne", coerce=int, validators=[Optional()])
    title = StringField("Tytuł", validators=[DataRequired(), Length(max=255)])
    description = TextAreaField("Opis", validators=[Optional(), Length(max=10000)])

    task_type = SelectField("Typ zadania", validators=[DataRequired()], choices=SERVICE_TASK_TYPE_CHOICES)
    status = SelectField("Status", validators=[DataRequired()], choices=SERVICE_TASK_STATUS_CHOICES)
    priority = SelectField("Priorytet", validators=[DataRequired()], choices=SERVICE_TASK_PRIORITY_CHOICES)
    assigned_to = SelectField("Przypisany technik", coerce=int, validators=[Optional()])

    planned_start = DateTimeLocalField("Planowany start", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    planned_finish = DateTimeLocalField("Planowany koniec", validators=[Optional()], format="%Y-%m-%dT%H:%M")

    estimated_minutes = IntegerField("Szacowany czas (min)", validators=[Optional(), NumberRange(min=0)])
    completion_percent = IntegerField("Postęp %", validators=[Optional(), NumberRange(min=0, max=100)])
    requires_confirmation = BooleanField("Wymaga potwierdzenia")

    submit = SubmitField("Zapisz")


class ServiceTaskStatusForm(FlaskForm):
    status = SelectField("Status", validators=[DataRequired()], choices=SERVICE_TASK_STATUS_CHOICES)
    note = TextAreaField("Notatka", validators=[Optional(), Length(max=2000)])
    completion_percent = IntegerField("Postęp %", validators=[Optional(), NumberRange(min=0, max=100)])
    submit = SubmitField("Aktualizuj status")


class ServiceTaskCommentForm(FlaskForm):
    content = TextAreaField("Komentarz", validators=[DataRequired(), Length(max=10000)])
    submit = SubmitField("Dodaj komentarz")


class ServiceTaskAttachmentForm(FlaskForm):
    file = FileField("Załącznik", validators=[DataRequired()])
    submit = SubmitField("Dodaj załącznik")


class ServiceTaskTimeActionForm(FlaskForm):
    note = TextAreaField("Notatka", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Zapisz")


class ServiceTaskFilterForm(FlaskForm):
    q = StringField("Szukaj", validators=[Optional(), Length(max=255)])
    status = SelectField("Status", validators=[Optional()])
    priority = SelectField("Priorytet", validators=[Optional()])
    assigned_to = SelectField("Technik", coerce=int, validators=[Optional()])
    submit = SubmitField("Filtruj")
