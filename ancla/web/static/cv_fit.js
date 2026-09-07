// Preview screen: sizing the CV so it comes out on one page, whatever the
// user wrote.
//
// A CV that quietly runs onto a second page is the failure this whole HTML
// path exists to remove, and no fixed type size can prevent it. How many
// experiences fit is bounded by the template's own range, but the length of
// "About me" is not, so for any size decided in advance there is a text long
// enough to overflow it. Rule 2 forbids the other way out: the user's text is
// never shortened or rewritten to make it fit.
//
// What a browser can do — and a `.docx` cannot, which is why the estimates in
// `export/fill.py` exist — is measure the page it just laid out. So the size
// is not chosen, it is searched for: the largest `--cv-escala` whose content
// still fits one page. Measuring is not the guesswork that was dropped from
// the `.docx` path; it is the reason for having moved to HTML.
//
// It lives with the preview screen and not in any template because it needs
// nothing design-specific: a template declares its page height
// (`--cv-alto-pagina`) and how its own type answers to `--cv-escala`, and
// gets fitting for free. A design added later needs no calibration.
//
// Measuring on screen is what makes the result hold on paper, and it has to
// be done here because `@media print` never applies on screen: the sheet is
// laid out at exactly the printed page's width, so the height reported here
// is the height the printer will have to paginate.
(() => {
  const cv = document.querySelector(".cv");
  if (!cv) return;

  // The ceiling is a matter of taste rather than of fit — past it a CV with
  // little in it stops reading as a document and starts reading as large
  // print. The floor is measured: it is what the longest "About me" in the
  // test sweep (1368 characters over five experiences) needs, and it is also
  // where body type reaches ~8pt, below which a CV that fits is worse than a
  // CV that doesn't.
  const MAX_SCALE = 1.2;
  const MIN_SCALE = 0.85;
  const PRECISION = 0.005;

  // Room left for the difference between the height measured here and the
  // one the print engine rounds to. Without it a page that fits to the
  // pixel on screen can still spill a hair over on paper.
  const PRINT_GUARD_PT = 4;

  const toPixels = (points) => (points * 96) / 72;

  function pageHeight() {
    const declared = getComputedStyle(cv).getPropertyValue("--cv-alto-pagina");
    return toPixels(parseFloat(declared));
  }

  function heightAt(scale) {
    cv.style.setProperty("--cv-escala", scale);
    return cv.getBoundingClientRect().height;
  }

  // The largest scale whose content fits, or the floor when even that
  // doesn't: the caller measures once more to tell the two apart, so there
  // is no second way of saying "it doesn't fit" to keep in step with this one.
  function largestScaleThatFits(limit) {
    if (heightAt(MAX_SCALE) <= limit) return MAX_SCALE;

    let fits = MIN_SCALE;
    let overflows = MAX_SCALE;
    while (overflows - fits > PRECISION) {
      const middle = (fits + overflows) / 2;
      if (heightAt(middle) <= limit) fits = middle;
      else overflows = middle;
    }
    return fits;
  }

  function fitToPage() {
    const limit = pageHeight() - toPixels(PRINT_GUARD_PT);
    if (!isFinite(limit)) return;

    // While measuring, the sheet is released from its one-page floor so that
    // what gets measured is the height the content asks for, not the height
    // the page imposes on it.
    cv.classList.add("cv-midiendo");
    const scale = largestScaleThatFits(limit);
    const fits = heightAt(scale) <= limit;
    cv.classList.remove("cv-midiendo");

    cv.style.setProperty("--cv-escala", scale);
    const warning = document.querySelector("[data-aviso-desborde]");
    if (warning) warning.hidden = fits;
  }

  // Text laid out in a font that hasn't loaded yet is text of the wrong
  // height, and a fit computed from it is a fit for a page nobody prints.
  document.fonts.ready.then(fitToPage);
})();
