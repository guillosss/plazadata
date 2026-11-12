# Arquitectura y seguridad de PlazaData

## 1. Arquitectura por capas

```
api.py                      punto de entrada (uvicorn api:app)
plazadata/
  config.py                 configuración leída del entorno (sin secretos en el código)
  logging_conf.py           registro en JSON con identificador de solicitud
  db.py                     motor y esquema (SQLAlchemy Core; SQLite local, PostgreSQL en la nube)
  domain.py                 reglas puras: mercados, unidades, variación, lista cerrada de eventos
  schemas.py                contratos Pydantic: valida TODA entrada y define las salidas
  repositories.py           acceso a datos: aquí vive todo el SQL, siempre parametrizado
  services.py               lógica de negocio: no sabe de HTTP ni de SQL
  security.py               límite de ritmo, IP del cliente, autenticación del administrador, cabeceras
  errors.py                 manejo de errores predecible (sin trazas hacia el cliente)
  api/                      rutas delgadas: validan, llaman al servicio y responden
  etl/                      transform.py (validación), load.py (carga idempotente), dane.py (cliente SOAP con reintentos)
  main.py                   create_app(settings): arma la aplicación e inyecta las dependencias
tests/                      77 pruebas (unitarias, integración y seguridad)
```

Regla de dependencias: `api → services → repositories → db`. El dominio no depende de nada.
`create_app(settings)` recibe la configuración por parámetro: cada prueba crea su propia aplicación con una base temporal.

## 2. Hallazgos de la revisión y cómo se resolvieron

| # | Hallazgo en la versión anterior | Riesgo | Solución |
|---|---|---|---|
| 1 | La clave de administrador viajaba en la URL (`?clave=`) | Alto: queda en registros del servidor, historial y cabecera Referer | Cabecera `X-Admin-Key`; la URL ya no se acepta; la página no guarda la clave |
| 2 | Sin protección contra fuerza bruta en el resumen privado | Alto | 5 intentos fallidos por IP → bloqueo de 15 minutos; clave mínima de 16 caracteres |
| 3 | Límite de ritmo por el identificador que envía el cliente | Medio: se evadía rotando el identificador | Límite por IP, con la IP obtenida solo de proxies de confianza |
| 4 | El diccionario del límite de ritmo crecía sin tope | Medio: agotamiento de memoria | Estructura acotada que descarta las claves más antiguas, segura entre hilos |
| 5 | Sin cabeceras de seguridad; scripts y estilos en línea | Medio: XSS, clickjacking | CSP estricta sin `unsafe-inline`, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, HSTS; JS y CSS en archivos propios |
| 6 | Valores de `localStorage` insertados en el HTML sin validar | Bajo: XSS local | Todo lo leído del navegador se valida por tipo, tamaño y rango |
| 7 | Comodines `%` y `_` de la búsqueda controlados por el usuario | Bajo: consultas amplias | Escape de comodines (`LIKE ... ESCAPE`) |
| 8 | Sin límite de tamaño del cuerpo de las solicitudes | Medio: agotamiento de memoria | Rechazo por `Content-Length` (8 KB) antes de leer el cuerpo |
| 9 | Los errores de validación devolvían el valor recibido | Bajo: reflejo de entradas | Respuesta con el campo y el mensaje, sin el valor |
| 10 | Una consulta por producto (N+1) | Rendimiento | Una sola consulta con función de ventana |
| 11 | Documentación interactiva pública | Bajo: exposición de la superficie | Oculta con `ENTORNO=produccion` |
| 12 | Dependencias sin versión | Medio: cambios incompatibles, cadena de suministro | Rangos por versión mayor; pruebas en integración continua |
| 13 | Análisis de XML del DANE con valores por defecto | Medio: XXE, expansión de entidades | Sin DTD, sin entidades y sin recursos externos; https obligatorio; validación de la forma de la respuesta |
| 14 | Sin reintentos ante fallos del DANE o de la base | Resiliencia | Reintentos con retroceso exponencial; `pool_pre_ping`; 503 con `Retry-After`; el panel muestra los últimos datos guardados |
| 15 | Registros de texto sin correlación | Auditoría | JSON con `request_id`, eventos de seguridad e IP convertida en huella no reversible |
| 16 | Todo en un archivo, sin pruebas | Mantenibilidad | Capas con inyección de dependencias y 77 pruebas |

