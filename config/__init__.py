import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'serwispro-secret-key')
    DATABASE_USER = os.getenv('DATABASE_USER', 'root')
    DATABASE_PASSWORD = os.getenv('DATABASE_PASSWORD', '')
    DATABASE_HOST = os.getenv('DATABASE_HOST', 'localhost')
    DATABASE_PORT = os.getenv('DATABASE_PORT', '3306')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'serwispro')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') or (
        f'mysql+pymysql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False
    SESSION_COOKIE_SECURE = False
    TENANCY_ENABLED = True
    COMPANY_PREFIX = os.getenv('COMPANY_PREFIX', 'SER')


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv('TEST_DATABASE_URL', 'sqlite:///:memory:')


_CONFIG_MAP = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    if name is None:
        name = os.getenv('SERWISPRO_ENV', os.getenv('FLASK_ENV', 'development'))
    return _CONFIG_MAP.get(name.lower(), DevelopmentConfig)
