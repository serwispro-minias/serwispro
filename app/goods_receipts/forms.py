from flask_wtf import FlaskForm
from wtforms import SubmitField


class GoodsReceiptManualForm(FlaskForm):
    """CSRF-bearing form for the dynamic manual receipt fields."""

    submit = SubmitField("Utwórz PZ")


class GoodsReceiptAcceptForm(FlaskForm):
    submit = SubmitField("Zatwierdź PZ")