// Vanilla JS, no dependencies. Small, local behaviors:
// copy to clipboard, confirm deletions, show the fields the chosen provider
// needs, and suggest keywords with AI.

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copiar]");
  if (!button) return;

  const source = document.getElementById(button.getAttribute("data-copiar"));
  if (!source) return;

  const text = "value" in source ? source.value : source.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const original = button.textContent;
    button.textContent = document.body.dataset.textoCopiado;
    setTimeout(() => { button.textContent = original; }, 1500);
  });
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  const message = form.getAttribute("data-confirmar");
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});

// Suggest keywords with AI. They are ADDED to whatever is already written,
// never replacing it: what the user typed always wins over what the model suggests.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-sugerir-keywords]");
  if (!button) return;

  const target = document.getElementById(button.getAttribute("data-destino"));
  const notice = button.closest(".campo").querySelector("[data-aviso-keywords]");
  if (!target) return;

  const payload = { tipo: button.getAttribute("data-tipo") };
  for (const pair of button.getAttribute("data-campos").split(",")) {
    const [field, key] = pair.includes(":") ? pair.split(":") : [pair, pair];
    payload[key] = (document.getElementById(field) || {}).value || "";
  }

  const original = button.textContent;
  button.textContent = document.body.dataset.textoPensando;
  button.disabled = true;
  notice.hidden = true;

  try {
    const response = await fetch("/perfil/keywords", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    const alreadyPresent = target.value.split(",").map((k) => k.trim()).filter(Boolean);
    const known = new Set(alreadyPresent.map((k) => k.toLowerCase()));
    const newOnes = (data.keywords || []).filter((k) => !known.has(k.toLowerCase()));
    target.value = alreadyPresent.concat(newOnes).join(", ");

    if (data.aviso) {
      notice.textContent = data.aviso;
      notice.hidden = false;
    }
  } catch (error) {
    notice.textContent = document.body.dataset.textoFalloKeywords;
    notice.hidden = false;
  } finally {
    button.textContent = original;
    button.disabled = false;
  }
});

// Generic drag-to-reorder for a list of cards, each carrying its own
// `data-clave`. Dragging only works by grabbing the "⠿" handle
// (`.manija-arrastrar`) — not the whole card — so it doesn't interfere
// with clicks on the card's own buttons. `saveOrder` is called with the
// new key order on every drop; the card has already moved on screen
// regardless of whether that request succeeds, and it's only retried the
// next time something gets reordered. Shared by "Mi perfil" (panel order)
// and the Proposal screen (which experiences make a template's cut) so
// the two never end up with two different drag implementations.
function activateDragToReorder(container, saveOrder) {
  let dragged = null;

  container.addEventListener("mousedown", (event) => {
    if (!event.target.closest(".manija-arrastrar")) return;
    const card = event.target.closest("[data-arrastrable]");
    if (card) card.draggable = true;
  });

  container.addEventListener("dragstart", (event) => {
    const card = event.target.closest("[data-arrastrable]");
    if (!card) return;
    dragged = card;
    card.classList.add("arrastrable-arrastrando");
    event.dataTransfer.effectAllowed = "move";
  });

  container.addEventListener("dragover", (event) => {
    const card = event.target.closest("[data-arrastrable]");
    if (!card || card === dragged) return;
    event.preventDefault();
    container.querySelectorAll("[data-arrastrable]").forEach((t) => t.classList.remove("arrastrable-destino"));
    card.classList.add("arrastrable-destino");
  });

  container.addEventListener("drop", (event) => {
    const target = event.target.closest("[data-arrastrable]");
    if (!target || !dragged || target === dragged) return;
    event.preventDefault();

    const before = event.clientY < target.getBoundingClientRect().top + target.offsetHeight / 2;
    target.parentNode.insertBefore(dragged, before ? target : target.nextSibling);

    saveOrder([...container.querySelectorAll("[data-arrastrable]")].map((t) => t.dataset.clave));
  });

  container.addEventListener("dragend", () => {
    container.querySelectorAll("[data-arrastrable]").forEach((t) => {
      t.draggable = false;
      t.classList.remove("arrastrable-arrastrando", "arrastrable-destino");
    });
    dragged = null;
  });
}

// My profile: drag the panels (Experience, Skills...) to change the order
// they're shown in.
(() => {
  const container = document.querySelector("[data-paneles-perfil]");
  if (!container) return;

  activateDragToReorder(container, (order) => {
    fetch("/perfil/orden", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ orden: order }),
    }).catch(() => {});
  });
})();

