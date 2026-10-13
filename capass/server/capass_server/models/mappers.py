import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from sqlalchemy import select
from sqlalchemy.orm import Session
from capass_server.models.entities import ToolRegistration


def find_tool_registration(db: Session, tool_endpoint: str, agent_id: str) -> ToolRegistration | None:
    stmt = select(ToolRegistration).where(
        ToolRegistration.tool_endpoint == tool_endpoint,
        ToolRegistration.agent_id == agent_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def insert_tool_registration(db: Session, registration: ToolRegistration) -> ToolRegistration:
    # commit は呼び出し側(service)の責務。ここでは flush までで、一意制約違反などをこの時点で検出する
    db.add(registration)
    db.flush()
    return registration
