import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from capass_server.common.db import Base


class ToolRegistration(Base):
    """ツール登録レコード: [ツールエンドポイント/コンテキスト/ツール代理トークン/AIエージェント情報/ツール代理トークン更新日時/ツール利用日時/ロック状況/ツールサーバ公開鍵]"""

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
    tool_server_public_key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
