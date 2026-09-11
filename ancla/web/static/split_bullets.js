// Experience form: splitting a paragraph of prose into one bullet per line.
//
// Writing the bullets by hand is the way this field is filled in, and it
// needs no API key. This button is an accelerator on top: it sends the
// textarea as it stands, the server cuts it where the model points (never
// rewriting a word, see `profile/bullets.py`) and writes the result back
// into the same field, for the user to accept, retouch or undo. Nothing is
// saved until the form is saved.
//
// One button per language, each one independent: the two textareas hold
// texts of their own and there is no reason to spend a call on a field the
// user is not looking at.
(() => {
  const form = document.querySelector("[data-experiencia]");
  if (!form) return;

  const script = document.currentScript;
  const { replaceAll } = window.Ancla;
  const previousTexts = new Map();

  const box = (button) => button.closest(".campo");
  const field = (button) => document.getElementById(button.dataset.destino);
  const undoButton = (button) =>
    box(button).querySelector("[data-deshacer-bullets]");

  const showWarnings = (button, mensajes) => {
    const warnings = box(button).querySelector("[data-avisos-bullets]");
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

  form.addEventListener("click", async (evento) => {
    const button = evento.target.closest("[data-dividir-bullets]");
    if (!button) return;

    const target = field(button);
    const original = button.textContent;
    button.textContent = document.body.dataset.textoPensando;
    button.disabled = true;
    showWarnings(button, []);

    try {
      const respuesta = await fetch("/perfil/experiencias/dividir-bullets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bullets: target.value }),
      });
      const datos = await respuesta.json();
      previousTexts.set(target.id, target.value);
      replaceAll(target, datos.bullets);
      undoButton(button).hidden = false;
      showWarnings(button, datos.avisos || []);
    } catch (error) {
      showWarnings(button, [script.dataset.textoFallo]);
    } finally {
      button.textContent = original;
      button.disabled = false;
    }
  });

  form.addEventListener("click", (evento) => {
    const button = evento.target.closest("[data-deshacer-bullets]");
    if (!button) return;
    const target = field(button);
    if (!previousTexts.has(target.id)) return;
    replaceAll(target, previousTexts.get(target.id));
    previousTexts.delete(target.id);
    button.hidden = true;
    showWarnings(button, []);
  });
})();
