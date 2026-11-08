"""
API de PlazaData (MVP): sirve los precios del SIPSA cargados por el ETL
y entrega el panel web (static/index.html).

Ejecutar en local, desde esta carpeta (donde está sipsa.db):
    python -m pip install -r requirements.txt
    python etl_sipsa.py data.xlsx          # una vez, para llenar la base
    python -m uvicorn api:app --reload
    # abrir http://127.0.0.1:8000

Con PostgreSQL (Render): definir la variable de entorno DATABASE_URL.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text

BASE = Path(__file__).parent
DATOS = BASE / "datos" / "sipsa_central_mayorista_2026.xlsx"
CANASTA_DEFECTO = ["Papa capira", "Tomate chonto regional", "Cebolla cabezona blanca", "Aguacate Hass"]


def conectar():
    url = os.getenv("DATABASE_URL", "sqlite:///sipsa.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url)


engine = conectar()


def _hay_datos():
    try:
        with engine.connect() as con:
            return (con.execute(text("SELECT COUNT(*) FROM precio_semanal")).scalar() or 0) > 0
    except Exception:
        return False


@asynccontextmanager
async def lifespan(_app):
    """Al iniciar: si la base está vacía, carga automáticamente los datos incluidos en /datos."""
    if not _hay_datos() and DATOS.exists():
        import etl_sipsa
        etl_sipsa.cargar(engine, etl_sipsa.transformar(etl_sipsa.extraer(str(DATOS))))
    yield


app = FastAPI(title="PlazaData API", version="0.2", lifespan=lifespan)


def _f(v):
    return None if v is None else float(v)


@app.get("/api/salud")
def salud():
    """Comprueba que la base responde y dice cuál es la última semana cargada."""
    with engine.connect() as con:
        ultima = con.execute(text("SELECT MAX(fecha) FROM precio_semanal")).scalar()
        filas = con.execute(text("SELECT COUNT(*) FROM precio_semanal")).scalar()
    return {"estado": "ok", "ultima_fecha": str(ultima)[:10] if ultima else None, "filas": filas}


@app.get("/api/productos")
def productos(q: str = "", limite: int = 20):
    """Busca productos por nombre (para agregar insumos a la canasta)."""
    sql = text("SELECT nombre FROM producto WHERE LOWER(nombre) LIKE :q ORDER BY nombre LIMIT :n")
    with engine.connect() as con:
        filas = con.execute(sql, {"q": f"%{q.strip().lower()}%", "n": max(1, min(limite, 50))}).fetchall()
    return [r[0] for r in filas]


@app.get("/api/precios/ultimo")
def precios_ultimo(producto: Optional[List[str]] = Query(default=None)):
    """Último precio (mín, máx, promedio) y variación frente a la semana anterior."""
    nombres = producto or CANASTA_DEFECTO
    sql = text("""
        SELECT ps.fecha, ps.precio_minimo, ps.precio_maximo, ps.precio_promedio
        FROM precio_semanal ps JOIN producto p ON p.id = ps.producto_id
        WHERE p.nombre = :n ORDER BY ps.fecha DESC LIMIT 2
    """)
    salida = []
    with engine.connect() as con:
        ultima = str(con.execute(text("SELECT MAX(fecha) FROM precio_semanal")).scalar())[:10]
        for n in nombres[:30]:
            filas = con.execute(sql, {"n": n}).fetchall()
            if not filas:
                salida.append({"producto": n, "disponible": False})
                continue
            f0 = filas[0]
            prom = _f(f0[3])
            ant = _f(filas[1][3]) if len(filas) > 1 else None
            var = round((prom - ant) / ant * 100, 1) if ant else None
            salida.append({
                "producto": n, "disponible": True, "fecha": str(f0[0])[:10],
                "minimo": _f(f0[1]), "maximo": _f(f0[2]), "promedio": prom,
                "promedio_anterior": ant,
                "fecha_anterior": str(filas[1][0])[:10] if len(filas) > 1 else None,
                "variacion_pct": var,
                # True si el último dato del producto es de una semana anterior a la última cargada
                "desactualizado": str(f0[0])[:10] < ultima,
            })
    return salida


@app.get("/api/precios/historico")
def precios_historico(producto: str, semanas: int = 12):
    """Serie semanal de un producto (las últimas N semanas con dato)."""
    sql = text("""
        SELECT ps.fecha, ps.precio_promedio, ps.precio_minimo, ps.precio_maximo
        FROM precio_semanal ps JOIN producto p ON p.id = ps.producto_id
        WHERE p.nombre = :n ORDER BY ps.fecha DESC LIMIT :k
    """)
    with engine.connect() as con:
        filas = con.execute(sql, {"n": producto, "k": max(1, min(semanas, 60))}).fetchall()
    if not filas:
        raise HTTPException(status_code=404, detail=f"Sin datos para '{producto}'")
    return [{"fecha": str(r[0])[:10], "promedio": _f(r[1]), "minimo": _f(r[2]), "maximo": _f(r[3])}
            for r in reversed(filas)]


# ---- Panel web (archivos estáticos)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def panel():
    return FileResponse(BASE / "static" / "index.html")
