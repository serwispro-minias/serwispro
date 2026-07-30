from datetime import datetime

from app.extensions import db


class SystemLog(db.Model):

    __tablename__ = "system_logs"


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    user_id = db.Column(
        db.Integer
    )


    action = db.Column(
        db.String(255)
    )


    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
