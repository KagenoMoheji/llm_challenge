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
from capass_server.models.entities import TblAgent, TblAgentTool, TblToolServer

# commit は呼び出し側(service)の責務。insert系はflushまでで、一意制約違反などをこの時点で検出する


def find_tbl_tool_server_by_id(db: Session, tool_server_id: int) -> TblToolServer | None:
    return db.get(TblToolServer, tool_server_id)


def find_tbl_tool_server_by_public_key(db: Session, tool_server_public_key: str) -> TblToolServer | None:
    stmt = select(TblToolServer).where(TblToolServer.tool_server_public_key == tool_server_public_key)
    return db.execute(stmt).scalar_one_or_none()


def insert_tbl_tool_server(db: Session, tool_server: TblToolServer) -> TblToolServer:
    db.add(tool_server)
    db.flush()
    return tool_server


def find_tbl_agent_by_agent_id(db: Session, agent_id: str) -> TblAgent | None:
    stmt = select(TblAgent).where(TblAgent.agent_id == agent_id)
    return db.execute(stmt).scalar_one_or_none()


def insert_tbl_agent(db: Session, agent: TblAgent) -> TblAgent:
    db.add(agent)
    db.flush()
    return agent


def find_tbl_agent_tool(db: Session, tool_endpoint: str, agent_id: str) -> TblAgentTool | None:
    stmt = select(TblAgentTool).where(
        TblAgentTool.tool_endpoint == tool_endpoint,
        TblAgentTool.agent_id == agent_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def insert_tbl_agent_tool(db: Session, agent_tool: TblAgentTool) -> TblAgentTool:
    db.add(agent_tool)
    db.flush()
    return agent_tool