// Proposal screen: drag the selected experiences to decide which ones fall
// inside a template's maximum (see cv_preview.py) once there are more of
// them than a chosen design has room for.
(() => {
  const container = document.querySelector("[data-experiencias-propuesta]");
  if (!container) return;

  activateDragToReorder(container, (order) => {
    fetch("/propuesta/orden-experiencias", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ orden: order }),
    }).catch(() => {});
  });
})();

// My CVs: the stats panel doubles as a filter. Clicking a card (Sent,
// Interview...) filters the list without reloading the page; every CV
// stays in the HTML, only the ones that don't match get hidden.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filtro]");
  if (!button) return;

  const panel = button.closest("[data-filtro-cvs]");
  const list = document.querySelector("[data-lista-cvs]");
  if (!panel || !list) return;

  panel.querySelectorAll("[data-filtro]").forEach((b) => b.classList.remove("bento-tarjeta-activa"));
  button.classList.add("bento-tarjeta-activa");

  const filter = button.getAttribute("data-filtro");
  let visibleCount = 0;
  list.querySelectorAll("[data-estado]").forEach((card) => {
    const matches = filter === "todos" || card.getAttribute("data-estado") === filter;
    card.hidden = !matches;
    if (matches) visibleCount += 1;
  });

  const noResults = document.querySelector("[data-sin-resultados]");
  if (noResults) noResults.hidden = visibleCount > 0;
});

// Settings: the base URL and model fields (and the Groq daily-limit notice)
// only show up when the chosen provider needs them — avoids displaying
// fields that don't apply to that provider.
(() => {
  const selector = document.getElementById("proveedor");
  if (!selector) return;
  const fields = document.querySelectorAll("[data-mostrar-si-proveedor]");

  const update = () => {
    fields.forEach((field) => {
      const allowed = field.getAttribute("data-mostrar-si-proveedor").split(",").map((v) => v.trim());
      field.hidden = !allowed.includes(selector.value);
    });
  };

  selector.addEventListener("change", update);
  update();
})();

// Settings: switching provider swaps in that provider's own remembered key
// (and its placeholder) instead of leaving the previous provider's key
// sitting in the field — the exact mix-up that let one provider's key get
// saved under another provider's name.
(() => {
  const selector = document.getElementById("proveedor");
  const keyField = document.getElementById("clave_api");
  if (!selector || !keyField) return;

  selector.addEventListener("change", () => {
    const option = selector.options[selector.selectedIndex];
    keyField.value = option.dataset.clave || "";
    keyField.placeholder = option.dataset.placeholderClave || "";
  });
})();

// Support: the message placeholder changes depending on whether it's a
// "problem" or a "suggestion", so the blank field itself hints at what to write.
document.addEventListener("change", (event) => {
  if (!event.target.matches("[data-cambia-placeholder]")) return;

  const message = document.getElementById("mensaje");
  if (!message) return;
  const key = `placeholder${event.target.value.charAt(0).toUpperCase()}${event.target.value.slice(1)}`;
  const newValue = message.dataset[key];
  if (newValue) message.placeholder = newValue;
});

// CV preview: opens the browser's own print dialog, which is what turns the
// page into a PDF. The app never generates the file itself.
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-imprimir]")) window.print();
});

// Proposal / saved CV: how many experiences fit is a property of the chosen
// design, not a free number — the field is clamped to that template's own
// [min, max] so the request can never ask for more than the page supports
// (the server clamps it again regardless, see cv_preview.py::_capacity).
(() => {
  const selector = document.getElementById("plantilla_html");
  const capacity = document.getElementById("capacidad_html");
  if (!selector || !capacity) return;

  const currentTemplateLimits = () => {
    const option = selector.options[selector.selectedIndex];
    const min = Number(option.dataset.capacidadMin) || 1;
    const max = Number(option.dataset.capacidadMax) || 0; // 0 = no maximum declared
    return { min, max };
  };

  const adjustFieldsToLimit = () => {
    const { min, max } = currentTemplateLimits();
    capacity.min = min;
    if (max > 0) capacity.max = max;
    else capacity.removeAttribute("max");

    let value = Number(capacity.value) || (max > 0 ? max : min);
    value = Math.max(value, min);
    if (max > 0) value = Math.min(value, max);
    capacity.value = value;
  };

  selector.addEventListener("change", adjustFieldsToLimit);
  capacity.addEventListener("change", adjustFieldsToLimit);
})();
