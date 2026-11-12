"""Pruebas de integración de la API de precios, con los datos reales del DANE incluidos en el repositorio."""
import pytest


def test_salud_carga_automatica(cliente):
    r = cliente.get("/api/salud").json()
    assert r == {"estado": "ok", "ultima_fecha": "2026-11-06", "filas": 16591}


def test_mercados(cliente):
    r = cliente.get("/api/mercados").json()
    assert [(m["clave"], m["productos"]) for m in r] == [("mayorista", 217), ("minorista", 130)]


def test_ultimo_mayorista_coincide_con_el_dane(cliente):
    r = {p["producto"]: p for p in cliente.get("/api/precios/ultimo").json()}
    papa = r["Papa capira"]
    assert (papa["minimo"], papa["maximo"], papa["promedio"], papa["variacion_pct"], papa["fecha"]) == (3000, 3800, 3598, 11.1, "2026-11-06")
    assert r["Aguacate Hass"]["variacion_pct"] == -10.5
    assert papa["desactualizado"] is False and papa["unidad"] == "COP/kg"


def test_ultimo_respeta_el_orden_y_quita_repetidos(cliente):
    r = cliente.get("/api/precios/ultimo", params={"producto": ["Tomate chonto regional", "Papa capira", "Tomate chonto regional", "  "]}).json()
    assert [p["producto"] for p in r] == ["Tomate chonto regional", "Papa capira"]


def test_minorista_y_producto_sin_datos(cliente):
    r = {p["producto"]: p for p in cliente.get("/api/precios/ultimo", params={"producto": ["Papa capira", "Aguacate Hass"], "mercado": "minorista"}).json()}
    assert r["Papa capira"]["promedio"] == 3653
    assert r["Aguacate Hass"] == {"producto": "Aguacate Hass", "disponible": False, "mercado": "minorista", "unidad": "COP/kg", "unidad_codigo": "kg"}


def test_unidades_y_dato_viejo(cliente):
    r = {p["producto"]: p for p in cliente.get("/api/precios/ultimo", params={"producto": ["Aceite girasol", "Huevo rojo A", "Papa R-12 negra"]}).json()}
    assert r["Aceite girasol"]["unidad"] == "COP/litro" and r["Huevo rojo A"]["unidad"] == "COP/unidad"
    assert r["Papa R-12 negra"]["desactualizado"] is True and r["Papa R-12 negra"]["fecha"] == "2026-07-31"


def test_historico_y_comparacion(cliente):
    h = cliente.get("/api/precios/historico", params={"producto": "Papa capira", "semanas": 12}).json()
    assert len(h) == 12 and h[0]["fecha"] == "2026-08-21" and h[-1]["promedio"] == 3598
    assert cliente.get("/api/precios/historico", params={"producto": "Aguacate Hass", "mercado": "minorista"}).json() == []
    c = cliente.get("/api/precios/comparar", params={"producto": "Papa capira"}).json()
    assert c["comparable"] is True and c["diferencia_pct"] == 1.5
    assert cliente.get("/api/precios/comparar", params={"producto": "Aguacate Hass"}).json()["comparable"] is False


def test_busqueda(cliente):
    assert cliente.get("/api/productos", params={"q": "zanah"}).json() == ["Zanahoria larga vida"]
    assert cliente.get("/api/productos", params={"q": "ZANAH", "mercado": "minorista"}).json() == ["Zanahoria larga vida"]
    assert len(cliente.get("/api/productos", params={"q": "papa", "limite": 3}).json()) == 3


@pytest.mark.parametrize("comodin", ["%", "_", "%%%", "a%a", "\\"])
def test_busqueda_los_comodines_son_literales(cliente, comodin):
    # Sin escape, «%» devolvería todo el catálogo. Ningún producto contiene estos caracteres.
    assert cliente.get("/api/productos", params={"q": comodin}).json() == []


@pytest.mark.parametrize("ataque", ["' OR '1'='1", "Papa capira'; DROP TABLE precio_semanal;--", "x' UNION SELECT nombre FROM mercado--"])
def test_inyeccion_sql_no_tiene_efecto(cliente, ataque):
    r = cliente.get("/api/precios/ultimo", params={"producto": [ataque]})
    assert r.status_code == 200 and r.json()[0]["disponible"] is False
    assert cliente.get("/api/precios/historico", params={"producto": ataque}).json() == []
    assert cliente.get("/api/productos", params={"q": ataque[:60]}).json() == []
    assert cliente.get("/api/salud").json()["filas"] == 16591          # la tabla sigue intacta


@pytest.mark.parametrize("ruta,params,estado", [
    ("/api/precios/ultimo", {"mercado": "otro"}, 400),               # mercado inexistente
    ("/api/precios/ultimo", {"mercado": "MAYORISTA; --"}, 422),      # formato inválido
    ("/api/precios/historico", {"producto": "Papa capira", "semanas": 0}, 422),
    ("/api/precios/historico", {"producto": "Papa capira", "semanas": 9999}, 422),
    ("/api/precios/historico", {"producto": ""}, 422),
    ("/api/precios/historico", {"producto": "x" * 201}, 422),
    ("/api/productos", {"limite": 0}, 422),
    ("/api/productos", {"limite": 1000}, 422),
    ("/api/productos", {"q": "x" * 61}, 422),
])
def test_validacion_de_parametros(cliente, ruta, params, estado):
    assert cliente.get(ruta, params=params).status_code == estado
