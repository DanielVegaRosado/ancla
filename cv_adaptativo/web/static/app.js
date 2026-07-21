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
    boton.textContent = "Copiado";
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
  boton.textContent = "Pensando…";
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
    aviso.textContent = "No se han podido proponer keywords.";
    aviso.hidden = false;
  } finally {
    boton.textContent = original;
    boton.disabled = false;
  }
});
