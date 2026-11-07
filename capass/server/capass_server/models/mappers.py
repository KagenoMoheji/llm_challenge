import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from capass_server.models.entities import (
    ApprovalStatus,
    TblAdmin,
    TblAgent,
    TblAgentTool,
    TblRequestNonce,
    TblTool,
    TblToolServer,
)

# commit は呼び出し側(service)の責務。insert系はflushまでで、一意制約違反などをこの時点で検出する


# ---------- tbl_admin ----------
def find_tbl_admin_by_public_key(db: Session, admin_public_key: str) -> TblAdmin | None:
    stmt = select(TblAdmin).where(TblAdmin.admin_public_key == admin_public_key)
    return db.execute(stmt).scalar_one_or_none()


# ---------- tbl_tool_server ----------
def find_tbl_tool_server_by_id(db: Session, tool_server_id: int) -> TblToolServer | None:
    return db.get(TblToolServer, tool_server_id)


def find_tbl_tool_server_by_public_key(db: Session, tool_server_public_key: str) -> TblToolServer | None:
    stmt = select(TblToolServer).where(TblToolServer.tool_server_public_key == tool_server_public_key)
    return db.execute(stmt).scalar_one_or_none()


def insert_tbl_tool_server(db: Session, tool_server: TblToolServer) -> TblToolServer:
    db.add(tool_server)
    db.flush()
    return tool_server


def find_tbl_tool_server_reserved_successor(db: Session, predecessor_id: int, now: datetime) -> TblToolServer | None:
    """旧ツールサーバ(predecessor_id)の後継として予約されている(RESERVED)、期限内のツールサーバを返す。"""
    stmt = select(TblToolServer).where(
        TblToolServer.replaces_tool_server_id == predecessor_id,
        TblToolServer.status == ApprovalStatus.RESERVED.value,
        TblToolServer.status_expires_at > now,
    )
    return db.execute(stmt).scalars().first()


def find_tbl_tool_server_active_successor(db: Session, predecessor_id: int) -> TblToolServer | None:
    """旧ツールサーバ(predecessor_id)の後継で、いまアクティブ(APPROVED)なツールサーバを返す。"""
    stmt = select(TblToolServer).where(
        TblToolServer.replaces_tool_server_id == predecessor_id,
        TblToolServer.status == ApprovalStatus.APPROVED.value,
    )
    return db.execute(stmt).scalars().first()


def update_tbl_tool_server_status(db: Session, tool_server_id: int, expected_status: str, new_status: str, status_expires_at: datetime | None) -> bool:
    """ステータスが、expected_statusのままの場合だけ、new_statusに更新する(並行して別のリクエストが更新していたらFalse)。"""
    stmt = (
        update(TblToolServer)
        .where(TblToolServer.id == tool_server_id, TblToolServer.status == expected_status)
        .values(status=new_status, status_expires_at=status_expires_at)
    )
    return db.execute(stmt).rowcount == 1


# ---------- tbl_agent ----------
def find_tbl_agent_by_agent_id(db: Session, agent_id: str) -> TblAgent | None:
    stmt = select(TblAgent).where(TblAgent.agent_id == agent_id)
    return db.execute(stmt).scalar_one_or_none()


def insert_tbl_agent(db: Session, agent: TblAgent) -> TblAgent:
    db.add(agent)
    db.flush()
    return agent


# ---------- tbl_tool ----------
def find_tbl_tool_by_endpoint(db: Session, tool_endpoint: str) -> TblTool | None:
    stmt = select(TblTool).where(TblTool.tool_endpoint == tool_endpoint)
    return db.execute(stmt).scalar_one_or_none()


def insert_tbl_tool(db: Session, tool: TblTool) -> TblTool:
    db.add(tool)
    db.flush()
    return tool


def move_tbl_tool_to_tool_server(db: Session, from_tool_server_id: int, to_tool_server_id: int) -> int:
    """ツールの持つツールサーバのidを、付け替える(ツールサーバのリプレース)。付け替えたツールの数を返す。"""
    stmt = update(TblTool).where(TblTool.tool_server_id == from_tool_server_id).values(tool_server_id=to_tool_server_id)
    return db.execute(stmt).rowcount


# ---------- tbl_agent_tool(割り当て) ----------
def find_tbl_agent_tool(db: Session, agent_id: str, tool_id: int) -> TblAgentTool | None:
    stmt = select(TblAgentTool).where(TblAgentTool.agent_id == agent_id, TblAgentTool.tool_id == tool_id)
    return db.execute(stmt).scalar_one_or_none()


def insert_tbl_agent_tool(db: Session, agent_tool: TblAgentTool) -> TblAgentTool:
    db.add(agent_tool)
    db.flush()
    return agent_tool


def list_tbl_tool_executable(db: Session, agent_id: str) -> list[TblTool]:
    """AIエージェントが実行できるツール(割り当てが承認済みで、ロックされておらず、ツールサーバが承認済み)の一覧を、ツールエンドポイント順に返す。"""
    stmt = (
        select(TblTool)
        .join(TblAgentTool, TblAgentTool.tool_id == TblTool.id)
        .join(TblToolServer, TblToolServer.id == TblTool.tool_server_id)
        .where(
            TblAgentTool.agent_id == agent_id,
            TblAgentTool.status == ApprovalStatus.APPROVED.value,
            TblAgentTool.locked.is_(False),
            TblTool.locked.is_(False),
            TblToolServer.status == ApprovalStatus.APPROVED.value,
        )
        .order_by(TblTool.tool_endpoint)
    )
    return list(db.execute(stmt).scalars().all())


def find_tbl_tool_executable(db: Session, agent_id: str, tool_endpoint: str) -> tuple[TblAgentTool, TblTool, TblToolServer] | None:
    """実行できるツール(上のlistと同じ条件)について、割り当て・ツール・ツールサーバを返す。"""
    stmt = (
        select(TblAgentTool, TblTool, TblToolServer)
        .join(TblTool, TblTool.id == TblAgentTool.tool_id)
        .join(TblToolServer, TblToolServer.id == TblTool.tool_server_id)
        .where(
            TblAgentTool.agent_id == agent_id,
            TblTool.tool_endpoint == tool_endpoint,
            TblAgentTool.status == ApprovalStatus.APPROVED.value,
            TblAgentTool.locked.is_(False),
            TblTool.locked.is_(False),
            TblToolServer.status == ApprovalStatus.APPROVED.value,
        )
    )
    row = db.execute(stmt).first()
    return None if row is None else (row[0], row[1], row[2])


# ---------- tbl_request_nonce ----------
def delete_expired_tbl_request_nonce(db: Session, now: datetime) -> None:
    db.execute(delete(TblRequestNonce).where(TblRequestNonce.expires_at < now))


def insert_tbl_request_nonce(db: Session, nonce: TblRequestNonce) -> TblRequestNonce:
    db.add(nonce)
    db.flush()
    return nonce
