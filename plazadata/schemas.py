"""Contratos de entrada y salida de la API (Pydantic). Toda entrada externa se valida aquí."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PATRON_CLIENTE = r"^[A-Za-z0-9-]{8,64}$"


def limpiar_texto(valor: str, permitir_saltos: bool = False) -> str:
    """Quita caracteres de control e invisibles (que podrían ocultar contenido o romper registros) y normaliza."""
    valor = unicodedata.normalize("NFC", valor)
    permitidos = {"\n"} if permitir_saltos else set()
    limpio = "".join(c for c in valor if c in permitidos or unicodedata.category(c)[0] != "C")
    return re.sub(r"[ \t]+", " ", limpio).strip()


class _Entrada(BaseModel):
    # Rechaza campos desconocidos: el cliente no puede colar datos que no esperamos.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EventoIn(_Entrada):
    cliente: str = Field(pattern=_PATRON_CLIENTE, description="Identificador aleatorio del navegador")
    evento: str = Field(min_length=1, max_length=40, pattern=r"^[a-z_]+$")
    detalle: Optional[str] = Field(default=None, max_length=200)

    @field_validator("detalle")
    @classmethod
    def _limpiar_detalle(cls, v: Optional[str]) -> Optional[str]:
        return (limpiar_texto(v) or None) if v is not None else None


class ComentarioIn(_Entrada):
    cliente: str = Field(pattern=_PATRON_CLIENTE)
    pantalla: Optional[str] = Field(default=None, max_length=30, pattern=r"^[a-z_]+$")
    texto: str = Field(min_length=1, max_length=1000)

    @field_validator("texto")
    @classmethod
    def _limpiar_comentario(cls, v: str) -> str:
        limpio = limpiar_texto(v, permitir_saltos=True)
        if not limpio:
            raise ValueError("El comentario está vacío")
        return limpio


class Salud(BaseModel):
    estado: str
    ultima_fecha: Optional[str]
    filas: int


class MercadoOut(BaseModel):
    clave: str
    etiqueta: str
    ultima_fecha: str
    productos: int


class PrecioOut(BaseModel):
    producto: str
    disponible: bool
    mercado: str
    unidad: str
    unidad_codigo: str
    fecha: Optional[str] = None
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    promedio: Optional[float] = None
    promedio_anterior: Optional[float] = None
    fecha_anterior: Optional[str] = None
    variacion_pct: Optional[float] = None
    desactualizado: Optional[bool] = None


class PuntoHistorico(BaseModel):
    fecha: str
    promedio: float
    minimo: float
    maximo: float


class PrecioMercado(BaseModel):
    promedio: float
    fecha: str


class ComparacionOut(BaseModel):
    producto: str
    unidad: str
    mayorista: Optional[PrecioMercado]
    minorista: Optional[PrecioMercado]
    comparable: bool
    diferencia_pct: Optional[float]


class SemanaUso(BaseModel):
    semana_desde: str
    usuarios: int
    aperturas: int


class EventoConteo(BaseModel):
    evento: str
    n: int


class UsuarioUso(BaseModel):
    cliente: str
    primer_uso: str
    ultimo_uso: str
    dias_activos: int
    semanas_activas: int
    eventos: int


class ComentarioOut(BaseModel):
    fecha: str
    pantalla: Optional[str]
    texto: str


class ResumenUso(BaseModel):
    usuarios_unicos: int
    eventos_total: int
    por_semana: list[SemanaUso]
    por_evento: list[EventoConteo]
    por_usuario: list[UsuarioUso]
    comentarios: list[ComentarioOut]
    nota: str
