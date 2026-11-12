"""Acceso a la base de datos: motor, definición de tablas y creación del esquema.

Las tablas se declaran con SQLAlchemy Core, así el mismo esquema sirve para SQLite (local) y PostgreSQL (nube).
"""
from __future__ import annotations

from sqlalchemy import (Column, Date, DateTime, ForeignKey, Index, Integer, MetaData, Numeric,
                        PrimaryKeyConstraint, Table, Text, create_engine)
from sqlalchemy.engine import Engine

metadata = MetaData()

mercado = Table(
    "mercado", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nombre", Text, nullable=False, unique=True),
)
producto = Table(
    "producto", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nombre", Text, nullable=False, unique=True),
)
precio_semanal = Table(
    "precio_semanal", metadata,
    Column("fecha", Date, nullable=False),
    Column("producto_id", Integer, ForeignKey("producto.id"), nullable=False),
    Column("mercado_id", Integer, ForeignKey("mercado.id"), nullable=False),
    Column("precio_promedio", Numeric, nullable=False),
    Column("precio_minimo", Numeric, nullable=False),
    Column("precio_maximo", Numeric, nullable=False),
    Column("fuente", Text, nullable=False),
    Column("cargado_en", DateTime, nullable=False),
    PrimaryKeyConstraint("fecha", "producto_id", "mercado_id"),
    Index("ix_precio_producto_mercado_fecha", "producto_id", "mercado_id", "fecha"),
)
evento_uso = Table(
    "evento_uso", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cliente", Text, nullable=False),
    Column("evento", Text, nullable=False),
    Column("detalle", Text),
    Column("creado_en", DateTime, nullable=False),
    Index("ix_evento_creado_en", "creado_en"),
)
comentario = Table(
    "comentario", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cliente", Text, nullable=False),
    Column("pantalla", Text),
    Column("texto", Text, nullable=False),
    Column("creado_en", DateTime, nullable=False),
)


def crear_motor(url: str) -> Engine:
    """Crea el motor. ``pool_pre_ping`` descarta conexiones caídas (útil con bases en la nube que cierran inactivas)."""
    return create_engine(url, pool_pre_ping=True)


def inicializar_esquema(engine: Engine) -> None:
    """Crea las tablas e índices que falten. Es seguro llamarlo en cada arranque."""
    metadata.create_all(engine)
    for tabla in metadata.tables.values():   # índices añadidos después a tablas que ya existían
        for indice in tabla.indexes:
            indice.create(engine, checkfirst=True)
