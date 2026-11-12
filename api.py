"""Punto de entrada para el servidor:  python -m uvicorn api:app --reload

La aplicación vive en el paquete ``plazadata`` (ver ``plazadata/main.py``).
"""
from plazadata.main import create_app

app = create_app()
