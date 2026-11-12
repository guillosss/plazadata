"""Configuración de las pruebas: una aplicación aislada con su propia base de datos temporal.

Para ejecutar contra PostgreSQL:  PRUEBAS_DATABASE_URL=postgresql://... python -m pytest
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from plazadata.config import Settings, normalizar_url_bd
from plazadata.main import create_app

CLAVE_ADMIN = "clave-de-pruebas-0123456789"


@pytest.fixture(scope="session")
def url_bd(tmp_path_factory) -> str:
    externa = os.getenv("PRUEBAS_DATABASE_URL")
    if externa:
        return normalizar_url_bd(externa)
    return f"sqlite:///{tmp_path_factory.mktemp('bd') / 'pruebas.db'}"


@pytest.fixture(scope="session")
def app(url_bd: str):
    return create_app(Settings(database_url=url_bd, admin_key=CLAVE_ADMIN, entorno="desarrollo"))


@pytest.fixture(scope="session")
def cliente(app):
    with TestClient(app) as c:      # el bloque «with» ejecuta el arranque (crea tablas y carga los datos)
        yield c


@pytest.fixture(autouse=True)
def _limitadores_limpios(app):
    """Cada prueba empieza sin historial de límite de ritmo."""
    for limitador in app.state.limitadores.values():
        limitador._eventos.clear()
    yield


@pytest.fixture
def admin() -> dict[str, str]:
    return {"X-Admin-Key": CLAVE_ADMIN}
