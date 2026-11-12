"""Configuración de la aplicación, leída únicamente de variables de entorno.

No hay secretos en el código: la clave de administrador y la URL de la base llegan por el entorno
(en local se puede usar un archivo ``.env``, que está en ``.gitignore``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ: Path = Path(__file__).resolve().parent.parent
LARGO_MINIMO_CLAVE_ADMIN: int = 16


def cargar_dotenv() -> None:
    """Carga ``.env`` en desarrollo si ``python-dotenv`` está instalado (en producción no es necesario)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # dependencia opcional
        return
    load_dotenv(RAIZ / ".env")


def normalizar_url_bd(url: str) -> str:
    """Render entrega ``postgres://`` o ``postgresql://``; SQLAlchemy necesita el nombre del driver."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@dataclass(frozen=True)
class Settings:
    """Valores de configuración inmutables. Se inyectan en ``create_app`` (facilita las pruebas)."""

    database_url: str = "sqlite:///sipsa.db"
    admin_key: str | None = None
    entorno: str = "desarrollo"
    #: Número de proxies de confianza delante de la app (0 = usar la IP de la conexión).
    proxy_hops: int = 0
    hosts_permitidos: tuple[str, ...] = ()
    log_level: str = "INFO"
    max_cuerpo_bytes: int = 8 * 1024
    ruta_static: Path = RAIZ / "static"
    rutas_datos: tuple[Path, ...] = field(default_factory=lambda: (
        RAIZ / "datos" / "sipsa_medellin.csv",
        RAIZ / "datos" / "sipsa_central_mayorista_2026.xlsx",
    ))

    @property
    def es_produccion(self) -> bool:
        return self.entorno.lower() in {"produccion", "production", "prod"}

    @property
    def admin_habilitado(self) -> bool:
        """El resumen privado solo se activa con una clave suficientemente larga."""
        return bool(self.admin_key) and len(self.admin_key or "") >= LARGO_MINIMO_CLAVE_ADMIN

    @classmethod
    def from_env(cls) -> "Settings":
        cargar_dotenv()
        hosts = tuple(h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip())
        try:
            hops = max(0, int(os.getenv("PROXY_HOPS", "0")))
        except ValueError:
            hops = 0
        return cls(
            database_url=normalizar_url_bd(os.getenv("DATABASE_URL", "sqlite:///sipsa.db")),
            admin_key=os.getenv("ADMIN_KEY") or None,
            entorno=os.getenv("ENTORNO", "desarrollo"),
            proxy_hops=hops,
            hosts_permitidos=hosts,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
