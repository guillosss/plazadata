"""Lógica de negocio. No sabe de HTTP ni de SQL: recibe repositorios por inyección (fácil de probar)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Sequence

from .domain import (CANASTA_DEFECTO, EVENTOS, MAX_PRODUCTOS_POR_CONSULTA, MERCADOS, EventoNoPermitido,
                     obtener_mercado, unidad_de, variacion_pct)
from .repositories import PreciosRepository, UsoRepository
from .schemas import (ComentarioIn, ComentarioOut, ComparacionOut, EventoConteo, EventoIn, MercadoOut, PrecioMercado,
                      PrecioOut, PuntoHistorico, ResumenUso, Salud, SemanaUso, UsuarioUso)

UTC_COLOMBIA = timedelta(hours=-5)   # Colombia no tiene horario de verano


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PreciosService:
    def __init__(self, repo: PreciosRepository) -> None:
        self._repo = repo

    def salud(self) -> Salud:
        ultima, filas = self._repo.resumen()
        return Salud(estado="ok", ultima_fecha=ultima, filas=filas)

    def mercados(self) -> list[MercadoOut]:
        """Solo los mercados que tienen datos (el panel muestra el selector si hay más de uno)."""
        salida: list[MercadoOut] = []
        for m in MERCADOS.values():
            ultima, n = self._repo.resumen_mercado(m.patron)
            if ultima:
                salida.append(MercadoOut(clave=m.clave, etiqueta=m.etiqueta, ultima_fecha=ultima, productos=n))
        return salida

    def buscar_productos(self, consulta: str, limite: int, mercado: Optional[str]) -> list[str]:
        patron = obtener_mercado(mercado).patron if mercado else None
        return self._repo.buscar_productos(consulta.strip(), limite, patron)

    def ultimos(self, productos: Optional[Sequence[str]], mercado: str) -> list[PrecioOut]:
        """Último precio y variación semanal de cada producto pedido, en el orden recibido y sin repetidos."""
        m = obtener_mercado(mercado)
        nombres = list(dict.fromkeys(p.strip() for p in (productos or CANASTA_DEFECTO) if p and p.strip()))
        nombres = nombres[:MAX_PRODUCTOS_POR_CONSULTA]
        ultima_mercado, _ = self._repo.resumen_mercado(m.patron)
        por_producto = self._repo.ultimos_dos(nombres, m.patron)
        salida: list[PrecioOut] = []
        for nombre in nombres:
            u = unidad_de(nombre)
            filas = por_producto.get(nombre)
            if not filas:
                salida.append(PrecioOut(producto=nombre, disponible=False, mercado=m.clave, unidad=u.etiqueta, unidad_codigo=u.codigo))
                continue
            fecha, minimo, maximo, promedio = filas[0]
            anterior = filas[1] if len(filas) > 1 else None
            salida.append(PrecioOut(
                producto=nombre, disponible=True, mercado=m.clave, unidad=u.etiqueta, unidad_codigo=u.codigo,
                fecha=fecha, minimo=minimo, maximo=maximo, promedio=promedio,
                promedio_anterior=anterior[3] if anterior else None,
                fecha_anterior=anterior[0] if anterior else None,
                variacion_pct=variacion_pct(promedio, anterior[3] if anterior else None),
                # El último dato del producto es anterior a la última semana cargada del mercado.
                desactualizado=bool(ultima_mercado and fecha < ultima_mercado),
            ))
        return salida

    def historico(self, producto: str, semanas: int, mercado: str) -> list[PuntoHistorico]:
        m = obtener_mercado(mercado)
        return [PuntoHistorico(fecha=f, promedio=p, minimo=mn, maximo=mx)
                for f, p, mn, mx in self._repo.historico(producto.strip(), m.patron, semanas)]

    def comparar(self, producto: str) -> ComparacionOut:
        """Compara el último promedio de la Plaza Minorista con el de la Central Mayorista (misma semana)."""
        nombre = producto.strip()
        datos: dict[str, Optional[PrecioMercado]] = {}
        for clave in ("mayorista", "minorista"):
            r = self.ultimos([nombre], clave)[0]
            datos[clave] = PrecioMercado(promedio=r.promedio, fecha=r.fecha) if r.disponible and r.promedio and r.fecha else None
        may, mino = datos["mayorista"], datos["minorista"]
        comparable = bool(may and mino and may.fecha == mino.fecha and may.promedio)
        return ComparacionOut(
            producto=nombre, unidad=unidad_de(nombre).etiqueta, mayorista=may, minorista=mino, comparable=comparable,
            diferencia_pct=variacion_pct(mino.promedio, may.promedio) if comparable and may and mino else None,
        )


class UsoService:
    """Medición de uso anónima: no recibe ni guarda nombre, correo, IP ni ubicación."""

    def __init__(self, repo: UsoRepository, reloj: Callable[[], datetime] = ahora_utc) -> None:
        self._repo = repo
        self._reloj = reloj

    def registrar_evento(self, e: EventoIn) -> None:
        if e.evento not in EVENTOS:
            raise EventoNoPermitido("Evento no permitido")
        self._repo.insertar_evento(e.cliente, e.evento, e.detalle, self._reloj())

    def registrar_comentario(self, c: ComentarioIn) -> None:
        self._repo.insertar_comentario(c.cliente, c.pantalla, c.texto, self._reloj())

    @staticmethod
    def _hora_colombia(valor: Any) -> datetime:
        if isinstance(valor, str):
            valor = datetime.fromisoformat(valor)
        return valor + UTC_COLOMBIA

    def resumen(self) -> ResumenUso:
        """Usuarios por semana (indicador «uso semanal por piloto»), eventos y comentarios."""
        por_semana: dict[str, dict[str, Any]] = defaultdict(lambda: {"usuarios": set(), "aperturas": 0})
        por_evento: dict[str, int] = defaultdict(int)
        por_usuario: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"primer_uso": None, "ultimo_uso": None, "dias": set(), "semanas": set(), "eventos": 0})
        eventos = self._repo.eventos()
        for cliente, evento, creado in eventos:
            t = self._hora_colombia(creado)
            lunes = (t - timedelta(days=t.weekday())).date().isoformat()
            por_semana[lunes]["usuarios"].add(cliente)
            if evento == "abrir_app":
                por_semana[lunes]["aperturas"] += 1
            por_evento[evento] += 1
            u = por_usuario[cliente]
            u["primer_uso"] = u["primer_uso"] or t
            u["ultimo_uso"] = t
            u["dias"].add(t.date().isoformat())
            u["semanas"].add(lunes)
            u["eventos"] += 1
        fmt = "%Y-%m-%d %H:%M"
        return ResumenUso(
            usuarios_unicos=len(por_usuario),
            eventos_total=len(eventos),
            por_semana=[SemanaUso(semana_desde=k, usuarios=len(v["usuarios"]), aperturas=v["aperturas"]) for k, v in sorted(por_semana.items())],
            por_evento=[EventoConteo(evento=k, n=v) for k, v in sorted(por_evento.items(), key=lambda x: -x[1])],
            por_usuario=[UsuarioUso(cliente=k[:8], primer_uso=v["primer_uso"].strftime(fmt), ultimo_uso=v["ultimo_uso"].strftime(fmt),
                                    dias_activos=len(v["dias"]), semanas_activas=len(v["semanas"]), eventos=v["eventos"])
                         for k, v in sorted(por_usuario.items(), key=lambda x: x[1]["primer_uso"])],
            comentarios=[ComentarioOut(fecha=self._hora_colombia(c).strftime(fmt), pantalla=p, texto=x) for p, x, c in self._repo.comentarios()],
            nota="Horas en Colombia (UTC-5). Los identificadores son aleatorios y no permiten saber quién es cada persona.",
        )
