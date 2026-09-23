from flask_wtf import FlaskForm
from wtforms import SubmitField


class StockIssueManualForm(FlaskForm):
    submit = SubmitField("Utwórz RW")


class StockIssuePostForm(FlaskForm):
    submit = SubmitField("Zaksięguj RW")
