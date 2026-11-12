# PlazaData MVP

ETL + API + panel web con precios mayoristas del SIPSA-DANE (Central Mayorista de Antioquia).
Fuente de los datos: DANE, SIPSA (información pública). Archivo incluido en `datos/`.

## Correr en tu computador
1. `python -m pip install -r requirements.txt`
2. `python -m uvicorn api:app --reload`
3. Abrir http://127.0.0.1:8000

Al iniciar, si la base está vacía, la API carga sola los datos de `datos/`. No hace falta correr el ETL a mano
(también se puede: `python etl_sipsa.py datos/sipsa_central_mayorista_2026.xlsx`).

## Rutas de la API
- `GET /api/salud`                                   estado y última semana cargada
- `GET /api/productos?q=papa`                        buscar productos
- `GET /api/precios/ultimo?producto=A&producto=B`    mín, máx, promedio, variación semanal
- `GET /api/precios/historico?producto=A&semanas=12` serie semanal
- Documentación automática: `/docs`

## Publicar en Render (gratis)
1. Subir este repositorio a GitHub (incluye `render.yaml`).
2. En render.com: **New → Blueprint** → elegir el repositorio → **Apply**.
3. Esperar a que termine el despliegue (unos minutos) y abrir la URL `https://plazadata-xxxx.onrender.com`.
   - El servicio gratuito se duerme tras 15 minutos sin uso: la primera visita tarda hasta un minuto en despertar.
   - La base gratuita expira a los 30 días de su creación: hacer copia (`pg_dump`) antes de esa fecha.
4. Para actualizar los datos: reemplazar el Excel de `datos/` por el nuevo y reiniciar con la base vacía
   (o correr `python etl_sipsa.py archivo.xlsx` con `DATABASE_URL` apuntando a la base).

## Actualizar los precios desde el servicio oficial del DANE
El DANE publica un servicio web (SOAP) con los precios semanales. El script `actualizar_sipsa.py` lo consulta y carga
las semanas nuevas, sin descargar Excel:

    python -m pip install -r requirements-actualizar.txt
    python actualizar_sipsa.py                  # usa DATABASE_URL, o sipsa.db si no existe
    python actualizar_sipsa.py --guardar-json respuesta.json   # además guarda la respuesta cruda

- Debe llamarse por https (con http el servidor redirige y la petición deja de ser SOAP).
- La respuesta incluye todo el país (~66 MB); tarda unos minutos.
- Es seguro repetirlo: no duplica filas.
- Verificado en nov-2026: los 8.998 registros del Excel del tablero coinciden exactamente con los del servicio.
- `.github/workflows/actualizar_datos.yml` permite ejecutarlo desde GitHub (a mano o programado cada sábado).

## Límites conocidos de esta versión
- La canasta y las alertas se guardan en el navegador (sin cuenta de usuario).
- Las alertas se muestran en el panel; el envío por correo no está implementado.
- La carga de datos nuevos se hace con un comando (`actualizar_sipsa.py`); aún no corre sola.
