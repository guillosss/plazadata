"use strict";
// Lógica del panel de PlazaData (archivo aparte: la CSP no permite scripts en línea).
// ---------------------------------------------------------------- utilidades
const SUGERIDOS = [
  ["Verduras y hortalizas", ["Papa capira", "Papa criolla limpia", "Tomate chonto regional", "Cebolla cabezona blanca", "Cebolla junca", "Zanahoria larga vida", "Pimentón", "Ajo", "Cilantro", "Lechuga Batavia"]],
  ["Frutas y plátano", ["Aguacate Hass", "Limón Tahití", "Limón común", "Plátano hartón verde", "Banano criollo", "Naranja Valencia"]],
  ["Granos y despensa", ["Arroz de primera", "Fríjol cargamanto rojo", "Lenteja importada", "Aceite girasol", "Azúcar morena"]],
  ["Carnes, pollo, pescado y huevos", ["Carne de res, sobrebarriga", "Carne de res, costilla", "Carne de cerdo, costilla", "Pechuga de pollo", "Pollo entero congelado sin vísceras", "Tilapia roja entera congelada", "Huevo rojo A"]],
];
const ETIQUETA = { mayorista: "Central Mayorista", minorista: "Plaza Minorista" };
const $ = (s) => document.querySelector(s);
const cop = (n) => "$ " + Math.round(n).toLocaleString("es-CO");
const pct = (n) => n.toLocaleString("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
const fechaCorta = (iso) => { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };
const mesCorto = (iso) => { const [, m, d] = iso.split("-"); return `${parseInt(d)} ${["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"][parseInt(m) - 1]}`; };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
const leer = (k, def) => { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? def; } catch (e) { return def; } };
// Lo guardado en el navegador se trata como entrada no confiable: se valida tipo, tamaño y rango antes de usarlo.
const esTextoCorto = (v) => typeof v === "string" && v.length > 0 && v.length <= 200;
const leerCanasta = () => { const v = leer("pd_canasta", null); return Array.isArray(v) ? [...new Set(v.filter(esTextoCorto))].slice(0, 40) : null; };
const umbralValido = (v) => { const n = Number(v); return Number.isFinite(n) ? Math.min(100, Math.max(0.5, n)) : 5; };
const leerAlertas = () => {
  const v = leer("pd_alertas", {}), limpio = {};
  if (v && typeof v === "object" && !Array.isArray(v)) Object.keys(v).slice(0, 60).forEach((k) => {
    if (esTextoCorto(k) && v[k] && typeof v[k] === "object") limpio[k] = { umbral: umbralValido(v[k].umbral), activa: v[k].activa === true };
  });
  return limpio;
};
const leerCliente = () => { const v = leer("pd_cliente", null); return (typeof v === "string" && /^[A-Za-z0-9-]{8,64}$/.test(v)) ? v : null; };
const leerMercado = () => { const v = leer("pd_mercado", "mayorista"); return (typeof v === "string" && /^[a-z]{1,20}$/.test(v)) ? v : "mayorista"; };
const nuevoId = () => (self.crypto && crypto.randomUUID) ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2));

// ---------------------------------------------------------------- estado (se guarda en este navegador, sin cuenta)
const estado = {
  vista: "panel",
  mercado: leerMercado(),
  mercados: [],
  canasta: leerCanasta(),          // null = primera vez → se guía la elección de insumos
  alertas: leerAlertas(),            // { producto: { umbral: 5, activa: true } }
  cliente: leerCliente() || (() => { const id = nuevoId(); guardar("pd_cliente", id); return id; })(),
  producto: null, semanas: 12, precios: [], borrador: new Set(), sinConexion: false,
};
estado.producto = (estado.canasta && estado.canasta[0]) || null;

// Medición de uso anónima: solo eventos de una lista cerrada, con un identificador aleatorio.
function registrar(evento, detalle) {
  try {
    fetch("/api/evento", { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
      body: JSON.stringify({ cliente: estado.cliente, evento, detalle: detalle ? String(detalle).slice(0, 200) : null }) }).catch(() => {});
  } catch (e) {}
}