## 3. Correspondencia con OWASP Top 10 (2021)

| Categoría | Estado |
|---|---|
| A01 Control de acceso | El único recurso privado (`/api/admin/*`) exige clave en cabecera, con bloqueo por intentos. El resto son datos públicos del DANE. |
| A02 Fallos criptográficos | No se guardan contraseñas ni datos personales. HTTPS lo da el proveedor; se envía HSTS. Comparación de la clave en tiempo constante. |
| A03 Inyección | SQL siempre con parámetros enlazados; comodines de LIKE escapados; salida HTML escapada; CSP sin scripts en línea. |
| A04 Diseño inseguro | Listas cerradas (eventos, mercados), límites de tamaño y de ritmo, mínimo privilegio en los flujos de GitHub. |
| A05 Configuración insegura | Cabeceras de seguridad, documentación oculta en producción, sin CORS (mismo origen), hosts permitidos opcionales. |
| A06 Componentes vulnerables | Rangos de versión. Pendiente: archivo de bloqueo con hashes y revisión periódica (`pip-audit`). |
| A07 Autenticación | Sin cuentas de usuario. Clave de administrador de alta entropía generada por el proveedor. |
| A08 Integridad de datos | Los datos del DANE se validan (estructura, rangos, fechas) antes de cargarlos; carga en una transacción. |
| A09 Registro y monitoreo | Registro estructurado de accesos y eventos de seguridad. Pendiente: alertas automáticas. |
| A10 SSRF | La única URL externa es fija (servicio del DANE) y se exige https. |

## 4. Lo que NO se implementó, y por qué

- **Cuentas, contraseñas (bcrypt/Argon2) y JWT.** La aplicación no tiene usuarios: la canasta vive en el navegador. Añadir cuentas hoy
  aumentaría la superficie de ataque y obligaría a tratar datos personales (Ley 1581 de 2012) sin que el producto lo necesite.
  Cuando se necesiten: Argon2id para contraseñas, sesiones en cookie `HttpOnly; Secure; SameSite=Lax` y protección CSRF.
- **Base de datos asíncrona.** Las rutas son funciones síncronas que FastAPI ejecuta en un grupo de hilos, así que no bloquean el
  bucle de eventos. Con el volumen de un piloto, un motor asíncrono añadiría complejidad sin beneficio medible.
- **Modelos ORM completos.** Se usa SQLAlchemy Core con consultas parametrizadas, que cumple el objetivo de evitar inyección.
- **Librerías de registro adicionales.** El registro en JSON se hace con la biblioteca estándar para no sumar dependencias.

## 5. Riesgos pendientes

1. **`PROXY_HOPS` en Render sin verificar.** Si el valor no coincide con los proxies reales, el límite de ritmo puede agrupar
   usuarios distintos o dejarse engañar. Verificación: abrir la app desde dos dispositivos y comprobar en los registros que el
   campo `ip` (una huella) es distinto en cada uno.
2. **El límite de ritmo está en memoria.** Con más de un proceso o tras un reinicio, el conteo se pierde. Suficiente para un piloto.
3. **Sin migraciones de esquema.** Las tablas se crean si faltan. Para cambios de esquema futuros: Alembic.
4. **La tabla de eventos crece sin límite.** Definir un tiempo de retención antes de un uso amplio.
5. **Los comentarios pueden contener datos personales** si alguien los escribe. La pantalla lo desaconseja; revisar antes de compartirlos.
6. **Supuestos de datos:** la unidad de los huevos (por unidad) se infirió por la magnitud del precio.
