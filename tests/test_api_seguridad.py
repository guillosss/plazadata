"""Pruebas de seguridad de la API: cabeceras, autenticación, límites, validación y manejo de errores."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from plazadata.config import Settings
from plazadata.main import create_app

from .conftest import CLAVE_ADMIN

EVENTO = {"cliente": "cliente-de-prueba-01", "evento": "abrir_app"}


# ------------------------------------------------------------ cabeceras
def test_cabeceras_de_seguridad(cliente):
    h = cliente.get("/").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
    csp = h["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert len(h["x-request-id"]) == 16


def test_hsts_solo_con_https(cliente):
    assert "strict-transport-security" not in cliente.get("/api/salud").headers
    assert "max-age=" in cliente.get("/api/salud", headers={"X-Forwarded-Proto": "https"}).headers["strict-transport-security"]


def test_cache(cliente, admin):
    assert cliente.get("/api/salud").headers["cache-control"] == "public, max-age=300"
    assert cliente.get("/api/admin/resumen", headers=admin).headers["cache-control"] == "no-store"
    assert cliente.get("/admin").headers["cache-control"] == "no-store"


def test_el_html_no_tiene_scripts_ni_estilos_en_linea(cliente):
    for ruta in ("/", "/admin"):
        html = cliente.get(ruta).text
        assert "<style" not in html and 'style="' not in html and "onclick=" not in html
        assert "<script>" not in html                     # solo <script src=...>


# ------------------------------------------------------------ administrador
def test_admin_requiere_cabecera(cliente, admin):
    assert cliente.get("/api/admin/resumen").status_code == 401
    assert cliente.get("/api/admin/resumen", params={"clave": CLAVE_ADMIN}).status_code == 401   # la clave en la URL ya no vale
    assert cliente.get("/api/admin/resumen", headers={"X-Admin-Key": "incorrecta"}).status_code == 401
    assert cliente.get("/api/admin/resumen", headers=admin).status_code == 200


def test_admin_bloquea_tras_fallos_repetidos(cliente, admin):
    for _ in range(5):
        assert cliente.get("/api/admin/resumen", headers={"X-Admin-Key": "adivinando"}).status_code == 401
    bloqueado = cliente.get("/api/admin/resumen", headers=admin)          # ni la clave correcta entra durante el bloqueo
    assert bloqueado.status_code == 429 and "retry-after" in bloqueado.headers


def test_admin_desactivado_sin_clave_o_con_clave_corta(tmp_path):
    for clave in (None, "corta"):
        app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'x.db'}", admin_key=clave, rutas_datos=()))
        with TestClient(app) as c:
            assert c.get("/api/admin/resumen", headers={"X-Admin-Key": clave or "x"}).status_code == 503


def test_documentacion_oculta_en_produccion(tmp_path, cliente):
    assert cliente.get("/docs").status_code == 200                 # en desarrollo sí está
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'p.db'}", entorno="produccion", rutas_datos=()))
    with TestClient(app) as c:
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


# ------------------------------------------------------------ entradas
def test_evento_valido_y_lista_cerrada(cliente):
    assert cliente.post("/api/evento", json=EVENTO).status_code == 204
    assert cliente.post("/api/evento", json={**EVENTO, "evento": "borrar_todo"}).status_code == 400


@pytest.mark.parametrize("cuerpo", [
    {"cliente": "x", "evento": "abrir_app"},
    {**EVENTO, "cliente": "<script>alert(1)</script>"},
    {**EVENTO, "es_admin": True},
    {**EVENTO, "detalle": "x" * 201},
    {"evento": "abrir_app"},
])
def test_evento_invalido_422_sin_devolver_la_entrada(cliente, cuerpo):
    r = cliente.post("/api/evento", json=cuerpo)
    assert r.status_code == 422
    assert "<script>" not in r.text and "input" not in r.json()        # no se refleja lo que mandó el cliente


def test_cuerpo_demasiado_grande(cliente):
    r = cliente.post("/api/comentario", json={"cliente": "cliente-de-prueba-01", "texto": "x" * 20000})
    assert r.status_code == 413


def test_cuerpo_sin_content_length(cliente):
    def trozos():
        yield b'{"cliente": "cliente-de-prueba-01", "evento": "abrir_app"}'

    assert cliente.post("/api/evento", content=trozos(), headers={"Content-Type": "application/json"}).status_code == 411


def test_comentario_guarda_texto_limpio_y_el_resumen_lo_devuelve(cliente, admin):
    malicioso = "<img src=x onerror=alert(1)>\x00 hola"
    assert cliente.post("/api/comentario", json={"cliente": "cliente-de-prueba-01", "pantalla": "panel", "texto": malicioso}).status_code == 204
    textos = [c["texto"] for c in cliente.get("/api/admin/resumen", headers=admin).json()["comentarios"]]
    # Se guarda como texto (sin el carácter nulo). El escape para HTML lo hace quien lo muestra (admin.js).
    assert "<img src=x onerror=alert(1)> hola" in textos


def test_limite_de_ritmo_en_comentarios(cliente):
    cuerpo = {"cliente": "cliente-de-prueba-02", "texto": "hola"}
    estados = [cliente.post("/api/comentario", json=cuerpo).status_code for _ in range(7)]
    assert estados == [204] * 5 + [429] * 2


def test_limite_de_ritmo_no_se_evade_cambiando_de_identificador(cliente):
    estados = [cliente.post("/api/comentario", json={"cliente": f"cliente-rotado-{i:04d}", "texto": "hola"}).status_code for i in range(7)]
    assert estados.count(429) == 2          # el límite es por IP, no por el identificador que envía el cliente


# ------------------------------------------------------------ errores
def test_error_inesperado_no_filtra_detalles(app, monkeypatch):
    def falla():
        raise RuntimeError("contraseña=secreto en /ruta/interna.py")

    monkeypatch.setattr(app.state.precios, "salud", falla)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/salud")
    assert r.status_code == 500 and r.json()["detail"] == "Error interno." and "secreto" not in r.text and r.json()["request_id"]


def test_base_caida_devuelve_503_con_retry_after(app, monkeypatch):
    def falla(*_a, **_k):
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada en 10.0.0.5:5432"))

    monkeypatch.setattr(app.state.precios, "mercados", falla)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/mercados")
    assert r.status_code == 503 and r.headers["retry-after"] == "30" and "10.0.0.5" not in r.text


# ------------------------------------------------------------ uso
def test_resumen_de_uso(cliente, admin):
    antes = cliente.get("/api/admin/resumen", headers=admin).json()
    for cuerpo in ({"cliente": "piloto-uno-0001", "evento": "abrir_app"}, {"cliente": "piloto-uno-0001", "evento": "ver_historico", "detalle": "Papa capira"},
                   {"cliente": "piloto-dos-0002", "evento": "abrir_app"}):
        assert cliente.post("/api/evento", json=cuerpo).status_code == 204
    r = cliente.get("/api/admin/resumen", headers=admin).json()
    assert r["eventos_total"] == antes["eventos_total"] + 3
    assert r["usuarios_unicos"] == antes["usuarios_unicos"] + 2
    assert {u["cliente"] for u in r["por_usuario"]} >= {"piloto-u", "piloto-d"}      # solo un prefijo del identificador
    assert sum(s["aperturas"] for s in r["por_semana"]) == sum(s["aperturas"] for s in antes["por_semana"]) + 2
