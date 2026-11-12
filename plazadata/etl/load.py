"""Carga idempotente a la base: repetirla actualiza las filas existentes y no las duplica."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..db import inicializar_esquema

log = logging.getLogger("plazadata.etl")

_UPSERT = text("""
    INSERT INTO precio_semanal
        (fecha, producto_id, mercado_id, precio_promedio, precio_minimo, precio_maximo, fuente, cargado_en)
    VALUES (:fecha, :p, :m, :prom, :min, :max, :f, :t)
    ON CONFLICT (fecha, producto_id, mercado_id) DO UPDATE SET
        precio_promedio = excluded.precio_promedio,
        precio_minimo   = excluded.precio_minimo,
        precio_maximo   = excluded.precio_maximo,
        cargado_en      = excluded.cargado_en
""")


def cargar(engine: Engine, df: pd.DataFrame, origen: str = "DANE-SIPSA") -> int:
    """Inserta o actualiza los precios en una sola transacción (todo o nada). Devuelve las filas cargadas."""
    inicializar_esquema(engine)
    if df.empty:
        return 0
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.begin() as con:
        for nombre in df["FUENTE"].unique():
            con.execute(text("INSERT INTO mercado (nombre) VALUES (:n) ON CONFLICT (nombre) DO NOTHING"), {"n": str(nombre)})
        for nombre in df["ARTÍCULO"].unique():
            con.execute(text("INSERT INTO producto (nombre) VALUES (:n) ON CONFLICT (nombre) DO NOTHING"), {"n": str(nombre)})
        mercados = {f[1]: f[0] for f in con.execute(text("SELECT id, nombre FROM mercado"))}
        productos = {f[1]: f[0] for f in con.execute(text("SELECT id, nombre FROM producto"))}
        filas = [{"fecha": r.FECHA.date(), "p": productos[r.ARTÍCULO], "m": mercados[r.FUENTE], "prom": float(r.PROMEDIO),
                  "min": float(r.MÍNIMO), "max": float(r.MÁXIMO), "f": origen, "t": ahora} for r in df.itertuples()]
        con.execute(_UPSERT, filas)
    log.info("etl_cargado", extra={"filas": len(filas)})
    return len(filas)
