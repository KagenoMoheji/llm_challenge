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
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from capass_server.common.db import Base
from capass_server.common.globals import (
    AGENT_ID_MAX_LEN,
    EMAIL_MAX_LEN,
    EXEC_URL_MAX_LEN,
    NONCE_MAX_LEN,
    NONCE_SCOPE_MAX_LEN,
    PUBLIC_KEY_MAX_LEN,
    STATUS_MAX_LEN,
    TOOL_ENDPOINT_MAX_LEN,
    TOOL_SERVER_NAME_MAX_LEN,
)


class ApprovalStatus(str, enum.Enum):
    """承認ステータス(ツールサーバ、AIエージェント、AIエージェントへのツールの割り当て)。"""

    PENDING = "pending"  # 承認待ち(申請直後)
    APPROVED = "approved"  # 承認済み(有効)。ツールサーバでは、現在使われている(アクティブな)ツールサーバ
    REVOKED = "revoked"  # 却下・失効
    # ---- ツールサーバのリプレース用 ----
    RESERVED = "reserved"  # 管理者が事前に承認した、後継のツールサーバ(まだ使われていない)。期限(status_expires_at)がある
    STANDBY = "standby"  # 切り替え後の、旧ツールサーバ(待機中)。期限(status_expires_at)まで、切り戻しできる


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
    """ツールサーバ(実行URLと公開鍵の組)の承認管理レコード。1行が、1台(1つの送り先)のツールサーバ。
    ツール(tbl_tool)は、このレコードのidを持つ。サーバの置き換えでは、後継のレコードを事前に承認(RESERVED)しておき、
    切り替え時に、ツールの持つidを付け替える(旧はSTANDBYになり、期限まで切り戻せる)。"""

    __tablename__ = "tbl_tool_server"

    id: Mapped[int] = mapped_column(primary_key=True)  # APIでは toolserver_id として公開する
    tool_server_public_key: Mapped[str] = mapped_column(String(PUBLIC_KEY_MAX_LEN), unique=True)
    tool_server_name: Mapped[str] = mapped_column(String(TOOL_SERVER_NAME_MAX_LEN))  # 管理者が承認時に識別するための名称
    # ツール実行の依頼先URL。CaPassサーバは、ここへツール代理トークン付きでPOSTする。管理者が承認時にURLを確認する
    exec_url: Mapped[str] = mapped_column(String(EXEC_URL_MAX_LEN))
    applicant_email: Mapped[str] = mapped_column(String(EMAIL_MAX_LEN))  # 申請者メアド(申請者の自己申告。管理者が確認の連絡をするために使う)
    approver_email: Mapped[str | None] = mapped_column(String(EMAIL_MAX_LEN), default=None)  # 承認者メアド(承認した管理者のadmin_email)
    status: Mapped[str] = mapped_column(String(STATUS_MAX_LEN), default=ApprovalStatus.PENDING.value)
    # 後継として予約(reserve)されたレコードが、置き換える対象(旧ツールサーバ)のid。管理者が承認するのは、この「旧→新」の遷移
    replaces_tool_server_id: Mapped[int | None] = mapped_column(ForeignKey("tbl_tool_server.id"), default=None, index=True)
    # RESERVED(予約の期限)、STANDBY(切り戻しできる期限)のときの期限。期限を過ぎたら、そのステータスは無効(使えない)
    status_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TblAgent(Base):
    """AIエージェント(公開鍵)の承認管理レコード。CaPassサーバ管理者が承認したAIエージェントのみ、ツールの割り当てを申請(grant)・利用できる。"""

    __tablename__ = "tbl_agent"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_MAX_LEN), unique=True)  # AIエージェント提供者が決める識別子
    agent_public_key: Mapped[str] = mapped_column(String(PUBLIC_KEY_MAX_LEN), unique=True)
    applicant_email: Mapped[str] = mapped_column(String(EMAIL_MAX_LEN))  # 申請者メアド(申請者の自己申告。管理者が確認の連絡をするために使う)
    approver_email: Mapped[str | None] = mapped_column(String(EMAIL_MAX_LEN), default=None)  # 承認者メアド(承認した管理者のadmin_email)
    status: Mapped[str] = mapped_column(String(STATUS_MAX_LEN), default=ApprovalStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TblTool(Base):
    """ツール(ロール単位のツールエンドポイント)。リソース(SaaS/DB)側のロール(スコープ/GRANT)1つに、ツール代理トークン1つが対応する。
    複数のAIエージェントに割り当てられる(tbl_agent_tool)。トークンを更新(chtkn)すると、割り当てられた全てのAIエージェントに反映される。"""

    __tablename__ = "tbl_tool"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_endpoint: Mapped[str] = mapped_column(String(TOOL_ENDPOINT_MAX_LEN), unique=True)  # 全体で一意
    context: Mapped[str] = mapped_column(Text)
    # ツールのparamsのスキーマ(JSON Schema)。AIエージェントへの一覧に含め、実行時にCaPassサーバがparamsを検証する
    params_schema: Mapped[dict] = mapped_column(JSON)
    # このツールを提供するツールサーバ(の、いまの送り先)。ツールサーバのリプレースで、付け替えられる
    tool_server_id: Mapped[int] = mapped_column(ForeignKey("tbl_tool_server.id"), index=True)
    # 暗号化(Fernet)したツール代理トークン。平文は保存しない。ツールサーバへの中継時にcommon/crypto.pyで復号する
    tool_proxy_token_encrypted: Mapped[str] = mapped_column(Text)
    tool_proxy_token_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)  # トークンの更新が止まったときなどのロック。ツールを使う全てのAIエージェントに効く
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TblAgentTool(Base):
    """AIエージェントへのツールの割り当て(1つのツールを、複数のAIエージェントに割り当てられる)。
    申請(grant)→承認(approve)で有効になり、取り消し(revoke)で無効になる。"""

    __tablename__ = "tbl_agent_tool"
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_tbl_agent_tool_agent_tool"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(AGENT_ID_MAX_LEN), ForeignKey("tbl_agent.agent_id", onupdate="CASCADE"), index=True
    )
    tool_id: Mapped[int] = mapped_column(ForeignKey("tbl_tool.id"), index=True)
    status: Mapped[str] = mapped_column(String(STATUS_MAX_LEN), default=ApprovalStatus.PENDING.value)
    applicant_email: Mapped[str] = mapped_column(String(EMAIL_MAX_LEN))  # 申請者メアド(自己申告)。将来は、WebUIでログインした利用者になる
    approver_email: Mapped[str | None] = mapped_column(String(EMAIL_MAX_LEN), default=None)  # 承認者メアド。将来は、利用者の上司などになる
    locked: Mapped[bool] = mapped_column(Boolean, default=False)  # このAIエージェントだけのロック(利用実績が古い割り当てを、ツールサーバが止める、など)
    tool_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)  # このAIエージェントが、最後に使った日時
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TblRequestNonce(Base):
    """署名付きリクエストのnonce(リプレイ防止)。同じ[scope, nonce]のリクエストは、2回目以降を拒否する。
    scopeは、nonceを区切る単位(AIエージェントのリクエストは "agent:<agent_id>"、ツールのトークン更新は "tool:<tool_endpoint>")。
    nonceは、署名時刻が許容範囲を過ぎたら(expires_at)、使われても拒否できる(署名時刻で拒否される)ので、期限切れのレコードは削除する。"""

    __tablename__ = "tbl_request_nonce"
    __table_args__ = (
        UniqueConstraint("scope", "nonce", name="uq_tbl_request_nonce_scope_nonce"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(NONCE_SCOPE_MAX_LEN))
    nonce: Mapped[str] = mapped_column(String(NONCE_MAX_LEN))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
