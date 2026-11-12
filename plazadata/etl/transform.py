"""Lectura y validación de los datos. Los datos externos no se dan por buenos: se validan antes de cargarlos."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Union

import pandas as pd

log = logging.getLogger("plazadata.etl")

COLUMNAS: tuple[str, ...] = ("FECHA", "FUENTE", "ARTÍCULO", "PROMEDIO", "MÍNIMO", "MÁXIMO")
PRECIO_MAXIMO_RAZONABLE: float = 5_000_000     # COP por unidad de venta; por encima se considera un dato corrupto
LARGO_MAXIMO_NOMBRE: int = 200

# El Excel que exporta el tablero del DANE no trae estilo por defecto; el aviso de openpyxl es inofensivo.
warnings.filterwarnings("ignore", message="Workbook contains no default style")


class DatosInvalidos(ValueError):
    """El archivo o la respuesta no tiene la estructura esperada."""


@dataclass
class InformeCalidad:
    """Qué se descartó y por qué (queda en los registros para auditoría del dato)."""

    leidas: int = 0
    validas: int = 0
    sin_fecha: int = 0
    sin_precio: int = 0
    precios_inconsistentes: int = 0
    fuera_de_rango: int = 0
    fechas_futuras: int = 0
    duplicadas: int = 0
    semanas: int = 0
    huecos: list[tuple[date, date]] = field(default_factory=list)


def leer_archivo(ruta: Union[str, Path]) -> pd.DataFrame:
    """Lee un CSV o Excel con las columnas del tablero del DANE."""
    ruta = Path(ruta)
    df = pd.read_csv(ruta) if ruta.suffix.lower() == ".csv" else pd.read_excel(ruta)
    return df


def transformar(df: pd.DataFrame, hoy: date | None = None) -> tuple[pd.DataFrame, InformeCalidad]:
    """Limpia y valida. Devuelve los datos válidos y un informe de lo descartado."""
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise DatosInvalidos(f"Faltan columnas: {faltan}")
    inf = InformeCalidad(leidas=len(df))
    df = df[list(COLUMNAS)].copy()

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    inf.sin_fecha = int(df["FECHA"].isna().sum())           # incluye las filas de pie de página del export
    df = df.dropna(subset=["FECHA"]).copy()

    for col in ("PROMEDIO", "MÍNIMO", "MÁXIMO"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    inf.sin_precio = int(df[["PROMEDIO", "MÍNIMO", "MÁXIMO"]].isna().any(axis=1).sum())
    df = df.dropna(subset=["PROMEDIO", "MÍNIMO", "MÁXIMO"]).copy()

    df["ARTÍCULO"] = df["ARTÍCULO"].astype(str).str.strip().str.slice(0, LARGO_MAXIMO_NOMBRE)
    df["FUENTE"] = df["FUENTE"].astype(str).str.strip().str.slice(0, LARGO_MAXIMO_NOMBRE)
    df = df[(df["ARTÍCULO"] != "") & (df["FUENTE"] != "")]

    inconsistentes = (df["PROMEDIO"] <= 0) | (df["MÍNIMO"] > df["PROMEDIO"]) | (df["PROMEDIO"] > df["MÁXIMO"])
    inf.precios_inconsistentes = int(inconsistentes.sum())
    df = df[~inconsistentes]

    fuera = df["MÁXIMO"] > PRECIO_MAXIMO_RAZONABLE
    inf.fuera_de_rango = int(fuera.sum())
    df = df[~fuera]

    limite = pd.Timestamp((hoy or date.today()) + timedelta(days=7))
    futuras = df["FECHA"] > limite
    inf.fechas_futuras = int(futuras.sum())
    df = df[~futuras]

    antes = len(df)
    df = df.drop_duplicates(subset=["FECHA", "FUENTE", "ARTÍCULO"], keep="last")
    inf.duplicadas = antes - len(df)

    fechas = sorted(pd.to_datetime(df["FECHA"].unique()))     # Timestamps: el cálculo de días funciona igual en pandas 2 y 3
    inf.semanas = len(fechas)
    inf.huecos = [(a.date(), b.date()) for a, b in zip(fechas, fechas[1:]) if (b - a).days != 7]
    inf.validas = len(df)

    descartadas = inf.leidas - inf.validas
    log.info("etl_transformado", extra={"leidas": inf.leidas, "validas": inf.validas, "descartadas": descartadas, "semanas": inf.semanas})
    if inf.precios_inconsistentes or inf.fuera_de_rango or inf.fechas_futuras:
        log.warning("etl_filas_descartadas", extra={"inconsistentes": inf.precios_inconsistentes,
                                                    "fuera_de_rango": inf.fuera_de_rango, "fechas_futuras": inf.fechas_futuras})
    if inf.huecos:
        log.warning("etl_semanas_faltantes", extra={"huecos": [f"{a} → {b}" for a, b in inf.huecos]})
    return df.reset_index(drop=True), inf
