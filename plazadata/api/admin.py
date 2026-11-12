"""Resumen privado para el autor. Requiere la cabecera ``X-Admin-Key``."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..schemas import ResumenUso
from ..security import requerir_admin
from ..services import UsoService
from .deps import servicio_uso

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(requerir_admin)])


@router.get("/resumen", response_model=ResumenUso)
def resumen(svc: UsoService = Depends(servicio_uso)) -> ResumenUso:
    """Usuarios por semana (indicador «uso semanal por piloto»), eventos y comentarios."""
    return svc.resumen()
