"""Carga un archivo del DANE (CSV o Excel) a la base de datos.

Uso:  python etl_sipsa.py [archivo]      (por defecto: datos/sipsa_medellin.csv)
La base se define con DATABASE_URL (si no existe, usa sipsa.db local). Es seguro repetirlo.
"""
from __future__ import annotations

import sys

from plazadata.config import Settings
from plazadata.db import crear_motor
from plazadata.etl.load import cargar
from plazadata.etl.transform import leer_archivo, transformar
from plazadata.logging_conf import configurar_logging


def main(argv: list[str]) -> int:
    settings = Settings.from_env()
    configurar_logging(settings.log_level)
    ruta = argv[1] if len(argv) > 1 else "datos/sipsa_medellin.csv"
    df, informe = transformar(leer_archivo(ruta))
    filas = cargar(crear_motor(settings.database_url), df)
    print(f"Leídas: {informe.leidas} | válidas: {informe.validas} | semanas: {informe.semanas} | cargadas: {filas}")
    if informe.huecos:
        print("Semanas faltantes entre:", ", ".join(f"{a} y {b}" for a, b in informe.huecos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
