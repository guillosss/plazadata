"""
Actualiza la base de datos con los precios semanales del servicio web OFICIAL del DANE (SIPSA).
Reemplaza la descarga manual del Excel: un solo comando trae las semanas nuevas.

Uso:
    python -m pip install -r requirements-actualizar.txt
    python actualizar_sipsa.py                          # pide los datos al DANE y los carga
    python actualizar_sipsa.py --desde-json archivo.json  # prueba sin red, con una respuesta guardada
    python actualizar_sipsa.py --guardar-json respuesta.json   # además guarda la respuesta del DANE

La base se define con la variable DATABASE_URL (si no existe, usa sipsa.db local).
Es seguro repetirlo: las filas que ya existen se actualizan, no se duplican.

Notas sobre el servicio (documentación del DANE, 2020, verificada en nov-2026):
  * Hay que llamar por https: con http el servidor redirige y la petición deja de ser SOAP.
  * Los campos terminan en «Kg» pero son PRECIOS por kilo (coinciden con el tablero del DANE).
  * 'fechaIni' es el sábado en que empieza la semana; la base usa el viernes de cierre (fechaIni + 6 días),
    igual que el Excel del tablero.
  * La respuesta incluye todos los mercados del país (~66 MB): tarda unos minutos.
"""
import argparse
import json
import logging

import pandas as pd

import etl_sipsa

URL = "https://appweb.dane.gov.co/sipsaWS/SrvSipsaUpraBeanService"
BINDING = "{http://servicios.sipsa.co.gov.dane/}SrvSipsaUpraPortBinding"
FUENTES = ["Medellín, Central Mayorista de Antioquia"]
CANASTA = ["Papa capira", "Tomate chonto regional", "Cebolla cabezona blanca", "Aguacate Hass"]

log = logging.getLogger("actualizar_sipsa")


def descargar():
    """Llama al método promediosSipsaSemanaMadr del servicio SOAP del DANE."""
    from zeep import Client
    from zeep.helpers import serialize_object
    from zeep.transports import Transport

    cliente = Client(URL + "?WSDL", transport=Transport(timeout=60, operation_timeout=900))
    servicio = cliente.create_service(BINDING, URL)   # fuerza https
    log.info("Pidiendo datos al DANE (puede tardar unos minutos)...")
    return serialize_object(servicio.promediosSipsaSemanaMadr())


def a_dataframe(registros, fuentes=FUENTES):
    """Convierte los registros del servicio al formato de columnas que ya usa el ETL."""
    df = pd.DataFrame(registros)
    df = df[df["fuenNombre"].isin(fuentes)].copy()
    inicio = pd.to_datetime(df["fechaIni"].astype(str).str[:10], errors="coerce")
    return pd.DataFrame({
        "FECHA": inicio + pd.Timedelta(days=6),
        "FUENTE": df["fuenNombre"].astype(str),
        "ARTÍCULO": df["artiNombre"].astype(str),
        "PROMEDIO": df["promedioKg"],
        "MÍNIMO": df["minimoKg"],
        "MÁXIMO": df["maximoKg"],
    })


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Actualiza la base con datos del servicio web del DANE")
    ap.add_argument("--desde-json", help="usar una respuesta guardada en lugar de llamar al DANE")
    ap.add_argument("--guardar-json", help="guardar la respuesta cruda del DANE en este archivo")
    args = ap.parse_args()

    if args.desde_json:
        log.info("Leyendo respuesta guardada: %s", args.desde_json)
        with open(args.desde_json, encoding="utf-8") as f:
            registros = json.load(f)
    else:
        registros = descargar()
        if args.guardar_json:
            with open(args.guardar_json, "w", encoding="utf-8") as f:
                json.dump(registros, f, default=str, ensure_ascii=False)
    log.info("Registros recibidos (todo el país): %d", len(registros))

    df = a_dataframe(registros)
    if df.empty:
        raise SystemExit("No hay registros de las fuentes configuradas: no se cargó nada.")
    datos = etl_sipsa.transformar(df)

    engine = etl_sipsa.conectar()
    etl_sipsa.cargar(engine, datos)
    print("\nPanel de prueba (última semana cargada):")
    for fila in etl_sipsa.panel(engine, CANASTA):
        print(" ", fila)


if __name__ == "__main__":
    main()
