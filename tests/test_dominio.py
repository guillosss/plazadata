import pytest

from plazadata.domain import MercadoInvalido, obtener_mercado, unidad_de, variacion_pct
from plazadata.schemas import ComentarioIn, EventoIn, limpiar_texto


@pytest.mark.parametrize("nombre,codigo", [
    ("Papa capira", "kg"), ("Aceite girasol", "litro"), ("  vinagre ", "litro"), ("Huevo rojo A", "unidad"),
    ("Jugo instantáneo (sobre)", "sin_confirmar"), ("Aguacate Hass", "kg"),
])
def test_unidad_de(nombre, codigo):
    assert unidad_de(nombre).codigo == codigo


def test_variacion_pct():
    assert variacion_pct(3598, 3238) == 11.1
    assert variacion_pct(100, 100) == 0.0
    assert variacion_pct(100, None) is None
    assert variacion_pct(100, 0) is None      # sin base de comparación no se divide por cero


def test_mercado_invalido():
    assert obtener_mercado("minorista").etiqueta == "Plaza Minorista"
    with pytest.raises(MercadoInvalido):
        obtener_mercado("otro")


def test_limpiar_texto_quita_caracteres_de_control_e_invisibles():
    assert limpiar_texto("hola\x00\u202e  mundo\t!") == "hola mundo!"
    assert limpiar_texto("línea 1\nlínea 2", permitir_saltos=True) == "línea 1\nlínea 2"
    assert limpiar_texto("línea 1\nlínea 2") == "línea 1línea 2"


@pytest.mark.parametrize("datos", [
    {"cliente": "corto", "evento": "abrir_app"},                               # identificador muy corto
    {"cliente": "abc<script>123", "evento": "abrir_app"},                      # caracteres no permitidos
    {"cliente": "abcdefgh1234", "evento": "ABRIR"},                            # formato de evento inválido
    {"cliente": "abcdefgh1234", "evento": "abrir_app", "detalle": "x" * 201},  # detalle demasiado largo
    {"cliente": "abcdefgh1234", "evento": "abrir_app", "admin": True},         # campo desconocido
])
def test_evento_rechaza_entradas_invalidas(datos):
    with pytest.raises(ValueError):
        EventoIn(**datos)


def test_comentario_se_limpia_y_no_puede_quedar_vacio():
    assert ComentarioIn(cliente="abcdefgh1234", texto="  hola\x07  ").texto == "hola"
    with pytest.raises(ValueError):
        ComentarioIn(cliente="abcdefgh1234", texto="\x00\x01 ")
    with pytest.raises(ValueError):
        ComentarioIn(cliente="abcdefgh1234", texto="x" * 1001)
