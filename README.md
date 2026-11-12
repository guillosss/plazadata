# PlazaData MVP

Panel web para restaurantes con los precios del SIPSA-DANE de la **Central Mayorista** y la **Plaza Minorista «José María Villa»** de Medellín.
Fuente de los datos: DANE, SIPSA (información pública).

## Correr en tu computador
```
python -m pip install -r requirements.txt
python -m uvicorn api:app --reload
```
Abrir http://127.0.0.1:8000. Si la base está vacía, la aplicación carga sola `datos/sipsa_medellin.csv`.
Si ya tenías un `sipsa.db` antiguo, bórralo y reinicia.

## Pruebas
```
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
77 pruebas: reglas de dominio, validación de entradas, ETL, API y seguridad (inyección, límites, autenticación, cabeceras).

## Configuración (variables de entorno)
Copia `.env.example` como `.env` para desarrollo. Nunca subas `.env`.

| Variable | Para qué | Por defecto |
|---|---|---|
| `DATABASE_URL` | Base de datos | `sqlite:///sipsa.db` |
| `ADMIN_KEY` | Clave del resumen privado (mínimo 16 caracteres) | sin definir = desactivado |
| `ENTORNO` | `produccion` oculta `/docs` | `desarrollo` |
| `PROXY_HOPS` | Proxies de confianza delante de la app | `0` |
| `ALLOWED_HOSTS` | Dominios permitidos, separados por comas | cualquiera |
| `LOG_LEVEL` | Nivel de registro | `INFO` |

Generar una clave: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Resultados de uso (indicadores del piloto)
Abre `/admin` y escribe la clave. Muestra usuarios por semana, eventos y comentarios.
La medición es anónima: un identificador aleatorio por navegador, sin nombre, correo ni IP.

## Actualizar los precios desde el servicio oficial del DANE
```
python -m pip install -r requirements-actualizar.txt
python actualizar_sipsa.py
```
Carga ambos mercados, reintenta si el DANE falla y no duplica filas.

## Publicar en Render
1. Subir el repositorio a GitHub (incluye `render.yaml`).
2. En render.com: **New → Blueprint** → elegir el repositorio → **Apply**.
3. La clave de administrador la genera Render: verla en el servicio → **Environment** → `ADMIN_KEY`.
4. Verificar `PROXY_HOPS` como indica `docs/ARQUITECTURA_Y_SEGURIDAD.md`.

El servicio gratuito se duerme tras 15 minutos sin uso y la base gratuita expira a los 30 días.

## Arquitectura y seguridad
Ver [`docs/ARQUITECTURA_Y_SEGURIDAD.md`](docs/ARQUITECTURA_Y_SEGURIDAD.md): capas, hallazgos de la revisión, correspondencia con OWASP Top 10, lo que no se implementó y los riesgos pendientes.

## Límites conocidos
- La canasta y las alertas se guardan en el navegador (sin cuenta de usuario).
- Las alertas se muestran en el panel; el envío por correo no está implementado.
- La unidad de los huevos (por unidad) se infirió por la magnitud del precio; confirmar con el DANE.
- Entre mercados, algunos productos tienen presentaciones distintas: comparar con cautela.