async function api(ruta) {
  const r = await fetch(ruta);
  // Sin conexión si el service worker entregó una copia guardada o si el dispositivo informa que no hay red.
  estado.sinConexion = r.headers.get("X-Desde-Cache") === "1" || navigator.onLine === false;
  if (!r.ok) throw new Error("Error " + r.status);
  return r.json();
}
const bannerConexion = () => estado.sinConexion ? '<div class="aviso ambar">Sin conexión: se muestran los últimos datos guardados en este dispositivo.</div>' : "";

function tendencia(p) {
  if (p.variacion_pct === null || p.variacion_pct === undefined) return '<span class="igual">–</span>';
  const v = p.variacion_pct;
  if (v > 0) return `<span class="sube">↑ ${pct(v)}</span>`;
  if (v < 0) return `<span class="baja">↓ ${pct(Math.abs(v))}</span>`;
  return `<span class="igual">→ ${pct(0)}</span>`;
}
function alertasActivas() {
  return estado.precios.filter((p) => {
    const a = estado.alertas[p.producto];
    return p.disponible && !p.desactualizado && a && a.activa && a.umbral > 0 && p.variacion_pct !== null && Math.abs(p.variacion_pct) > a.umbral;
  });
}
function selectorMercado() {
  if (estado.mercados.length < 2) return "";
  return '<div class="seg" role="group" aria-label="Mercado">' + estado.mercados.map((m) =>
    `<button class="chip ${estado.mercado === m.clave ? "act" : ""}" data-mercado="${m.clave}">${esc(m.etiqueta)}</button>`).join("") + "</div>";
}
function ligarSelectorMercado(despues) {
  document.querySelectorAll("[data-mercado]").forEach((b) => b.addEventListener("click", () => {
    if (estado.mercado === b.dataset.mercado) return;
    estado.mercado = b.dataset.mercado; guardar("pd_mercado", estado.mercado); registrar("cambiar_mercado", estado.mercado); despues();
  }));
}
const etiquetaMercado = () => ETIQUETA[estado.mercado] || estado.mercado;

async function cargarPrecios() {
  if (!estado.canasta || !estado.canasta.length) { estado.precios = []; return; }
  const qs = estado.canasta.map((p) => "producto=" + encodeURIComponent(p)).join("&");
  estado.precios = await api(`/api/precios/ultimo?${qs}&mercado=${encodeURIComponent(estado.mercado)}`);
}

