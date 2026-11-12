"""Registro estructurado en JSON con identificador de solicitud, para trazabilidad y auditoría."""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

#: Identificador de la solicitud en curso (se propaga a todos los registros de esa solicitud).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVADOS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Una línea JSON por registro. Los campos extra (``extra={...}``) se incluyen tal cual."""

    def format(self, record: logging.LogRecord) -> str:
        datos: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for clave, valor in record.__dict__.items():
            if clave not in _RESERVADOS and not clave.startswith("_"):
                datos[clave] = valor
        if record.exc_info:
            datos["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False, default=str)


def configurar_logging(nivel: str = "INFO") -> None:
    """Configura el registro raíz con salida JSON (idempotente)."""
    raiz = logging.getLogger()
    for h in list(raiz.handlers):
        if getattr(h, "_plazadata", False):
            raiz.removeHandler(h)
    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(JsonFormatter())
    manejador._plazadata = True  # type: ignore[attr-defined]
    raiz.addHandler(manejador)
    raiz.setLevel(getattr(logging, nivel, logging.INFO))
