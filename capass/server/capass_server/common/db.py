import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from capass_server.common.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)


def create_db_engine(db_host, db_port, db_name, db_user, db_password):
    # URL.create を使うことで、ユーザ名/パスワードに「@」「:」「/」等の特殊文字が含まれていても自動でエスケープされる
    db_url = URL.create(
        drivername="postgresql+psycopg",
        username=db_user,
        password=db_password,
        host=db_host,
        port=db_port,
        database=db_name,
    )
    _connect_args = {"check_same_thread": False} if db_url.get_backend_name() == "sqlite" else {}
    # create_engine はこの時点ではDBに接続しない(遅延接続)。接続確認とリトライは wait_for_db で行う
    return create_engine(db_url, connect_args=_connect_args)


def wait_for_db(db_engine, db_retry_count, db_retry_delay_sec):
    """DBへ実際に接続できるか(SELECT 1)を確認し、失敗したらリトライする。リトライ上限に達したら最後の例外を送出する。"""
    if db_retry_count < 1:
        raise ValueError("db_retry_count must be >= 1")

    for i in range(1, db_retry_count + 1):
        try:
            with db_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except SQLAlchemyError as e:
            if i < db_retry_count:
                logger.warning("DB connection failed (%d/%d). retry in %ss: %s", i, db_retry_count, db_retry_delay_sec, e)
                time.sleep(db_retry_delay_sec)
            else:
                raise e


engine = create_db_engine(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