// ---------------------------------------------------------------- vista: canasta (primer uso y edición)
function vistaCanasta() {
  const inicio = estado.canasta === null;
  const sugeridos = new Set(SUGERIDOS.flatMap((g) => g[1]));
  const extras = () => [...estado.borrador].filter((n) => !sugeridos.has(n));
  const chip = (n) => `<button class="opcion ${estado.borrador.has(n) ? "sel" : ""}" data-n="${esc(n)}">${esc(n)}</button>`;
  let h = `<h1>${inicio ? "Arma tu canasta" : "Mi canasta"}</h1>
    <p class="sub">Elige los insumos que más compras${inicio ? " (con 5 o más verás mejor tus precios)" : ""}. Podrás cambiarlos cuando quieras.</p>`;
  SUGERIDOS.forEach(([g, items]) => { h += `<h2>${esc(g)}</h2><div class="grupo">${items.map(chip).join("")}</div>`; });
  h += `<div id="extras"></div>
    <h2>¿No ves tu insumo?</h2>
    <input class="campo" id="buscar" list="opciones" placeholder="Escribe para buscar (ej. zanahoria, panela)" autocomplete="off" aria-label="Buscar insumo">
    <datalist id="opciones"></datalist>
    <button class="btn suave" id="btnAgregar">+ Agregar a mi canasta</button>
    <button class="btn" id="btnListo"></button>
    ${inicio ? "" : '<button class="btn suave" id="btnVolver">Volver</button>'}
    <p class="pie">Los precios son de la Central Mayorista y la Plaza Minorista de Medellín (DANE-SIPSA). Tu canasta se guarda solo en este dispositivo.</p>`;
  $("#contenido").innerHTML = h;

  const pintarExtras = () => {
    const ex = extras();
    $("#extras").innerHTML = ex.length ? `<h2>Otros insumos que elegiste</h2><div class="grupo">${ex.map(chip).join("")}</div>` : "";
    ligarChips();
  };
  const actualizarBoton = () => { const n = estado.borrador.size; const b = $("#btnListo"); b.disabled = n === 0; b.textContent = n === 0 ? "Elige al menos un insumo" : `Ver mis precios (${n})`; };
  function ligarChips() {
    document.querySelectorAll(".opcion").forEach((b) => { b.onclick = () => {
      const n = b.dataset.n;
      if (estado.borrador.has(n)) estado.borrador.delete(n); else estado.borrador.add(n);
      b.classList.toggle("sel", estado.borrador.has(n)); actualizarBoton();
      if (!sugeridos.has(n)) pintarExtras();
    }; });
  }
  pintarExtras(); actualizarBoton();

  $("#buscar").addEventListener("input", async (e) => {
    const q = e.target.value.trim(); if (q.length < 2) return;
    try { const lista = await api("/api/productos?q=" + encodeURIComponent(q)); $("#opciones").innerHTML = lista.map((o) => `<option value="${esc(o)}">`).join(""); } catch (err) {}
  });
  $("#btnAgregar").addEventListener("click", async () => {
    const v = $("#buscar").value.trim(); if (!v) return;
    let lista = []; try { lista = await api("/api/productos?q=" + encodeURIComponent(v) + "&limite=60"); } catch (err) {}
    const exacto = lista.find((o) => o.toLowerCase() === v.toLowerCase());
    if (!exacto) { alert("Elige un producto de la lista que aparece al escribir."); return; }
    estado.borrador.add(exacto); $("#buscar").value = ""; actualizarBoton();
    document.querySelectorAll(".opcion").forEach((b) => { if (b.dataset.n === exacto) b.classList.add("sel"); });
    if (!sugeridos.has(exacto)) pintarExtras();
  });
  $("#btnListo").addEventListener("click", async () => {
    const nueva = [...estado.borrador], antes = estado.canasta || [];
    if (inicio) registrar("completar_canasta", nueva.length);
    else {
      nueva.filter((n) => !antes.includes(n)).forEach((n) => registrar("agregar_insumo", n));
      antes.filter((n) => !nueva.includes(n)).forEach((n) => registrar("quitar_insumo", n));
    }
    estado.canasta = nueva; guardar("pd_canasta", nueva);
    if (!nueva.includes(estado.producto)) estado.producto = nueva[0];
    ir("panel");
  });
  if (!inicio) $("#btnVolver").addEventListener("click", () => ir("panel"));
}

