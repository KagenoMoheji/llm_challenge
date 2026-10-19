import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from capass_server.models.entities import ApprovalStatus, TblAdmin, TblAgent, TblAgentTool, TblRequestNonce, TblToolServer

# commit は呼び出し側(service)の責務。insert系はflushまでで、一意制約違反などをこの時点で検出する


def find_tbl_admin_by_public_key(db: Session, admin_public_key: str) -> TblAdmin | None:
    stmt = select(TblAdmin).where(TblAdmin.admin_public_key == admin_public_key)
    return db.execute(stmt).scalar_one_or_none()


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


def list_tbl_agent_tool_executable(db: Session, agent_id: str) -> list[TblAgentTool]:
    """AIエージェントが実行できるツール(ロックされておらず、ツールサーバが承認済み)の一覧を、ツールエンドポイント順に返す。"""
    stmt = (
        select(TblAgentTool)
        .join(TblToolServer, TblToolServer.tool_server_public_key == TblAgentTool.tool_server_public_key)
        .where(
            TblAgentTool.agent_id == agent_id,
            TblAgentTool.locked.is_(False),
            TblToolServer.status == ApprovalStatus.APPROVED.value,
        )
        .order_by(TblAgentTool.tool_endpoint)
    )
    return list(db.execute(stmt).scalars().all())


def find_tbl_agent_tool_executable(db: Session, agent_id: str, tool_endpoint: str) -> tuple[TblAgentTool, TblToolServer] | None:
    """実行できる(ロックされておらず、ツールサーバが承認済みの)ツールと、そのツールサーバを返す。"""
    stmt = (
        select(TblAgentTool, TblToolServer)
        .join(TblToolServer, TblToolServer.tool_server_public_key == TblAgentTool.tool_server_public_key)
        .where(
            TblAgentTool.agent_id == agent_id,
            TblAgentTool.tool_endpoint == tool_endpoint,
            TblAgentTool.locked.is_(False),
            TblToolServer.status == ApprovalStatus.APPROVED.value,
        )
    )
    row = db.execute(stmt).first()
    return None if row is None else (row[0], row[1])


def delete_expired_tbl_request_nonce(db: Session, now: datetime) -> None:
    db.execute(delete(TblRequestNonce).where(TblRequestNonce.expires_at < now))


def insert_tbl_request_nonce(db: Session, nonce: TblRequestNonce) -> TblRequestNonce:
    db.add(nonce)
    db.flush()
    return nonce
