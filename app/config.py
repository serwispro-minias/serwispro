import os
from dotenv import load_dotenv


load_dotenv()


class Config:

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "serwispro-secret-key"
    )


    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://"
        + os.getenv("DATABASE_USER", "root")
        + ":"
        + os.getenv("DATABASE_PASSWORD", "")
        + "@"
        + os.getenv("DATABASE_HOST", "localhost")
        + ":"
        + os.getenv("DATABASE_PORT", "3306")
        + "/"
        + os.getenv("DATABASE_NAME", "serwispro")
    )


