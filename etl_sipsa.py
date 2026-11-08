"""
ETL mínimo de PlazaData: precios mayoristas SIPSA-DANE -> base de datos.

Uso:
    pip install pandas openpyxl sqlalchemy psycopg2-binary
    # Prueba local (crea sipsa.db con SQLite):
    python etl_sipsa.py data.xlsx
    # Contra PostgreSQL (por ejemplo en Render):
    set DATABASE_URL=postgresql://usuario:clave@host/nombre_bd      (Windows)
    export DATABASE_URL=postgresql://usuario:clave@host/nombre_bd   (Linux/Mac)
    python etl_sipsa.py data.xlsx

Qué hace:
  1. Extrae: lee el Excel exportado del tablero de precios mayoristas del DANE.
  2. Transforma: limpia filas que no son datos, normaliza nombres, valida precios.
  3. Carga: inserta en las tablas mercado, producto y precio_semanal (se puede
     repetir sin duplicar: si la fila ya existe, la actualiza).

Nota: los datos del tablero son SEMANALES, por eso la tabla se llama
precio_semanal (en el informe se llamaba precio_diario).
"""
import logging
import os
import sys
import warnings
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import bindparam, create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("etl_sipsa")

# El Excel que exporta el tablero del DANE no trae estilo por defecto; el aviso es inofensivo.
warnings.filterwarnings("ignore", message="Workbook contains no default style")

