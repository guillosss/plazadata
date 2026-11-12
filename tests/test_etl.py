from datetime import date

import pandas as pd
import pytest

from plazadata.db import crear_motor
from plazadata.etl.dane import DaneClient, ErrorServicioDane, a_dataframe, validar_registros
from plazadata.etl.load import cargar
from plazadata.etl.transform import DatosInvalidos, transformar
from plazadata.repositories import PreciosRepository

HOY = date(2026, 11, 11)


def _df(filas):
    return pd.DataFrame(filas, columns=["FECHA", "FUENTE", "ARTÍCULO", "PROMEDIO", "MÍNIMO", "MÁXIMO"])


def test_transformar_descarta_lo_invalido_y_lo_cuenta():
    df, inf = transformar(_df([
        ["2026-10-30", "M", "Papa", 100, 90, 110],            # válida
        ["2026-11-06", "M", "Papa", 110, 100, 120],           # válida
        ["Filtros aplicados", "M", "Papa", 1, 1, 1],          # pie de página del export
        ["2026-11-06", "M", "Yuca", "abc", 1, 2],             # precio no numérico
        ["2026-11-06", "M", "Ajo", 100, 200, 300],            # mínimo > promedio
        ["2026-11-06", "M", "Oro", 9e9, 9e9, 9e9],            # fuera de rango razonable
        ["2030-01-01", "M", "Futuro", 100, 90, 110],          # fecha futura
        ["2026-11-06", "M", "Papa", 111, 100, 120],           # duplicada: gana la última
    ]), hoy=HOY)
    assert (inf.leidas, inf.validas) == (8, 2)
    assert (inf.sin_fecha, inf.sin_precio, inf.precios_inconsistentes, inf.fuera_de_rango, inf.fechas_futuras, inf.duplicadas) == (1, 1, 1, 1, 1, 1)
    assert df[df["FECHA"] == "2026-11-06"]["PROMEDIO"].iloc[0] == 111


def test_transformar_detecta_semanas_faltantes():
    _, inf = transformar(_df([["2026-07-31", "M", "Papa", 1, 1, 1], ["2026-08-14", "M", "Papa", 1, 1, 1]]), hoy=HOY)
    assert inf.huecos == [(date(2026, 7, 31), date(2026, 8, 14))]


def test_transformar_exige_las_columnas():
    with pytest.raises(DatosInvalidos):
        transformar(pd.DataFrame({"FECHA": []}))


def test_cargar_es_idempotente(tmp_path):
    engine = crear_motor(f"sqlite:///{tmp_path / 'etl.db'}")
    df, _ = transformar(_df([["2026-10-30", "M", "Papa", 100, 90, 110], ["2026-11-06", "M", "Papa", 110, 100, 120]]), hoy=HOY)
    assert cargar(engine, df) == 2
    df2 = df.copy(); df2.loc[df2["FECHA"] == "2026-11-06", "PROMEDIO"] = 115     # una corrección posterior del DANE
    assert cargar(engine, df2) == 2
    repo = PreciosRepository(engine)
    assert repo.resumen() == ("2026-11-06", 2)                                   # no se duplicó
    assert repo.historico("Papa", "%M%", 12)[-1][1] == 115                       # y se actualizó el valor


REGISTRO = {"artiNombre": "Papa capira", "fuenNombre": "Medellín, Central Mayorista de Antioquia",
            "fechaIni": "2026-10-31 00:00:00-05:00", "promedioKg": "3598", "minimoKg": "3000", "maximoKg": "3800"}


def test_cliente_dane_reintenta_con_retroceso_exponencial():
    intentos, esperas = {"n": 0}, []

    def llamada(*_):
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise ConnectionError("caída simulada")
        return [REGISTRO]

    assert DaneClient(llamada=llamada, dormir=esperas.append).obtener_semanal() == [REGISTRO]
    assert intentos["n"] == 3 and len(esperas) == 2 and esperas[1] > esperas[0]


def test_cliente_dane_agota_reintentos():
    def llamada(*_):
        raise TimeoutError("sin red")

    with pytest.raises(ErrorServicioDane) as info:
        DaneClient(reintentos=2, llamada=llamada, dormir=lambda s: None).obtener_semanal()
    assert isinstance(info.value.__cause__, TimeoutError)


def test_cliente_dane_exige_https_y_valida_la_respuesta():
    with pytest.raises(ValueError):
        DaneClient(url="http://appweb.dane.gov.co/sipsaWS")
    for mala in ([], "texto", [{"otro": 1}]):
        with pytest.raises(ValueError):
            validar_registros(mala)
    with pytest.raises(ErrorServicioDane):       # una respuesta con forma inesperada también cuenta como fallo
        DaneClient(reintentos=1, llamada=lambda *_: [{"otro": 1}], dormir=lambda s: None).obtener_semanal()


def test_a_dataframe_filtra_fuentes_y_pasa_al_viernes_de_cierre():
    df = a_dataframe([REGISTRO, {**REGISTRO, "fuenNombre": "Bogotá, Corabastos"}])
    assert len(df) == 1
    assert df["FECHA"].iloc[0] == pd.Timestamp("2026-11-06")      # sábado 31 oct + 6 días
