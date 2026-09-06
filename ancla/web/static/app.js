// Vanilla JS, no dependencies. Small, local behaviors:
// copy to clipboard, confirm deletions, show the fields the chosen provider
// needs, and suggest keywords with AI.

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

// Suggest keywords with AI. They are ADDED to whatever is already written,
// never replacing it: what the user typed always wins over what the model suggests.
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

// My profile: drag the panels (Experience, Skills...) to change the order
// they're shown in. Dragging only works by grabbing the "⠿" handle — not
// the whole card — so it doesn't interfere with clicks on its buttons. The
// new order is saved to the server on drop; if the request fails, the
// panel has already moved on screen regardless, and it's only retried the
// next time something gets reordered.
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

// My CVs: the stats panel doubles as a filter. Clicking a card (Sent,
// Interview...) filters the list without reloading the page; every CV
// stays in the HTML, only the ones that don't match get hidden.
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

// Settings: the base URL and model fields (and the Groq daily-limit notice)
// only show up when the chosen provider needs them — avoids displaying
// fields that don't apply to that provider.
(() => {
  const selector = document.getElementById("proveedor");
  if (!selector) return;
  const campos = document.querySelectorAll("[data-mostrar-si-proveedor]");

  const actualizar = () => {
    campos.forEach((campo) => {
      const permitidos = campo.getAttribute("data-mostrar-si-proveedor").split(",").map((v) => v.trim());
      campo.hidden = !permitidos.includes(selector.value);
    });
  };

  selector.addEventListener("change", actualizar);
  actualizar();
})();

// Settings: switching provider swaps in that provider's own remembered key
// (and its placeholder) instead of leaving the previous provider's key
// sitting in the field — the exact mix-up that let one provider's key get
// saved under another provider's name.
(() => {
  const selector = document.getElementById("proveedor");
  const campoClave = document.getElementById("clave_api");
  if (!selector || !campoClave) return;

  selector.addEventListener("change", () => {
    const opcion = selector.options[selector.selectedIndex];
    campoClave.value = opcion.dataset.clave || "";
    campoClave.placeholder = opcion.dataset.placeholderClave || "";
  });
})();

// Support: the message placeholder changes depending on whether it's a
// "problem" or a "suggestion", so the blank field itself hints at what to write.
document.addEventListener("change", (evento) => {
  if (!evento.target.matches("[data-cambia-placeholder]")) return;

  const mensaje = document.getElementById("mensaje");
  if (!mensaje) return;
  const clave = `placeholder${evento.target.value.charAt(0).toUpperCase()}${evento.target.value.slice(1)}`;
  const nuevo = mensaje.dataset[clave];
  if (nuevo) mensaje.placeholder = nuevo;
});

// CV preview: opens the browser's own print dialog, which is what turns the
// page into a PDF. The app never generates the file itself.
document.addEventListener("click", (evento) => {
  if (evento.target.closest("[data-imprimir]")) window.print();
});

// Proposal / saved CV: how many experiences fit is a property of the chosen
// design, so picking another template offers that template's own number
// instead of leaving the previous one's behind.
(() => {
  const selector = document.getElementById("plantilla_html");
  const capacidad = document.getElementById("capacidad_html");
  if (!selector || !capacidad) return;

  selector.addEventListener("change", () => {
    capacidad.value = selector.options[selector.selectedIndex].dataset.capacidad || capacidad.value;
  });
})();
