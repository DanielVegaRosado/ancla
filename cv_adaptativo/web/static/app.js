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
