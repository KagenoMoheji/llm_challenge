import os
import inspect
import sys
import time
import traceback
PYPATH = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
MODNAME = os.path.splitext(os.path.basename(inspect.getfile(inspect.currentframe())))[0]

# その他のモジュールやROOTPATHのディレクトリ起点の相対パスでのimport
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from capass_server.common import errors

# service層の業務エラー -> HTTPステータス。isinstanceで上から順に判定するので、サブクラスを先に書く
_STATUS_BY_ERROR: list[tuple[type[errors.ServiceError], int]] = [
    (errors.SignatureError, 401),
    (errors.NotAdminError, 403),
    (errors.ToolServerNotApprovedError, 403),
    (errors.AgentNotApprovedError, 403),
    (errors.ToolServerNotFoundError, 404),
    (errors.AgentNotFoundError, 404),
    (errors.DuplicateToolServerError, 409),
    (errors.DuplicateAgentError, 409),
    (errors.DuplicateAgentToolError, 409),
    (errors.InvalidApprovalStateError, 409),
    (errors.RateLimitExceededError, 429),
]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(errors.ServiceError)
    async def _handle_service_error(_: Request, exc: errors.ServiceError) -> JSONResponse:
        status_code = next((code for cls, code in _STATUS_BY_ERROR if isinstance(exc, cls)), 500)
        headers = None
        if status_code == 401:
            headers = {"WWW-Authenticate": "CaPass-Signature"}
        elif isinstance(exc, errors.RateLimitExceededError):
            headers = {"Retry-After": str(exc.retry_after_sec)}
        return JSONResponse(status_code=status_code, content={"detail": str(exc)}, headers=headers)
