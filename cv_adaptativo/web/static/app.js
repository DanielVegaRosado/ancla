// Vanilla JS, sin dependencias. Tres comportamientos pequeños y locales:
// copiar al portapapeles, confirmar borrados y auto-generar un identificador
// a partir de un título mientras el usuario no lo haya tocado a mano.

document.addEventListener("click", (evento) => {
  const boton = evento.target.closest("[data-copiar]");
  if (!boton) return;

  const origen = document.getElementById(boton.getAttribute("data-copiar"));
  if (!origen) return;

  const texto = "value" in origen ? origen.value : origen.textContent;
  navigator.clipboard.writeText(texto).then(() => {
    const original = boton.textContent;
    boton.textContent = document.body.dataset.textoCopiado;
    setTimeout(() => { boton.textContent = original; }, 1500);
  });
});

document.addEventListener("submit", (evento) => {
  const formulario = evento.target;
  const mensaje = formulario.getAttribute("data-confirmar");
  if (mensaje && !window.confirm(mensaje)) {
    evento.preventDefault();
  }
});

document.addEventListener("input", (evento) => {
  if (!evento.target.matches("[data-fuente-id]")) return;
  const destino = document.getElementById(evento.target.getAttribute("data-fuente-id"));
  if (!destino || destino.dataset.tocado === "1") return;
  destino.value = evento.target.value
    .toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
});

document.addEventListener("input", (evento) => {
  if (evento.target.matches("[data-id-manual]")) {
    evento.target.dataset.tocado = "1";
  }
});

// Proponer keywords con IA. Se AÑADEN a las que ya haya escritas, nunca las
// sustituyen: lo que el usuario escribió manda sobre lo que sugiera el modelo.
document.addEventListener("click", async (evento) => {
  const boton = evento.target.closest("[data-sugerir-keywords]");
  if (!boton) return;

  const destino = document.getElementById(boton.getAttribute("data-destino"));
  const aviso = boton.closest(".campo").querySelector("[data-aviso-keywords]");
  if (!destino) return;

  const cuerpo = { tipo: boton.getAttribute("data-tipo") };
  for (const par of boton.getAttribute("data-campos").split(",")) {
    const [campo, clave] = par.includes(":") ? par.split(":") : [par, par];
    cuerpo[clave] = (document.getElementById(campo) || {}).value || "";
  }

  const original = boton.textContent;
  boton.textContent = document.body.dataset.textoPensando;
  boton.disabled = true;
  aviso.hidden = true;

  try {
    const respuesta = await fetch("/perfil/keywords", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    const datos = await respuesta.json();

    const yaEstaban = destino.value.split(",").map((k) => k.trim()).filter(Boolean);
    const conocidas = new Set(yaEstaban.map((k) => k.toLowerCase()));
    const nuevas = (datos.keywords || []).filter((k) => !conocidas.has(k.toLowerCase()));
    destino.value = yaEstaban.concat(nuevas).join(", ");

    if (datos.aviso) {
      aviso.textContent = datos.aviso;
      aviso.hidden = false;
    }
  } catch (error) {
    aviso.textContent = document.body.dataset.textoFalloKeywords;
    aviso.hidden = false;
  } finally {
    boton.textContent = original;
    boton.disabled = false;
  }
});

// Mi perfil: arrastrar los paneles (Experiencia, Skills...) para cambiar el
// orden en el que se ven. Solo se puede arrastrar agarrando el asa "⠿" —no
// la tarjeta entera— para no interferir con los clics en sus botones. El
// orden nuevo se guarda en el servidor al soltar; si la petición falla, el
// panel ya se movió en pantalla igualmente, y se reintentará solo la
// próxima vez que se reordene algo.
(() => {
  const contenedor = document.querySelector("[data-paneles-perfil]");
  if (!contenedor) return;

  let arrastrado = null;

  contenedor.addEventListener("mousedown", (evento) => {
    if (!evento.target.closest(".manija-arrastrar")) return;
    const panel = evento.target.closest("[data-panel-arrastrable]");
    if (panel) panel.draggable = true;
  });

  contenedor.addEventListener("dragstart", (evento) => {
    const panel = evento.target.closest("[data-panel-arrastrable]");
    if (!panel) return;
    arrastrado = panel;
    panel.classList.add("panel-perfil-arrastrando");
    evento.dataTransfer.effectAllowed = "move";
  });

  contenedor.addEventListener("dragover", (evento) => {
    const panel = evento.target.closest("[data-panel-arrastrable]");
    if (!panel || panel === arrastrado) return;
    evento.preventDefault();
    contenedor.querySelectorAll("[data-panel-arrastrable]").forEach((p) => p.classList.remove("panel-perfil-destino"));
    panel.classList.add("panel-perfil-destino");
  });

  contenedor.addEventListener("drop", (evento) => {
    const destino = evento.target.closest("[data-panel-arrastrable]");
    if (!destino || !arrastrado || destino === arrastrado) return;
    evento.preventDefault();

    const antes = evento.clientY < destino.getBoundingClientRect().top + destino.offsetHeight / 2;
    destino.parentNode.insertBefore(arrastrado, antes ? destino : destino.nextSibling);

    const orden = [...contenedor.querySelectorAll("[data-panel-arrastrable]")].map((p) => p.dataset.clave);
    fetch("/perfil/orden", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ orden }),
    }).catch(() => {});
  });

  contenedor.addEventListener("dragend", () => {
    contenedor.querySelectorAll("[data-panel-arrastrable]").forEach((p) => {
      p.draggable = false;
      p.classList.remove("panel-perfil-arrastrando", "panel-perfil-destino");
    });
    arrastrado = null;
  });
})();

// Mis CVs: el panel de cifras hace también de filtro. Se pulsa una tarjeta
// (Enviado, Entrevista...) y la lista se filtra sin recargar la página; los
// CVs siguen todos en el HTML, solo se ocultan los que no tocan.
document.addEventListener("click", (evento) => {
  const boton = evento.target.closest("[data-filtro]");
  if (!boton) return;

  const panel = boton.closest("[data-filtro-cvs]");
  const lista = document.querySelector("[data-lista-cvs]");
  if (!panel || !lista) return;

  panel.querySelectorAll("[data-filtro]").forEach((b) => b.classList.remove("bento-tarjeta-activa"));
  boton.classList.add("bento-tarjeta-activa");

  const filtro = boton.getAttribute("data-filtro");
  let visibles = 0;
  lista.querySelectorAll("[data-estado]").forEach((tarjeta) => {
    const coincide = filtro === "todos" || tarjeta.getAttribute("data-estado") === filtro;
    tarjeta.hidden = !coincide;
    if (coincide) visibles += 1;
  });

  const sinResultados = document.querySelector("[data-sin-resultados]");
  if (sinResultados) sinResultados.hidden = visibles > 0;
});

// Soporte: el placeholder del mensaje cambia según sea "problema" o
// "sugerencia", para que el hueco en blanco ya sugiera qué escribir.
document.addEventListener("change", (evento) => {
  if (!evento.target.matches("[data-cambia-placeholder]")) return;

  const mensaje = document.getElementById("mensaje");
  if (!mensaje) return;
  const clave = `placeholder${evento.target.value.charAt(0).toUpperCase()}${evento.target.value.slice(1)}`;
  const nuevo = mensaje.dataset[clave];
  if (nuevo) mensaje.placeholder = nuevo;
});
