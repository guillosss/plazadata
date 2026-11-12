from starlette.requests import Request

from plazadata.config import Settings
from plazadata.repositories import escapar_like
from plazadata.security import RateLimiter, huella_ip, ip_cliente


def _solicitud(xff: str | None = None, cliente: str = "9.9.9.9") -> Request:
    cabeceras = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": cabeceras, "client": (cliente, 1234)})


def test_limitador_ventana_deslizante():
    t = [0.0]
    r = RateLimiter(maximo=3, ventana_s=10, reloj=lambda: t[0])
    assert [r.permitir("a") for _ in range(4)] == [True, True, True, False]
    assert r.bloqueado("a") and not r.bloqueado("b")
    t[0] = 10.1
    assert r.permitir("a")            # al pasar la ventana se recupera el cupo


def test_limitador_memoria_acotada():
    r = RateLimiter(maximo=5, ventana_s=60, max_claves=100)
    for i in range(10_000):           # un atacante rotando claves no hace crecer la memoria sin límite
        r.permitir(f"clave-{i}")
    assert len(r._eventos) == 100


def test_ip_sin_proxy_ignora_x_forwarded_for():
    assert ip_cliente(_solicitud("1.1.1.1"), proxy_hops=0) == "9.9.9.9"      # cabecera falsificable: no se usa


def test_ip_con_un_proxy_toma_la_ultima_entrada():
    # El cliente puede anteponer valores falsos; solo es fiable lo que añade nuestro proxy (al final).
    assert ip_cliente(_solicitud("6.6.6.6, 1.2.3.4"), proxy_hops=1) == "1.2.3.4"
    assert ip_cliente(_solicitud(None), proxy_hops=1) == "9.9.9.9"


def test_huella_ip_no_revela_la_ip():
    h = huella_ip("1.2.3.4")
    assert "1.2.3.4" not in h and len(h) == 12 and h == huella_ip("1.2.3.4")


def test_escapar_like():
    assert escapar_like("100%_a\\b") == "100\\%\\_a\\\\b"


def test_clave_admin_corta_no_habilita():
    assert not Settings(admin_key="corta").admin_habilitado
    assert not Settings(admin_key=None).admin_habilitado
    assert Settings(admin_key="x" * 16).admin_habilitado
