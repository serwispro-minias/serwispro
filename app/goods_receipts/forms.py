from flask_wtf import FlaskForm
from wtforms import SubmitField


class GoodsReceiptAcceptForm(FlaskForm):
    submit = SubmitField("Zatwierdź PZ")