// ---------------------------------------------------------------- vista: panel
function vistaPanel() {
  const ok = estado.precios.filter((p) => p.disponible && !p.desactualizado);
  const semana = ok.length ? fechaCorta(ok[0].fecha) : "";
  let h = bannerConexion() + `<h1>Precios de ${esc(etiquetaMercado())}</h1>${selectorMercado()}
    <p class="sub">SIPSA-DANE · Medellín${semana ? " · semana que termina el " + semana : ""}</p>
    <div class="aviso">Fuente: DANE-SIPSA. La tendencia compara el precio promedio con el de la semana anterior.</div>`;
  alertasActivas().forEach((p) => {
    h += `<div class="aviso alerta">Alerta: ${esc(p.producto)} varió ${pct(p.variacion_pct)} (tu umbral: ${umbralValido(estado.alertas[p.producto].umbral)}%)</div>`;
  });
  h += '<table><thead><tr><th>Insumo</th><th class="num">Mín.</th><th class="num">Máx.</th><th class="num">Tendencia</th></tr></thead><tbody>';
  estado.precios.forEach((p) => {
    const unidad = p.unidad_codigo !== "kg" ? `<span class="viejo">${esc(p.unidad)}</span>` : "";
    if (!p.disponible) { h += `<tr><td class="nombre">${esc(p.producto)}${unidad}</td><td colspan="3" class="igual">Sin datos en ${esc(etiquetaMercado())}</td></tr>`; return; }
    const viejo = p.desactualizado ? `<span class="viejo">último dato: ${mesCorto(p.fecha)}</span>` : "";
    h += `<tr class="fila" data-producto="${esc(p.producto)}"><td class="nombre">${esc(p.producto)}${unidad}${viejo}</td>
      <td class="num">${cop(p.minimo)}</td><td class="num">${cop(p.maximo)}</td><td class="num">${p.desactualizado ? '<span class="igual">–</span>' : tendencia(p)}</td></tr>`;
  });
  h += `</tbody></table>
    <p class="pie">Precios en COP/kg, salvo donde se indica otra unidad. Toca un insumo para ver su histórico y compararlo entre mercados.</p>
    <button class="btn borde" id="btnEditar">Editar mi canasta</button>
    <button class="enlace" id="btnComentar">¿Qué le falta a esta herramienta? Cuéntanos</button>
    <p class="pie">Medimos de forma anónima cómo se usa la aplicación para mejorarla. No guardamos tu nombre ni datos personales.</p>`;
  $("#contenido").innerHTML = h;
  ligarSelectorMercado(async () => { await cargarPrecios(); vistaPanel(); });
  document.querySelectorAll("tr.fila").forEach((tr) => tr.addEventListener("click", () => { estado.producto = tr.dataset.producto; ir("hist"); }));
  $("#btnEditar").addEventListener("click", () => ir("canasta"));
  $("#btnComentar").addEventListener("click", () => abrirComentario("panel"));
}

