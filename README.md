# PlazaData MVP

ETL + API + panel web con precios mayoristas del SIPSA-DANE (Central Mayorista de Antioquia).

## Correr en tu computador
1. Instalar dependencias:  `python -m pip install -r requirements.txt`
2. Copiar aquí el archivo `data.xlsx` (export del tablero del DANE).
3. Cargar los datos:       `python etl_sipsa.py data.xlsx`   (crea `sipsa.db`)
4. Iniciar el servidor:    `python -m uvicorn api:app --reload`
5. Abrir:                  http://127.0.0.1:8000

## Rutas de la API
- `GET /api/salud`                              estado y última semana cargada
- `GET /api/productos?q=papa`                   buscar productos
- `GET /api/precios/ultimo?producto=A&producto=B`   mín, máx, promedio y variación semanal
- `GET /api/precios/historico?producto=A&semanas=12` serie semanal
- Documentación interactiva automática: http://127.0.0.1:8000/docs

## Desplegar en Render (resumen)
- Servicio web (Python): Build `pip install -r requirements.txt` — Start `uvicorn api:app --host 0.0.0.0 --port $PORT`
- Variable de entorno `DATABASE_URL` con la URL de la base PostgreSQL.
- Cargar los datos una vez: ejecutar `python etl_sipsa.py data.xlsx` en tu computador con `DATABASE_URL` apuntando a la base de Render.

## Límites conocidos de esta versión
- La canasta y las alertas se guardan en el navegador (sin cuenta de usuario).
- Las alertas se muestran en el panel; el envío por correo no está implementado.
- La carga de datos es manual (descargar el Excel semanal y correr el ETL).
