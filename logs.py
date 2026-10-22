import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("taverna")

CAMPOS = ("rid", "metodo", "rota", "status", "ms", "detalhe", "evento")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        d = {
            "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nivel": record.levelname,
            "msg": record.getMessage(),
        }
        for c in CAMPOS:
            v = getattr(record, c, None)
            if v is not None:
                d[c] = v
        if record.exc_info:
            d["excecao"] = self.formatException(record.exc_info)
        return json.dumps(d, ensure_ascii=False)


def configurar_logs():
    raiz = logging.getLogger()
    raiz.handlers.clear()
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    raiz.addHandler(h)
    raiz.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logging.getLogger("uvicorn.access").disabled = True   # as requisições são logadas pelo middleware
    for ruidoso in ("httpx", "httpcore", "hpack"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def _rota(request):
    r = request.scope.get("route")
    return getattr(r, "path", None) or request.url.path


class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = uuid.uuid4().hex[:8]
        request.state.request_id = rid
        t0 = time.perf_counter()
        try:
            resposta = await call_next(request)
        except Exception:
            logger.exception("erro_nao_tratado", extra={
                "evento": "erro_nao_tratado", "rid": rid, "metodo": request.method, "rota": _rota(request)})
            resposta = JSONResponse({"detail": f"Erro interno. Código {rid}"}, status_code=500)
        ms = round((time.perf_counter() - t0) * 1000)
        resposta.headers["X-Request-ID"] = rid
        logger.info("requisicao", extra={
            "evento": "requisicao", "rid": rid, "metodo": request.method,
            "rota": _rota(request), "status": resposta.status_code, "ms": ms})
        return resposta


async def tratar_http_exception(request, exc):
    if exc.status_code == 500:
        rid = getattr(request.state, "request_id", "-")
        logger.error("erro_500", extra={
            "evento": "erro_500", "rid": rid, "metodo": request.method,
            "rota": _rota(request), "detalhe": str(exc.detail)[:300]})
        return JSONResponse({"detail": f"Erro interno. Código {rid}"}, status_code=500)
    return await http_exception_handler(request, exc)