// ---------------------------------------------------------------- vista: histórico (ambos mercados en una gráfica)
async function vistaHist() {
  if (!estado.producto) { $("#contenido").innerHTML = '<p class="vacio">Agrega un insumo a tu canasta para ver su histórico.</p>'; return; }
  $("#contenido").innerHTML = '<p class="vacio">Cargando…</p>';
  const pedir = (m) => api(`/api/precios/historico?producto=${encodeURIComponent(estado.producto)}&semanas=${encodeURIComponent(estado.semanas)}&mercado=${encodeURIComponent(m)}`).catch(() => null);
  const claves = estado.mercados.map((m) => m.clave);
  const [series, comp] = await Promise.all([
    Promise.all(claves.map(pedir)),
    api("/api/precios/comparar?producto=" + encodeURIComponent(estado.producto)).catch(() => null),
  ]);
  const por = {}; claves.forEach((c, i) => { por[c] = series[i]; });
  const conDatos = claves.filter((c) => por[c] && por[c].length);
  if (!conDatos.length) { $("#contenido").innerHTML = '<h1>' + esc(estado.producto) + '</h1><p class="vacio">No hay datos de este producto.</p>'; return; }
  const mostrado = conDatos.includes(estado.mercado) ? estado.mercado : conDatos[0];
  const base = por[mostrado], ult = base[base.length - 1];
  const todos = conDatos.flatMap((c) => por[c].map((d) => d.promedio));
  const mn = Math.min(...todos), mx = Math.max(...todos), rango = (mx - mn) || 1;
  const W = 334, H = 190, L = 12, R = 12, T = 28, B = 34;
  const X = (i, n) => L + (n === 1 ? 0 : i * (W - L - R) / (n - 1));
  const Y = (v) => T + (H - T - B) * (1 - (v - mn) / rango);
  const colores = { mayorista: "#1f7a4d", minorista: "#c2680a" };
  const mayor = Math.max(...conDatos.map((c) => por[c].length));
  const lineas = conDatos.map((c) => {
    const s = por[c], pts = s.map((d, i) => `${X(i + (mayor - s.length), mayor).toFixed(1)},${Y(d.promedio).toFixed(1)}`).join(" ");
    const ultimo = s[s.length - 1];
    return `<polyline points="${pts}" fill="none" stroke="${colores[c]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" ${c === "minorista" ? 'stroke-dasharray="7 5"' : ""}/>
      <circle cx="${X(mayor - 1, mayor)}" cy="${Y(ultimo.promedio)}" r="5" fill="${colores[c]}" stroke="#fff" stroke-width="2"/>`;
  }).join("");
  const largo = por[conDatos.reduce((a, c) => (por[c].length > por[a].length ? c : a), conDatos[0])];
  const chips = [4, 8, 12].map((n) => `<button class="chip ${estado.semanas === n ? "act" : ""}" data-sem="${n}">${n} sem</button>`).join("");
  const unidad = (estado.precios.find((p) => p.producto === estado.producto) || {}).unidad || (comp && comp.unidad) || "COP/kg";
  let nota = "";
  if (comp && comp.comparable) {
    const d = comp.diferencia_pct, igual = Math.abs(d) < 0.05;
    nota = `<div class="nota-comp">En la semana del ${fechaCorta(comp.minorista.fecha)}, la Plaza Minorista estuvo ${igual ? "al mismo nivel que" : `<b>${pct(Math.abs(d))} ${d > 0 ? "por encima" : "por debajo"}</b> de`} la Central Mayorista. <span class="tenue">Las presentaciones del producto pueden diferir entre mercados.</span></div>`;
  } else if (estado.mercados.length > 1 && conDatos.length === 1) {
    nota = `<div class="nota-comp">Este producto no tiene datos en ${esc(ETIQUETA[claves.find((c) => c !== conDatos[0])])}.</div>`;
  }
  $("#contenido").innerHTML = bannerConexion() + `<h1>${esc(estado.producto)}</h1>
    <p class="sub">Precio promedio semanal · ${esc(unidad)} · Medellín</p>
    <div class="aviso">Fuente: DANE-SIPSA · ${mesCorto(largo[0].fecha)} a ${mesCorto(largo[largo.length - 1].fecha)} de ${largo[largo.length - 1].fecha.slice(0, 4)}</div>
    <div class="seg">${chips}</div>
    <div class="card"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Precio promedio semanal de ${esc(estado.producto)}">
      <line x1="${L}" x2="${W - R}" y1="${T}" y2="${T}" stroke="#e4e6ea"/><line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="#e4e6ea"/>
      <text x="${L}" y="${T - 8}" font-size="10" fill="#6b7280">promedio máx. ${cop(mx)}</text>
      <text x="${W - R}" y="${H - B - 6}" font-size="10" fill="#6b7280" text-anchor="end">promedio mín. ${cop(mn)}</text>
      ${lineas}
      <text x="${L}" y="${H - 12}" font-size="10" fill="#6b7280">${mesCorto(largo[0].fecha)}</text>
      <text x="${W - R}" y="${H - 12}" font-size="10" fill="#6b7280" text-anchor="end">${mesCorto(largo[largo.length - 1].fecha)}</text>
    </svg></div>
    <div class="leyenda">${conDatos.map((c) => `<span><i class="l-${c}"></i>${esc(ETIQUETA[c])}: ${cop(por[c][por[c].length - 1].promedio)}</span>`).join("")}</div>
    ${nota}
    ${selectorMercado()}
    <div class="stats"><div class="stat"><small>Mín. vigente · ${esc(ETIQUETA[mostrado])}</small><b>${cop(ult.minimo)}</b></div><div class="stat"><small>Máx. vigente · ${esc(ETIQUETA[mostrado])}</small><b>${cop(ult.maximo)}</b></div></div>
    <p class="sub">Último dato publicado: ${fechaCorta(ult.fecha)} · promedio ${cop(ult.promedio)}</p>
    <button class="btn" id="btnAlerta">Crear alerta para este insumo</button>`;
  registrar("ver_historico", estado.producto);
  document.querySelectorAll("[data-sem]").forEach((b) => b.addEventListener("click", () => { estado.semanas = parseInt(b.dataset.sem); vistaHist(); }));
  ligarSelectorMercado(() => vistaHist());
  $("#btnAlerta").addEventListener("click", () => {
    if (!estado.alertas[estado.producto]) { estado.alertas[estado.producto] = { umbral: 5, activa: true }; guardar("pd_alertas", estado.alertas); }
    registrar("crear_alerta", estado.producto); ir("alertas");
  });
}

