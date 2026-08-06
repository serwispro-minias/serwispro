from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import Length, Optional


class PublicEstimateApprovalForm(FlaskForm):
    customer_note = TextAreaField("Uwagi klienta", validators=[Optional(), Length(max=4000)])
