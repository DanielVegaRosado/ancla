// "About me" screen: marking the six gaps over the text the user wrote.
//
// Marking by hand is the way this screen is completed: it needs no API key
// and makes no request, so it keeps working when the provider is down or the
// free quota runs out. Asking the AI to propose the six positions is an
// accelerator on top, and it goes through exactly the same field, so the
// user carries on adjusting the proposal with the same buttons.
//
// Every edit goes through `replaceSelection`, which uses `execCommand` so
// the browser records it in its own undo stack and Ctrl+Z works as anywhere
// else. The explicit "undo" button is there because nobody expects Ctrl+Z to
// undo something a button did.
(() => {
  const form = document.querySelector("[data-sobre-mi]");
  if (!form) return;

  const script = document.currentScript;
  const proposeButton = form.querySelector("[data-proponer-huecos]");
  const undoButton = form.querySelector("[data-deshacer-huecos]");
  const warnings = form.querySelector("[data-avisos-huecos]");
  const fields = [...form.querySelectorAll("textarea")];
  let previousTexts = null;

  // Replaces what is selected (or inserts at the caret) keeping the change
  // in the browser's undo history. `execCommand` is deprecated with no
  // replacement for this; without it the value is still written, only Ctrl+Z
  // no longer reaches it.
  const replaceSelection = (field, text) => {
    field.focus();
    if (!document.execCommand || !document.execCommand("insertText", false, text)) {
      const { selectionStart: start, selectionEnd: end, value } = field;
      field.value = value.slice(0, start) + text + value.slice(end);
      field.setSelectionRange(start + text.length, start + text.length);
    }
    field.dispatchEvent(new Event("input", { bubbles: true }));
  };

  const replaceAll = (field, text) => {
    field.setSelectionRange(0, field.value.length);
    replaceSelection(field, text);
  };

  // A gap already in the text would be placed twice, and the second one only
  // shows up as a stray token in the finished CV.
  const refreshButtons = () => {
    for (const button of form.querySelectorAll("[data-hueco]")) {
      const field = document.getElementById(button.dataset.destino);
      button.disabled = field.value.includes(button.dataset.hueco);
    }
  };

  const showWarnings = (mensajes) => {
    warnings.replaceChildren(
      ...mensajes.map((mensaje) => {
        const item = document.createElement("li");
        item.className = "aviso";
        item.textContent = mensaje;
        return item;
      })
    );
    warnings.hidden = mensajes.length === 0;
  };

  form.addEventListener("click", (evento) => {
    const button = evento.target.closest("[data-hueco]");
    if (!button) return;
    replaceSelection(document.getElementById(button.dataset.destino), button.dataset.hueco);
  });

  form.addEventListener("input", refreshButtons);

  proposeButton.addEventListener("click", async () => {
    const original = proposeButton.textContent;
    proposeButton.textContent = document.body.dataset.textoPensando;
    proposeButton.disabled = true;
    showWarnings([]);

    try {
      const respuesta = await fetch("/perfil/sobre-mi/huecos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plantilla_es: fields[0].value,
          plantilla_en: fields[1].value,
        }),
      });
      const datos = await respuesta.json();
      previousTexts = fields.map((field) => field.value);
      replaceAll(fields[0], datos.plantilla_es);
      replaceAll(fields[1], datos.plantilla_en);
      undoButton.hidden = false;
      showWarnings(datos.avisos || []);
    } catch (error) {
      showWarnings([script.dataset.textoFallo]);
    } finally {
      proposeButton.textContent = original;
      proposeButton.disabled = false;
      refreshButtons();
    }
  });

  undoButton.addEventListener("click", () => {
    if (!previousTexts) return;
    fields.forEach((field, i) => replaceAll(field, previousTexts[i]));
    previousTexts = null;
    undoButton.hidden = true;
    showWarnings([]);
    refreshButtons();
  });

  refreshButtons();
})();
