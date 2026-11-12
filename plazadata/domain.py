"""Reglas del dominio, sin dependencias de web ni de base de datos (fáciles de probar)."""
from __future__ import annotations

from dataclasses import dataclass


class ErrorDominio(Exception):
    """Error esperable causado por una entrada inválida; se traduce a una respuesta 4xx."""


class MercadoInvalido(ErrorDominio):
    pass


class EventoNoPermitido(ErrorDominio):
    pass


@dataclass(frozen=True)
class Mercado:
    clave: str
    etiqueta: str
    #: Patrón LIKE del nombre con que el DANE identifica la fuente (constante, no viene del usuario).
    patron: str


MERCADOS: dict[str, Mercado] = {
    "mayorista": Mercado("mayorista", "Central Mayorista", "%Central Mayorista%"),
    "minorista": Mercado("minorista", "Plaza Minorista", "%Plaza Minorista%"),
}

CANASTA_DEFECTO: tuple[str, ...] = ("Papa capira", "Tomate chonto regional", "Cebolla cabezona blanca", "Aguacate Hass")
MAX_PRODUCTOS_POR_CONSULTA: int = 40

#: Lista cerrada de eventos de uso: la API rechaza cualquier otro valor.
EVENTOS: frozenset[str] = frozenset({
    "abrir_app", "completar_canasta", "agregar_insumo", "quitar_insumo", "cambiar_mercado", "ver_historico",
    "crear_alerta", "guardar_alertas", "abrir_comentario", "enviar_comentario", "instalar_app",
})


def obtener_mercado(clave: str) -> Mercado:
    try:
        return MERCADOS[clave]
    except KeyError:
        raise MercadoInvalido(f"Mercado no válido. Opciones: {', '.join(MERCADOS)}") from None


@dataclass(frozen=True)
class Unidad:
    codigo: str
    etiqueta: str


def unidad_de(nombre: str) -> Unidad:
    """Unidad en la que el DANE expresa el precio de un producto.

    - Por defecto, el boletín semanal publica «pesos por kilogramo».
    - Litro: el tablero del DANE aclara que aceites y vinagre se miden por litro.
    - Unidad: los huevos valen ~500 pesos, magnitud que solo cuadra por unidad (inferido; confirmar con el DANE).
    - Sin confirmar: «Jugo instantáneo (sobre)» no encaja ni por kilo ni por litro.
    """
    n = nombre.strip().lower()
    if n.startswith(("aceite", "vinagre")):
        return Unidad("litro", "COP/litro")
    if n.startswith("huevo"):
        return Unidad("unidad", "COP/unidad")
    if n.startswith("jugo"):
        return Unidad("sin_confirmar", "COP (unidad por confirmar)")
    return Unidad("kg", "COP/kg")


def variacion_pct(actual: float, anterior: float | None) -> float | None:
    """Variación porcentual frente al valor anterior; ``None`` si no hay base de comparación."""
    if not anterior:
        return None
    return round((actual - anterior) / anterior * 100, 1)
