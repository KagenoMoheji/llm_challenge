import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
import enum
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from capass_server.common.db import Base


class ToolServerStatus(str, enum.Enum):
    """ツールサーバ(公開鍵)の承認ステータス。"""

    PENDING = "pending"  # 承認待ち
    APPROVED = "approved"  # 承認済み(registが許可される)
    REVOKED = "revoked"  # 却下・失効


class TblToolServer(Base):
    """ツールサーバ(公開鍵)の承認管理レコード。CaPassサーバ管理者が承認した公開鍵のみ、ツール登録(register)が許可される。"""

    __tablename__ = "tbl_tool_server"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_server_public_key: Mapped[str] = mapped_column(String(64), unique=True)
    tool_server_name: Mapped[str] = mapped_column(String(255))  # 管理者が承認時に識別するための名称
    status: Mapped[str] = mapped_column(String(16), default=ToolServerStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TblAgentTool(Base):
    """AIエージェントとツールの紐づけレコード: [ツールエンドポイント/コンテキスト/ツール代理トークン/AIエージェント情報/ツール代理トークン更新日時/ツール利用日時/ロック状況/ツールサーバ公開鍵]"""

    __tablename__ = "tbl_agent_tool"
    __table_args__ = (
        UniqueConstraint("tool_endpoint", "agent_id", name="uq_tbl_agent_tool_endpoint_agent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_endpoint: Mapped[str] = mapped_column(String(512))
    context: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str] = mapped_column(String(128))
    # 暗号化(Fernet)したツール代理トークン。平文は保存しない。ツールサーバへの中継時にcommon/crypto.pyで復号する
    tool_proxy_token_encrypted: Mapped[str] = mapped_column(Text)
    tool_proxy_token_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tool_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    # tbl_tool_serverで承認済みの公開鍵のみ登録できる。公開鍵の更新(chkey)は、onupdate=CASCADEでこの列にも伝播する
    tool_server_public_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("tbl_tool_server.tool_server_public_key", onupdate="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
