"""Seguridad defensiva: límite de ritmo, IP del cliente, autenticación del administrador y middlewares.

Decisiones:
- El límite de ritmo se aplica por IP (no por el identificador que envía el cliente, que se puede rotar)
  y su memoria está acotada, para que no sirva como vector de agotamiento de memoria.
- La clave de administrador viaja en una cabecera, nunca en la URL (las URL quedan en registros e historiales).
- Las cabeceras de seguridad incluyen una CSP estricta: por eso el frontend no usa scripts ni estilos en línea.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
import uuid
from collections import OrderedDict, deque
from typing import Awaitable, Callable, Deque

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from .logging_conf import request_id_var

log = logging.getLogger("plazadata.seguridad")
_SAL_PROCESO = secrets.token_bytes(16)   # sal por proceso: las IP no se pueden reconstruir desde los registros


class RateLimiter:
    """Ventana deslizante por clave, segura entre hilos y con memoria acotada (descarta las claves más antiguas)."""

    def __init__(self, maximo: int, ventana_s: float, max_claves: int = 10_000,
                 reloj: Callable[[], float] = time.monotonic) -> None:
        self.maximo, self.ventana_s, self.max_claves = maximo, ventana_s, max_claves
        self._reloj = reloj
        self._eventos: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self._candado = threading.Lock()

    def _purgar(self, cola: Deque[float], ahora: float) -> None:
        while cola and ahora - cola[0] > self.ventana_s:
            cola.popleft()

    def permitir(self, clave: str) -> bool:
        """Registra un intento y dice si está dentro del límite."""
        ahora = self._reloj()
        with self._candado:
            cola = self._eventos.pop(clave, None) or deque()
            self._purgar(cola, ahora)
            permitido = len(cola) < self.maximo
            if permitido:
                cola.append(ahora)
            self._eventos[clave] = cola            # la clave usada pasa a ser la más reciente
            while len(self._eventos) > self.max_claves:
                self._eventos.popitem(last=False)   # descarta la menos reciente
            return permitido

    def bloqueado(self, clave: str) -> bool:
        """Consulta sin registrar (para saber si ya se agotó el cupo)."""
        ahora = self._reloj()
        with self._candado:
            cola = self._eventos.get(clave)
            if not cola:
                return False
            self._purgar(cola, ahora)
            return len(cola) >= self.maximo


def ip_cliente(request: Request, proxy_hops: int) -> str:
    """IP real del cliente.

    ``X-Forwarded-For`` lo puede falsificar cualquiera, así que solo se confía en las últimas ``proxy_hops``
    entradas (las que añaden nuestros propios proxies). Con 0 se usa la IP de la conexión.
    """
    directa = request.client.host if request.client else "desconocida"
    if proxy_hops <= 0:
        return directa
    partes = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return partes[-proxy_hops] if len(partes) >= proxy_hops else directa


def huella_ip(ip: str) -> str:
    """Huella no reversible de la IP para los registros (permite correlacionar sin guardar el dato personal)."""
    return hashlib.sha256(_SAL_PROCESO + ip.encode()).hexdigest()[:12]


def limitar(nombre: str) -> Callable[[Request], None]:
    """Dependencia de FastAPI que aplica el limitador ``nombre`` por IP."""

    def dependencia(request: Request) -> None:
        limitador: RateLimiter = request.app.state.limitadores[nombre]
        ip = ip_cliente(request, request.app.state.settings.proxy_hops)
        if not limitador.permitir(ip):
            log.warning("limite_de_ritmo", extra={"limitador": nombre, "ip": huella_ip(ip)})
            raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Intenta de nuevo en un momento.",
                                headers={"Retry-After": str(int(limitador.ventana_s))})

    return dependencia


def requerir_admin(request: Request) -> None:
    """Autentica al administrador con la cabecera ``X-Admin-Key``.

    - Comparación en tiempo constante (evita ataques de temporización).
    - Bloqueo temporal por IP tras varios fallos (fuerza bruta).
    - Si no hay clave configurada, o es demasiado corta, el resumen queda desactivado.
    """
    settings = request.app.state.settings
    if not settings.admin_habilitado:
        raise HTTPException(status_code=503, detail="El resumen está desactivado: define ADMIN_KEY (16 caracteres o más).")
    ip = ip_cliente(request, settings.proxy_hops)
    fallos: RateLimiter = request.app.state.limitadores["admin_fallos"]
    if fallos.bloqueado(ip):
        log.warning("admin_bloqueado", extra={"ip": huella_ip(ip)})
        raise HTTPException(status_code=429, detail="Demasiados intentos fallidos. Espera unos minutos.",
                            headers={"Retry-After": str(int(fallos.ventana_s))})
    recibida = request.headers.get("x-admin-key", "")
    if not recibida or not secrets.compare_digest(recibida.encode(), settings.admin_key.encode()):
        fallos.permitir(ip)
        log.warning("admin_clave_incorrecta", extra={"ip": huella_ip(ip)})
        raise HTTPException(status_code=401, detail="Clave incorrecta o ausente.", headers={"WWW-Authenticate": "X-Admin-Key"})
    log.info("admin_acceso", extra={"ip": huella_ip(ip)})


CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
_RUTAS_DOC = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade cabeceras de seguridad a todas las respuestas."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        respuesta = await call_next(request)
        h = respuesta.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if not request.url.path.startswith(_RUTAS_DOC):      # la documentación interactiva carga recursos externos
            h.setdefault("Content-Security-Policy", CSP)
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        ruta = request.url.path
        if ruta.startswith("/api/admin") or ruta.startswith("/admin"):
            h["Cache-Control"] = "no-store"
        elif ruta.startswith("/api/") and request.method == "GET" and respuesta.status_code == 200:
            h.setdefault("Cache-Control", "public, max-age=300")   # datos públicos que cambian una vez por semana
        return respuesta


class BodyLimitMiddleware(BaseHTTPMiddleware):
    """Rechaza cuerpos grandes antes de leerlos (evita agotar memoria con solicitudes enormes)."""

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method in {"POST", "PUT", "PATCH"}:
            largo = request.headers.get("content-length")
            if largo is None or not largo.isdigit():
                return JSONResponse({"detail": "Se requiere la cabecera Content-Length."}, status_code=411)
            if int(largo) > self.max_bytes:
                return JSONResponse({"detail": "El cuerpo de la solicitud es demasiado grande."}, status_code=413)
        return await call_next(request)


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Asigna un identificador a cada solicitud y registra método, ruta, estado y duración (sin la query string)."""

    def __init__(self, app, proxy_hops: int = 0) -> None:
        super().__init__(app)
        self.proxy_hops = proxy_hops
        self._log = logging.getLogger("plazadata.acceso")

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        inicio = time.perf_counter()
        estado = 500
        try:
            respuesta = await call_next(request)
            estado = respuesta.status_code
            respuesta.headers["X-Request-ID"] = rid
            return respuesta
        finally:
            self._log.info("solicitud", extra={
                "metodo": request.method, "ruta": request.url.path, "estado": estado,
                "ms": round((time.perf_counter() - inicio) * 1000, 1), "ip": huella_ip(ip_cliente(request, self.proxy_hops)),
            })
            request_id_var.reset(token)
