"""Rutas de consulta de precios (datos públicos, solo lectura)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ..schemas import ComparacionOut, MercadoOut, PrecioOut, PuntoHistorico, Salud
from ..security import limitar
from ..services import PreciosService
from .deps import servicio_precios

router = APIRouter(prefix="/api", tags=["precios"], dependencies=[Depends(limitar("lectura"))])

_Producto = Query(min_length=1, max_length=200, description="Nombre del producto tal como lo publica el DANE")
_Mercado = Query(default="mayorista", pattern="^[a-z]{1,20}$")


@router.get("/salud", response_model=Salud)
def salud(svc: PreciosService = Depends(servicio_precios)) -> Salud:
    """Comprueba que la base responde y dice cuál es la última semana cargada."""
    return svc.salud()


@router.get("/mercados", response_model=List[MercadoOut])
def mercados(svc: PreciosService = Depends(servicio_precios)) -> List[MercadoOut]:
    return svc.mercados()


@router.get("/productos", response_model=List[str])
def productos(q: str = Query(default="", max_length=60), limite: int = Query(default=20, ge=1, le=60),
              mercado: Optional[str] = Query(default=None, pattern="^[a-z]{1,20}$"),
              svc: PreciosService = Depends(servicio_precios)) -> List[str]:
    """Busca productos por nombre (búsqueda literal: los comodines no tienen efecto)."""
    return svc.buscar_productos(q, limite, mercado)


@router.get("/precios/ultimo", response_model=List[PrecioOut], response_model_exclude_none=True)
def precios_ultimo(producto: Optional[List[str]] = Query(default=None, max_length=40), mercado: str = _Mercado,
                   svc: PreciosService = Depends(servicio_precios)) -> List[PrecioOut]:
    """Último precio (mín, máx, promedio) y variación frente a la semana anterior."""
    if producto and any(len(p) > 200 for p in producto):
        producto = [p[:200] for p in producto]
    return svc.ultimos(producto, mercado)


@router.get("/precios/historico", response_model=List[PuntoHistorico])
def precios_historico(producto: str = _Producto, semanas: int = Query(default=12, ge=1, le=60), mercado: str = _Mercado,
                      svc: PreciosService = Depends(servicio_precios)) -> List[PuntoHistorico]:
    """Serie semanal de un producto (lista vacía si no hay datos en ese mercado)."""
    return svc.historico(producto, semanas, mercado)


@router.get("/precios/comparar", response_model=ComparacionOut)
def precios_comparar(producto: str = _Producto, svc: PreciosService = Depends(servicio_precios)) -> ComparacionOut:
    """Compara el último promedio de la Plaza Minorista con el de la Central Mayorista."""
    return svc.comparar(producto)
