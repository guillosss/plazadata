"""Rutas de medición de uso anónima y comentarios (escritura, con límite de ritmo estricto)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..schemas import ComentarioIn, EventoIn
from ..security import limitar
from ..services import UsoService
from .deps import servicio_uso

router = APIRouter(prefix="/api", tags=["uso"])


@router.post("/evento", status_code=204, dependencies=[Depends(limitar("eventos"))])
def registrar_evento(evento: EventoIn, svc: UsoService = Depends(servicio_uso)) -> Response:
    svc.registrar_evento(evento)
    return Response(status_code=204)


@router.post("/comentario", status_code=204, dependencies=[Depends(limitar("comentarios"))])
def registrar_comentario(comentario: ComentarioIn, svc: UsoService = Depends(servicio_uso)) -> Response:
    svc.registrar_comentario(comentario)
    return Response(status_code=204)