// ---------------------------------------------------------------- vista: alertas
let promptInstalar = null;
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); promptInstalar = e; if (estado.vista === "alertas") vistaAlertas(); });
window.addEventListener("appinstalled", () => { registrar("instalar_app"); promptInstalar = null; });
const esIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
const instalada = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;

function vistaAlertas() {
  let h = `<h1>Mis alertas</h1>
    <p class="sub">Te avisamos cuando un insumo varíe más del porcentaje que definas frente a la semana anterior. Se evalúan con el mercado que tengas elegido en el Panel (${esc(etiquetaMercado())}).</p>
    <div class="aviso ambar">Por ahora las alertas se muestran en el panel. El envío por correo llegará en una siguiente versión.</div>`;
  if (!estado.canasta || !estado.canasta.length) h += '<p class="vacio">Agrega insumos a tu canasta primero.</p>';
  (estado.canasta || []).forEach((n) => {
    const a = estado.alertas[n] || { umbral: 5, activa: false };
    h += `<div class="fila-alerta" data-n="${esc(n)}"><span class="n">${esc(n)}</span>
      <input type="number" min="0.5" step="0.5" value="${umbralValido(a.umbral)}" aria-label="Umbral en % para ${esc(n)}"> %
      <label class="sw"><input type="checkbox" ${a.activa ? "checked" : ""} aria-label="Activar alerta de ${esc(n)}"><span></span></label>
      <button class="quitar">Quitar</button></div>`;
  });
  h += '<button class="btn" id="btnGuardar">Guardar alertas</button><p class="pie" id="msg"></p>';
  if (!instalada) {
    h += '<h2>Instálala en tu celular</h2>';
    if (promptInstalar) h += '<button class="btn suave" id="btnInstalar">Instalar PlazaData</button>';
    else if (esIOS) h += '<p class="pie">En iPhone: toca el botón Compartir y elige «Agregar a pantalla de inicio».</p>';
    else h += '<p class="pie">Desde el menú del navegador elige «Instalar aplicación» o «Agregar a pantalla de inicio». Así abre más rápido y funciona sin conexión con los últimos datos.</p>';
  }
  h += '<button class="enlace" id="btnComentar">¿Qué le falta a esta herramienta? Cuéntanos</button>';
  $("#contenido").innerHTML = h;
  $("#btnGuardar").addEventListener("click", () => {
    document.querySelectorAll(".fila-alerta").forEach((f) => {
      estado.alertas[f.dataset.n] = { umbral: umbralValido(f.querySelector("input[type=number]").value), activa: f.querySelector("input[type=checkbox]").checked };
    });
    guardar("pd_alertas", estado.alertas); registrar("guardar_alertas", Object.values(estado.alertas).filter((x) => x.activa).length);
    $("#msg").textContent = "Alertas guardadas. Se evalúan con los precios de la última semana.";
  });
  document.querySelectorAll(".quitar").forEach((b) => b.addEventListener("click", async () => {
    const n = b.closest(".fila-alerta").dataset.n;
    estado.canasta = estado.canasta.filter((x) => x !== n); guardar("pd_canasta", estado.canasta); registrar("quitar_insumo", n);
    if (estado.producto === n) estado.producto = estado.canasta[0] || null;
    try { await cargarPrecios(); } catch (e) {} vistaAlertas();
  }));
  const bi = $("#btnInstalar");
  if (bi) bi.addEventListener("click", async () => { promptInstalar.prompt(); try { await promptInstalar.userChoice; } catch (e) {} });
  $("#btnComentar").addEventListener("click", () => abrirComentario("alertas"));
}

