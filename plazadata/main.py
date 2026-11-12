"""Fábrica de la aplicación. ``create_app(settings)`` permite crear instancias aisladas (por ejemplo, en las pruebas)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .api import admin, precios, uso, web
from .config import LARGO_MINIMO_CLAVE_ADMIN, Settings
from .db import crear_motor, inicializar_esquema
from .errors import registrar_manejadores
from .logging_conf import configurar_logging
from .repositories import PreciosRepository, UsoRepository
from .security import BodyLimitMiddleware, RateLimiter, RequestLogMiddleware, SecurityHeadersMiddleware
from .services import PreciosService, UsoService

log = logging.getLogger("plazadata")


def _cargar_datos_iniciales(settings: Settings, engine) -> None:
    """Si la base está vacía, carga el archivo de datos incluido en el repositorio."""
    archivo = next((p for p in settings.rutas_datos if p.exists()), None)
    if archivo is None:
        log.warning("sin_datos_iniciales")
        return
    from .etl.load import cargar
    from .etl.transform import leer_archivo, transformar
    df, _ = transformar(leer_archivo(archivo))
    cargar(engine, df)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configurar_logging(settings.log_level)
    engine = crear_motor(settings.database_url)
    repo_precios, repo_uso = PreciosRepository(engine), UsoRepository(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Trabajo de arranque fuera del bucle de eventos, para no bloquearlo.
        await run_in_threadpool(inicializar_esquema, engine)
        if not await run_in_threadpool(repo_precios.hay_datos):
            await run_in_threadpool(_cargar_datos_iniciales, settings, engine)
        if settings.admin_key and not settings.admin_habilitado:
            log.warning("admin_key_demasiado_corta", extra={"minimo": LARGO_MINIMO_CLAVE_ADMIN})
        log.info("aplicacion_iniciada", extra={"version": __version__, "entorno": settings.entorno, "admin": settings.admin_habilitado})
        yield
        engine.dispose()

    documentacion = not settings.es_produccion     # en producción no se publica la documentación interactiva
    app = FastAPI(title="PlazaData API", version=__version__, lifespan=lifespan,
                  docs_url="/docs" if documentacion else None, redoc_url=None,
                  openapi_url="/openapi.json" if documentacion else None)

    app.state.settings = settings
    app.state.engine = engine
    app.state.precios = PreciosService(repo_precios)
    app.state.uso = UsoService(repo_uso)
    app.state.limitadores = {
        "lectura": RateLimiter(maximo=240, ventana_s=60),         # consultas de precios
        "eventos": RateLimiter(maximo=120, ventana_s=60),         # medición de uso
        "comentarios": RateLimiter(maximo=5, ventana_s=300),      # comentarios: 5 cada 5 minutos por IP
        "admin_fallos": RateLimiter(maximo=5, ventana_s=900),     # 5 claves erróneas → bloqueo de 15 minutos
    }

    # El último middleware añadido es el más externo: el registro envuelve a todo lo demás.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_cuerpo_bytes)
    if settings.hosts_permitidos:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.hosts_permitidos))
    app.add_middleware(RequestLogMiddleware, proxy_hops=settings.proxy_hops)

    registrar_manejadores(app)
    app.include_router(precios.router)
    app.include_router(uso.router)
    app.include_router(admin.router)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=settings.ruta_static), name="static")
    return app
