"""Manejo de errores predecible: cada tipo de fallo tiene una respuesta definida y queda registrado.

Nunca se devuelve al cliente una traza ni un mensaje interno; se entrega un identificador para rastrear el caso.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from .domain import ErrorDominio
from .logging_conf import request_id_var

log = logging.getLogger("plazadata.errores")


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorDominio)
    async def _dominio(_request: Request, exc: ErrorDominio) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Se informa qué campo falló, sin devolver el valor recibido.
        errores = [{"campo": ".".join(str(p) for p in e.get("loc", [])[1:]), "mensaje": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse({"detail": "Datos de entrada no válidos.", "errores": errores}, status_code=422)

    @app.exception_handler(OperationalError)
    @app.exception_handler(DBAPIError)
    async def _base_de_datos(_request: Request, exc: Exception) -> JSONResponse:
        # Degradación elegante: la base no responde → 503 con Retry-After (el panel muestra los últimos datos guardados).
        log.error("base_de_datos_no_disponible", exc_info=exc)
        return JSONResponse({"detail": "El servicio no está disponible temporalmente.", "request_id": request_id_var.get()},
                            status_code=503, headers={"Retry-After": "30"})

    @app.exception_handler(Exception)
    async def _inesperado(_request: Request, exc: Exception) -> JSONResponse:
        log.error("error_inesperado", exc_info=exc)
        return JSONResponse({"detail": "Error interno.", "request_id": request_id_var.get()}, status_code=500)
