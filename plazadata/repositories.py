"""Capa de acceso a datos. Aquí vive TODO el SQL, siempre con parámetros enlazados (sin concatenar entradas)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine


def fecha_iso(valor: Any) -> str:
    """SQLite devuelve texto y PostgreSQL un ``date``: se unifica a ``AAAA-MM-DD``."""
    return str(valor)[:10]


def escapar_like(texto: str) -> str:
    """Neutraliza los comodines de LIKE (``%`` y ``_``) para que la búsqueda sea literal."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PreciosRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def hay_datos(self) -> bool:
        with self._engine.connect() as con:
            return (con.execute(text("SELECT COUNT(*) FROM precio_semanal")).scalar() or 0) > 0

    def resumen(self) -> tuple[Optional[str], int]:
        with self._engine.connect() as con:
            ultima = con.execute(text("SELECT MAX(fecha) FROM precio_semanal")).scalar()
            filas = con.execute(text("SELECT COUNT(*) FROM precio_semanal")).scalar() or 0
        return (fecha_iso(ultima) if ultima else None, int(filas))

    def resumen_mercado(self, patron: str) -> tuple[Optional[str], int]:
        """Última fecha y número de productos de un mercado."""
        sql = text("""
            SELECT MAX(ps.fecha), COUNT(DISTINCT ps.producto_id)
            FROM precio_semanal ps JOIN mercado me ON me.id = ps.mercado_id WHERE me.nombre LIKE :patron
        """)
        with self._engine.connect() as con:
            fila = con.execute(sql, {"patron": patron}).fetchone()
        if not fila or not fila[0]:
            return (None, 0)
        return (fecha_iso(fila[0]), int(fila[1]))

    def buscar_productos(self, consulta: str, limite: int, patron_mercado: Optional[str] = None) -> list[str]:
        params: dict[str, Any] = {"q": f"%{escapar_like(consulta.lower())}%", "n": limite}
        sql = "SELECT DISTINCT p.nombre FROM producto p"
        if patron_mercado:
            params["patron"] = patron_mercado
            sql += (" JOIN precio_semanal ps ON ps.producto_id = p.id"
                    " JOIN mercado me ON me.id = ps.mercado_id AND me.nombre LIKE :patron")
        sql += " WHERE LOWER(p.nombre) LIKE :q ESCAPE '\\' ORDER BY p.nombre LIMIT :n"
        with self._engine.connect() as con:
            return [f[0] for f in con.execute(text(sql), params).fetchall()]

    def ultimos_dos(self, productos: Sequence[str], patron_mercado: str) -> dict[str, list[tuple[str, float, float, float]]]:
        """Las dos semanas más recientes de cada producto, en UNA consulta (evita el problema N+1).

        Devuelve ``{producto: [(fecha, mínimo, máximo, promedio), ...]}`` de más reciente a más antigua.
        """
        if not productos:
            return {}
        sql = text("""
            SELECT nombre, fecha, precio_minimo, precio_maximo, precio_promedio FROM (
                SELECT p.nombre AS nombre, ps.fecha AS fecha, ps.precio_minimo AS precio_minimo,
                       ps.precio_maximo AS precio_maximo, ps.precio_promedio AS precio_promedio,
                       ROW_NUMBER() OVER (PARTITION BY ps.producto_id ORDER BY ps.fecha DESC) AS orden
                FROM precio_semanal ps
                JOIN producto p ON p.id = ps.producto_id
                JOIN mercado me ON me.id = ps.mercado_id
                WHERE p.nombre IN :nombres AND me.nombre LIKE :patron
            ) t WHERE orden <= 2 ORDER BY nombre, fecha DESC
        """).bindparams(bindparam("nombres", expanding=True))
        salida: dict[str, list[tuple[str, float, float, float]]] = {}
        with self._engine.connect() as con:
            for nombre, fecha, minimo, maximo, promedio in con.execute(sql, {"nombres": list(productos), "patron": patron_mercado}):
                salida.setdefault(nombre, []).append((fecha_iso(fecha), float(minimo), float(maximo), float(promedio)))
        return salida

    def historico(self, producto: str, patron_mercado: str, semanas: int) -> list[tuple[str, float, float, float]]:
        """Últimas ``semanas`` con dato, en orden cronológico: ``(fecha, promedio, mínimo, máximo)``."""
        sql = text("""
            SELECT ps.fecha, ps.precio_promedio, ps.precio_minimo, ps.precio_maximo
            FROM precio_semanal ps JOIN producto p ON p.id = ps.producto_id JOIN mercado me ON me.id = ps.mercado_id
            WHERE p.nombre = :producto AND me.nombre LIKE :patron ORDER BY ps.fecha DESC LIMIT :semanas
        """)
        with self._engine.connect() as con:
            filas = con.execute(sql, {"producto": producto, "patron": patron_mercado, "semanas": semanas}).fetchall()
        return [(fecha_iso(f[0]), float(f[1]), float(f[2]), float(f[3])) for f in reversed(filas)]


class UsoRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def insertar_evento(self, cliente: str, evento: str, detalle: Optional[str], creado_en: datetime) -> None:
        with self._engine.begin() as con:
            con.execute(text("INSERT INTO evento_uso (cliente, evento, detalle, creado_en) VALUES (:c, :e, :d, :t)"),
                        {"c": cliente, "e": evento, "d": detalle, "t": creado_en})

    def insertar_comentario(self, cliente: str, pantalla: Optional[str], texto: str, creado_en: datetime) -> None:
        with self._engine.begin() as con:
            con.execute(text("INSERT INTO comentario (cliente, pantalla, texto, creado_en) VALUES (:c, :p, :x, :t)"),
                        {"c": cliente, "p": pantalla, "x": texto, "t": creado_en})

    def eventos(self) -> list[tuple[str, str, Any]]:
        with self._engine.connect() as con:
            return [(f[0], f[1], f[2]) for f in con.execute(text("SELECT cliente, evento, creado_en FROM evento_uso ORDER BY creado_en"))]

    def comentarios(self, limite: int = 200) -> list[tuple[Optional[str], str, Any]]:
        with self._engine.connect() as con:
            return [(f[0], f[1], f[2]) for f in con.execute(
                text("SELECT pantalla, texto, creado_en FROM comentario ORDER BY creado_en DESC LIMIT :n"), {"n": limite})]
