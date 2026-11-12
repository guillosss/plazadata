"""Proveedores de dependencias (inversión de control): las rutas reciben servicios, no los construyen."""
from __future__ import annotations

from fastapi import Request

from ..services import PreciosService, UsoService


def servicio_precios(request: Request) -> PreciosService:
    return request.app.state.precios


def servicio_uso(request: Request) -> UsoService:
    return request.app.state.uso
