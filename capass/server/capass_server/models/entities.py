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
from capass_server.common.globals import (
    AGENT_ID_MAX_LEN,
    EMAIL_MAX_LEN,
    EXEC_URL_MAX_LEN,
    NONCE_MAX_LEN,
    PUBLIC_KEY_MAX_LEN,
    STATUS_MAX_LEN,
    TOOL_ENDPOINT_MAX_LEN,
    TOOL_SERVER_NAME_MAX_LEN,
)


class ApprovalStatus(str, enum.Enum):
    """ツールサーバ/AIエージェント(公開鍵)の承認ステータス。"""

    PENDING = "pending"  # 承認待ち(初回登録直後)
    APPROVED = "approved"  # 承認済み(CaPassサーバ管理者が承認)
    REVOKED = "revoked"  # 却下・失効


class TblAdmin(Base):
    """CaPassサーバ管理者(公開鍵)。承認系API(approve)は、ここに登録された有効な公開鍵の署名のみ受け付ける。
    管理者の追加・無効化は、APIを設けず、管理者がSQLクライアントでこのテーブルを直接更新して行う(アプリの再起動は不要)。"""

    __tablename__ = "tbl_admin"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_email: Mapped[str] = mapped_column(String(EMAIL_MAX_LEN), unique=True)  # 承認時に、承認者メアド(approver_email)として記録される
    admin_public_key: Mapped[str] = mapped_column(String(PUBLIC_KEY_MAX_LEN), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # Falseにすると、承認できなくなる(レコードは残す)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TblToolServer(Base):
    """ツールサーバ(公開鍵)の承認管理レコード。CaPassサーバ管理者が承認した公開鍵のみ、AIエージェントへのツール追加(addtool)が許可される。"""

    __tablename__ = "tbl_tool_server"

    id: Mapped[int] = mapped_column(primary_key=True)  # APIでは toolserver_id として公開する
    tool_server_public_key: Mapped[str] = mapped_column(String(PUBLIC_KEY_MAX_LEN), unique=True)
    tool_server_name: Mapped[str] = mapped_column(String(TOOL_SERVER_NAME_MAX_LEN))  # 管理者が承認時に識別するための名称
    # ツール実行の依頼先URL。CaPassサーバは、ここへツール代理トークン付きでPOSTする。管理者が承認時にURLを確認する
    exec_url: Mapped[str] = mapped_column(String(EXEC_URL_MAX_LEN))
    applicant_email: Mapped[str] = mapped_column(String(EMAIL_MAX_LEN))  # 申請者メアド(申請者の自己申告。管理者が確認の連絡をするために使う)
    approver_email: Mapped[str | None] = mapped_column(String(EMAIL_MAX_LEN), default=None)  # 承認者メアド(承認した管理者のadmin_email)
    status: Mapped[str] = mapped_column(String(STATUS_MAX_LEN), default=ApprovalStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TblAgent(Base):
    """AIエージェント(公開鍵)の承認管理レコード。CaPassサーバ管理者が承認したAIエージェントのみ、ツールを追加(addtool)できる。"""

    __tablename__ = "tbl_agent"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_MAX_LEN), unique=True)  # AIエージェント提供者が決める識別子
    agent_public_key: Mapped[str] = mapped_column(String(PUBLIC_KEY_MAX_LEN), unique=True)
    applicant_email: Mapped[str] = mapped_column(String(EMAIL_MAX_LEN))  # 申請者メアド(申請者の自己申告。管理者が確認の連絡をするために使う)
    approver_email: Mapped[str | None] = mapped_column(String(EMAIL_MAX_LEN), default=None)  # 承認者メアド(承認した管理者のadmin_email)
    status: Mapped[str] = mapped_column(String(STATUS_MAX_LEN), default=ApprovalStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TblAgentTool(Base):
    """AIエージェントとツールの紐づけレコード: [ツールエンドポイント/コンテキスト/ツール代理トークン/AIエージェント情報/ツール代理トークン更新日時/ツール利用日時/ロック状況/ツールサーバ公開鍵]"""

    __tablename__ = "tbl_agent_tool"
    __table_args__ = (
        UniqueConstraint("tool_endpoint", "agent_id", name="uq_tbl_agent_tool_endpoint_agent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_endpoint: Mapped[str] = mapped_column(String(TOOL_ENDPOINT_MAX_LEN))
    context: Mapped[str] = mapped_column(Text)
    # tbl_agentで承認済みのAIエージェントのみ登録できる
    agent_id: Mapped[str] = mapped_column(
        String(AGENT_ID_MAX_LEN), ForeignKey("tbl_agent.agent_id", onupdate="CASCADE"), index=True
    )
    # 暗号化(Fernet)したツール代理トークン。平文は保存しない。ツールサーバへの中継時にcommon/crypto.pyで復号する
    tool_proxy_token_encrypted: Mapped[str] = mapped_column(Text)
    tool_proxy_token_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tool_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    # tbl_tool_serverで承認済みの公開鍵のみ登録できる。公開鍵の更新(chkey)は、onupdate=CASCADEでこの列にも伝播する
    tool_server_public_key: Mapped[str] = mapped_column(
        String(PUBLIC_KEY_MAX_LEN), ForeignKey("tbl_tool_server.tool_server_public_key", onupdate="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TblRequestNonce(Base):
    """署名付きリクエストのnonce(リプレイ防止)。同じ[agent_id, nonce]のリクエストは、2回目以降を拒否する。
    nonceは、署名時刻が許容範囲を過ぎたら(expires_at)、使われても拒否できる(署名時刻で拒否される)ので、期限切れのレコードは削除する。"""

    __tablename__ = "tbl_request_nonce"
    __table_args__ = (
        UniqueConstraint("agent_id", "nonce", name="uq_tbl_request_nonce_agent_nonce"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_MAX_LEN))
    nonce: Mapped[str] = mapped_column(String(NONCE_MAX_LEN))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
