"use strict";
// Página privada de resultados. La clave se envía en una cabecera (nunca en la URL) y solo se guarda en memoria.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const tabla = (cols, filas) => `<table><thead><tr>${cols.map((c) => `<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>${
  filas.length ? filas.map((f) => `<tr>${cols.map((c) => `<td>${esc(f[c[1]])}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${cols.length}">Sin datos todavía</td></tr>`}</tbody></table>`;
const MENSAJES = { 401: "Clave incorrecta.", 429: "Demasiados intentos fallidos. Espera unos minutos.", 503: "El resumen está desactivado: falta definir ADMIN_KEY (16 caracteres o más) en el servidor." };

async function cargar() {
  const clave = $("#clave").value;
  $("#error").textContent = "";
  if (!clave) { $("#error").textContent = "Escribe la clave."; return; }
  let r;
  try { r = await fetch("/api/admin/resumen", { headers: { "X-Admin-Key": clave }, cache: "no-store" }); }
  catch (e) { $("#error").textContent = "No hay conexión con el servidor."; return; }
  if (!r.ok) { $("#error").textContent = MENSAJES[r.status] || "No se pudo cargar (" + r.status + ")."; return; }
  const d = await r.json();
  $("#clave").value = "";
  $("#acceso").hidden = true; $("#datos").hidden = false;
  $("#datos").innerHTML = `<div class="tarjetas"><div class="t"><b>${esc(d.usuarios_unicos)}</b><small>usuarios únicos</small></div><div class="t"><b>${esc(d.eventos_total)}</b><small>eventos registrados</small></div><div class="t"><b>${esc(d.comentarios.length)}</b><small>comentarios</small></div></div>
    <h2>Usuarios activos por semana</h2>${tabla([["Semana desde (lunes)", "semana_desde"], ["Usuarios", "usuarios"], ["Aperturas de la app", "aperturas"]], d.por_semana)}
    <h2>Por usuario (código aleatorio)</h2>${tabla([["Código", "cliente"], ["Primer uso", "primer_uso"], ["Último uso", "ultimo_uso"], ["Días activos", "dias_activos"], ["Semanas activas", "semanas_activas"], ["Eventos", "eventos"]], d.por_usuario)}
    <h2>Qué hacen</h2>${tabla([["Evento", "evento"], ["Veces", "n"]], d.por_evento)}
    <h2>Comentarios</h2>${d.comentarios.length ? d.comentarios.map((c) => `<div class="com"><small>${esc(c.fecha)} · ${esc(c.pantalla || "")}</small>${esc(c.texto)}</div>`).join("") : '<p class="sub">Sin comentarios todavía.</p>'}
    <p class="sub">${esc(d.nota)}</p>`;
}
$("#ver").addEventListener("click", cargar);
$("#clave").addEventListener("keydown", (e) => { if (e.key === "Enter") cargar(); });
