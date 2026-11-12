"""Actualiza la base con los precios semanales del servicio web OFICIAL del DANE (SIPSA).

Uso:
    python -m pip install -r requirements-actualizar.txt
    python actualizar_sipsa.py                              # pide los datos al DANE y los carga
    python actualizar_sipsa.py --desde-json archivo.json     # prueba sin red, con una respuesta guardada
    python actualizar_sipsa.py --guardar-json respuesta.json  # además guarda la respuesta cruda
Carga la Central Mayorista y la Plaza Minorista de Medellín. Es seguro repetirlo: no duplica filas.
"""
from __future__ import annotations

import argparse
import json
import sys

from plazadata.config import Settings
from plazadata.db import crear_motor
from plazadata.etl.dane import DaneClient, ErrorServicioDane, a_dataframe, validar_registros
from plazadata.etl.load import cargar
from plazadata.etl.transform import transformar
from plazadata.logging_conf import configurar_logging
from plazadata.repositories import PreciosRepository
from plazadata.services import PreciosService


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Actualiza la base con datos del servicio web del DANE")
    ap.add_argument("--desde-json", help="usar una respuesta guardada en lugar de llamar al DANE")
    ap.add_argument("--guardar-json", help="guardar la respuesta cruda del DANE en este archivo")
    args = ap.parse_args(argv[1:])
    settings = Settings.from_env()
    configurar_logging(settings.log_level)

    try:
        if args.desde_json:
            with open(args.desde_json, encoding="utf-8") as f:
                registros = json.load(f)
            validar_registros(registros)
        else:
            registros = DaneClient().obtener_semanal()
            if args.guardar_json:
                with open(args.guardar_json, "w", encoding="utf-8") as f:
                    json.dump(registros, f, default=str, ensure_ascii=False)
    except (ErrorServicioDane, ValueError, OSError) as exc:
        print(f"No se pudieron obtener los datos: {exc}", file=sys.stderr)
        return 1

    df = a_dataframe(registros)
    if df.empty:
        print("No hay registros de las fuentes configuradas: no se cargó nada.", file=sys.stderr)
        return 1
    datos, informe = transformar(df)
    engine = crear_motor(settings.database_url)
    filas = cargar(engine, datos)
    print(f"Registros recibidos (todo el país): {len(registros)} | válidos de Medellín: {informe.validas} | "
          f"semanas: {informe.semanas} | cargados: {filas}")
    if informe.huecos:
        print("Semanas faltantes entre:", ", ".join(f"{a} y {b}" for a, b in informe.huecos))
    print("\nÚltima semana (Central Mayorista):")
    for p in PreciosService(PreciosRepository(engine)).ultimos(None, "mayorista"):
        if p.disponible:
            print(f"  {p.producto:26s} mín {p.minimo:>8,.0f}  máx {p.maximo:>8,.0f}  promedio {p.promedio:>8,.0f}  variación {p.variacion_pct}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