COLUMNAS = ["FECHA", "FUENTE", "ARTÍCULO", "PROMEDIO", "MÍNIMO", "MÁXIMO"]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mercado (
    id      {id_col},
    nombre  TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS producto (
    id      {id_col},
    nombre  TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS precio_semanal (
    fecha           DATE    NOT NULL,
    producto_id     INTEGER NOT NULL REFERENCES producto(id),
    mercado_id      INTEGER NOT NULL REFERENCES mercado(id),
    precio_promedio NUMERIC NOT NULL,
    precio_minimo   NUMERIC NOT NULL,
    precio_maximo   NUMERIC NOT NULL,
    fuente          TEXT    NOT NULL,
    cargado_en      TIMESTAMP NOT NULL,
    PRIMARY KEY (fecha, producto_id, mercado_id)
);
"""


def conectar():
    url = os.getenv("DATABASE_URL", "sqlite:///sipsa.db")
    # Render entrega "postgres://" o "postgresql://"; SQLAlchemy necesita el driver.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url)


def extraer(ruta):
    log.info("Leyendo %s", ruta)
    df = pd.read_excel(ruta)
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas en el Excel: {faltan}")
    return df[COLUMNAS].copy()


def transformar(df):
    n_inicial = len(df)
    # El export trae al final filas de texto con los filtros aplicados: no son datos.
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df.dropna(subset=["FECHA"]).copy()
    for col in ["PROMEDIO", "MÍNIMO", "MÁXIMO"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ARTÍCULO"] = df["ARTÍCULO"].astype(str).str.strip()
    df["FUENTE"] = df["FUENTE"].astype(str).str.strip()
    df = df.dropna(subset=["PROMEDIO", "MÍNIMO", "MÁXIMO"]).copy()

    # Validaciones de calidad: precios positivos y mín <= promedio <= máx.
    invalidas = (
        (df["PROMEDIO"] <= 0)
        | (df["MÍNIMO"] > df["PROMEDIO"])
        | (df["PROMEDIO"] > df["MÁXIMO"])
    )
    if invalidas.any():
        log.warning("Filas con precios inconsistentes (se descartan): %d", invalidas.sum())
        df = df[~invalidas]

    antes = len(df)
    df = df.drop_duplicates(subset=["FECHA", "FUENTE", "ARTÍCULO"], keep="last")
    if len(df) < antes:
        log.warning("Duplicados descartados: %d", antes - len(df))

    # Control de continuidad: ¿faltan semanas?
    fechas = sorted(df["FECHA"].unique())
    huecos = [
        (pd.Timestamp(a).date(), pd.Timestamp(b).date())
        for a, b in zip(fechas, fechas[1:])
        if (b - a).days != 7
    ]
    if huecos:
        log.warning("Semanas faltantes entre estas fechas: %s", huecos)

    log.info("Filas leídas: %d | válidas: %d | semanas: %d", n_inicial, len(df), len(fechas))
    return df.reset_index(drop=True)


def cargar(engine, df):
    id_col = ("INTEGER PRIMARY KEY AUTOINCREMENT" if engine.dialect.name == "sqlite"
              else "SERIAL PRIMARY KEY")
    ddl = ESQUEMA.format(id_col=id_col)
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)

    with engine.begin() as con:
        for sentencia in [s for s in ddl.split(";") if s.strip()]:
            con.execute(text(sentencia))

        for nombre in df["FUENTE"].unique():
            con.execute(text("INSERT INTO mercado (nombre) VALUES (:n) ON CONFLICT (nombre) DO NOTHING"), {"n": nombre})
        for nombre in df["ARTÍCULO"].unique():
            con.execute(text("INSERT INTO producto (nombre) VALUES (:n) ON CONFLICT (nombre) DO NOTHING"), {"n": nombre})

        mercados = {r[1]: r[0] for r in con.execute(text("SELECT id, nombre FROM mercado"))}
        productos = {r[1]: r[0] for r in con.execute(text("SELECT id, nombre FROM producto"))}

        filas = [
            {
                "fecha": r.FECHA.date(),
                "p": productos[r.ARTÍCULO],
                "m": mercados[r.FUENTE],
                "prom": float(r.PROMEDIO),
                "min": float(r.MÍNIMO),
                "max": float(r.MÁXIMO),
                "f": "DANE-SIPSA",
                "t": ahora,
            }
            for r in df.itertuples()
        ]
        con.execute(
            text("""
                INSERT INTO precio_semanal
                    (fecha, producto_id, mercado_id, precio_promedio, precio_minimo, precio_maximo, fuente, cargado_en)
                VALUES (:fecha, :p, :m, :prom, :min, :max, :f, :t)
                ON CONFLICT (fecha, producto_id, mercado_id) DO UPDATE SET
                    precio_promedio = excluded.precio_promedio,
                    precio_minimo   = excluded.precio_minimo,
                    precio_maximo   = excluded.precio_maximo,
                    cargado_en      = excluded.cargado_en
            """),
            filas,
        )
    log.info("Cargadas/actualizadas %d filas en precio_semanal", len(filas))


def panel(engine, productos):
    """Consulta de ejemplo para el panel: última semana y variación vs la anterior."""
    sql = text("""
        WITH base AS (
            SELECT p.nombre AS producto, ps.fecha, ps.precio_promedio, ps.precio_minimo, ps.precio_maximo,
                   LAG(ps.precio_promedio) OVER (PARTITION BY ps.producto_id ORDER BY ps.fecha) AS prom_anterior
            FROM precio_semanal ps JOIN producto p ON p.id = ps.producto_id
            WHERE p.nombre IN :productos
        )
        SELECT producto, fecha, precio_minimo, precio_maximo, precio_promedio,
               ROUND(100.0 * (precio_promedio - prom_anterior) / prom_anterior, 1) AS variacion_pct
        FROM base
        WHERE fecha = (SELECT MAX(fecha) FROM precio_semanal)
        ORDER BY producto
    """).bindparams(bindparam("productos", expanding=True))
    with engine.connect() as con:
        return con.execute(sql, {"productos": list(productos)}).fetchall()


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "data.xlsx"
    engine = conectar()
    datos = transformar(extraer(ruta))
    cargar(engine, datos)
    canasta = ["Papa capira", "Tomate chonto regional", "Cebolla cabezona blanca", "Aguacate Hass"]
    print("\nPanel de prueba (última semana cargada):")
    for fila in panel(engine, canasta):
        print(" ", fila)
