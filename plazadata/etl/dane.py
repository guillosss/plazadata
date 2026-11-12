"""Cliente del servicio web oficial del DANE (SOAP), con reintentos y análisis de XML endurecido.

Notas verificadas en nov-2026:
  * Hay que llamar por https: con http el servidor redirige y la petición deja de ser SOAP.
  * Los campos terminan en «Kg» pero son PRECIOS por kilo (coinciden con el tablero del DANE).
  * ``fechaIni`` es el sábado en que empieza la semana; la base usa el viernes de cierre (fechaIni + 6 días).
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Sequence

import pandas as pd

log = logging.getLogger("plazadata.dane")

URL_SERVICIO: str = "https://appweb.dane.gov.co/sipsaWS/SrvSipsaUpraBeanService"
BINDING: str = "{http://servicios.sipsa.co.gov.dane/}SrvSipsaUpraPortBinding"
FUENTES: tuple[str, ...] = ("Medellín, Central Mayorista de Antioquia", 'Medellín, Plaza Minorista "José María Villa"')
CAMPOS_REQUERIDOS: frozenset[str] = frozenset({"artiNombre", "fuenNombre", "fechaIni", "promedioKg", "minimoKg", "maximoKg"})


class ErrorServicioDane(RuntimeError):
    """El servicio del DANE no respondió correctamente tras agotar los reintentos."""


def _llamada_soap(url: str, binding: str, timeout_s: int, timeout_operacion_s: int) -> list[dict[str, Any]]:
    """Llamada real con zeep. Se importa aquí para que la API web no dependa de zeep."""
    from zeep import Client, Settings
    from zeep.helpers import serialize_object
    from zeep.transports import Transport

    # Análisis de XML endurecido: sin DTD, sin entidades y sin recursos externos (previene XXE y «billion laughs»).
    ajustes = Settings(strict=True, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    cliente = Client(url + "?WSDL", transport=Transport(timeout=timeout_s, operation_timeout=timeout_operacion_s), settings=ajustes)
    servicio = cliente.create_service(binding, url)     # fuerza https en lugar de la dirección http que publica el WSDL
    return serialize_object(servicio.promediosSipsaSemanaMadr())


class DaneClient:
    """Obtiene los precios semanales con reintentos exponenciales.

    ``llamada`` y ``dormir`` son inyectables para probar la lógica de reintentos sin red.
    """

    def __init__(self, url: str = URL_SERVICIO, binding: str = BINDING, reintentos: int = 3, espera_base_s: float = 2.0,
                 timeout_s: int = 60, timeout_operacion_s: int = 900,
                 llamada: Callable[[str, str, int, int], list[dict[str, Any]]] = _llamada_soap,
                 dormir: Callable[[float], None] = time.sleep) -> None:
        if not url.lower().startswith("https://"):
            raise ValueError("El servicio del DANE debe consultarse por https")
        self.url, self.binding = url, binding
        self.reintentos, self.espera_base_s = max(1, reintentos), espera_base_s
        self.timeout_s, self.timeout_operacion_s = timeout_s, timeout_operacion_s
        self._llamada, self._dormir = llamada, dormir

    def obtener_semanal(self) -> list[dict[str, Any]]:
        ultimo: Exception | None = None
        for intento in range(1, self.reintentos + 1):
            try:
                registros = self._llamada(self.url, self.binding, self.timeout_s, self.timeout_operacion_s)
                validar_registros(registros)
                log.info("dane_respuesta", extra={"registros": len(registros), "intento": intento})
                return registros
            except Exception as exc:   # se registra y se reintenta; al agotar los intentos se propaga con contexto
                ultimo = exc
                log.warning("dane_fallo", extra={"intento": intento, "de": self.reintentos, "error": f"{type(exc).__name__}: {exc}"[:300]})
                if intento < self.reintentos:
                    self._dormir(self.espera_base_s * (2 ** (intento - 1)) + random.uniform(0, 1))   # retroceso exponencial con variación
        raise ErrorServicioDane(f"El servicio del DANE falló tras {self.reintentos} intentos") from ultimo


def validar_registros(registros: Any) -> None:
    """Comprueba la forma de la respuesta antes de usarla (no se confía en datos externos)."""
    if not isinstance(registros, list) or not registros:
        raise ValueError("La respuesta del DANE está vacía o no es una lista")
    primero = registros[0]
    if not isinstance(primero, dict) or not CAMPOS_REQUERIDOS.issubset(primero.keys()):
        raise ValueError("La respuesta del DANE no tiene los campos esperados")


def a_dataframe(registros: Sequence[dict[str, Any]], fuentes: Sequence[str] = FUENTES) -> pd.DataFrame:
    """Convierte los registros del servicio a las columnas que usa el ETL, solo para las fuentes pedidas."""
    df = pd.DataFrame(registros)
    df = df[df["fuenNombre"].isin(list(fuentes))].copy()
    inicio = pd.to_datetime(df["fechaIni"].astype(str).str[:10], errors="coerce")
    return pd.DataFrame({
        "FECHA": inicio + pd.Timedelta(days=6),
        "FUENTE": df["fuenNombre"].astype(str), "ARTÍCULO": df["artiNombre"].astype(str),
        "PROMEDIO": df["promedioKg"], "MÍNIMO": df["minimoKg"], "MÁXIMO": df["maximoKg"],
    })