// ---------------------------------------------------------------- comentarios
function abrirComentario(pantalla) {
  registrar("abrir_comentario", pantalla);
  const velo = document.createElement("div"); velo.className = "velo"; velo.setAttribute("role", "dialog"); velo.setAttribute("aria-modal", "true");
  velo.innerHTML = `<div class="hoja"><h3>¿Qué le falta a PlazaData?</h3>
    <p class="sub">Cuéntanos qué echas de menos o qué no se entiende. No escribas datos personales.</p>
    <textarea id="txtComentario" maxlength="1000" aria-label="Tu comentario" placeholder="Ej.: me gustaría comparar con el precio que yo pago…"></textarea>
    <div class="fila-btn"><button class="btn suave" id="cCancelar">Cancelar</button><button class="btn" id="cEnviar">Enviar</button></div></div>`;
  document.body.appendChild(velo);
  $("#txtComentario").focus();
  const cerrar = () => velo.remove();
  velo.addEventListener("click", (e) => { if (e.target === velo) cerrar(); });
  $("#cCancelar").addEventListener("click", cerrar);
  $("#cEnviar").addEventListener("click", async () => {
    const texto = $("#txtComentario").value.trim(); if (!texto) return;
    $("#cEnviar").disabled = true;
    try {
      const r = await fetch("/api/comentario", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cliente: estado.cliente, pantalla, texto }) });
      if (!r.ok) throw new Error();
      registrar("enviar_comentario", pantalla);
      velo.querySelector(".hoja").innerHTML = '<h3>¡Gracias!</h3><p class="sub">Tu comentario nos ayuda a mejorar la herramienta.</p><button class="btn" id="cCerrar">Cerrar</button>';
      $("#cCerrar").addEventListener("click", cerrar);
    } catch (e) { $("#cEnviar").disabled = false; alert("No se pudo enviar. Revisa tu conexión e inténtalo de nuevo."); }
  });
}

// ---------------------------------------------------------------- navegación
async function ir(vista) {
  estado.vista = vista;
  const primeraVez = vista === "canasta" && estado.canasta === null;
  $("#nav").classList.toggle("oculto", primeraVez);
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("act", b.dataset.vista === vista));
  window.scrollTo(0, 0);
  if (vista === "canasta") { if (!estado.borrador.size || estado.canasta !== null) estado.borrador = new Set(estado.canasta || []); vistaCanasta(); }
  else if (vista === "panel") {
    try { await cargarPrecios(); vistaPanel(); }
    catch (e) { $("#contenido").innerHTML = '<p class="vacio">No se pudo cargar. Revisa tu conexión e inténtalo de nuevo.</p>'; }
  }
  else if (vista === "hist") vistaHist();
  else vistaAlertas();
}
document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => ir(b.dataset.vista)));
$("#btnTitulo").addEventListener("click", () => ir("canasta"));

async function iniciar() {
  try { estado.mercados = await api("/api/mercados"); } catch (e) { estado.mercados = [{ clave: "mayorista", etiqueta: "Central Mayorista" }]; }
  if (!estado.mercados.length) estado.mercados = [{ clave: "mayorista", etiqueta: "Central Mayorista" }];
  if (!estado.mercados.some((m) => m.clave === estado.mercado)) estado.mercado = estado.mercados[0].clave;
  registrar("abrir_app");
  ir(estado.canasta === null ? "canasta" : "panel");
}
// Al perder o recuperar la conexión se vuelve a pintar la pantalla (salvo mientras se edita la canasta).
["online", "offline"].forEach((ev) => window.addEventListener(ev, () => { if (estado.vista !== "canasta") ir(estado.vista); }));
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
iniciar();
