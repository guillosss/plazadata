"""Páginas y archivos de la aplicación instalable."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)


def _static(request: Request, nombre: str, **kw) -> FileResponse:
    return FileResponse(request.app.state.settings.ruta_static / nombre, **kw)


@router.get("/")
def panel(request: Request) -> FileResponse:
    return _static(request, "index.html", headers={"Cache-Control": "no-cache"})


@router.get("/admin")
def admin(request: Request) -> FileResponse:
    return _static(request, "admin.html")


@router.get("/manifest.webmanifest")
def manifiesto(request: Request) -> FileResponse:
    return _static(request, "manifest.webmanifest", media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker(request: Request) -> FileResponse:
    # Debe servirse desde la raíz para controlar toda la app, y sin caché para que las actualizaciones lleguen.
    return _static(request, "sw.js", media_type="text/javascript", headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})
