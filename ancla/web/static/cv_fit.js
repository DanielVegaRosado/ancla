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
// What a browser can do — and the old `.docx` export could not, which is why
// it had to estimate line wrapping instead — is measure the page it just
// laid out. So the size is not chosen, it is searched for: the largest scale
// whose content still fits one page.
//
// It lives with the preview screen and not in any template because it needs
// nothing design-specific: a template declares its page height
// (`--cv-alto-pagina`) and how its own type answers to `--cv-escala` and
// `--cv-escala-lateral`, and gets fitting for free. A design added later
// needs no calibration.
//
// Measuring on screen is what makes the result hold on paper, and it has to
// be done here because `@media print` never applies on screen: the sheet is
// laid out at exactly the printed page's width, so the height reported here
// is the height the printer will have to paginate.
//
// Two columns, two independent searches. The sidebar's content (contact,
// skills, languages) is the profile's, not the proposal's, so it never grows
// past its own natural size to fill blank space the way the main column
// does — its ceiling is 1, not 1.2. It also cannot shrink as far: its type
// is already smaller than the main column's body text, so its floor sits
// higher than `MIN_SCALE`. Sharing one variable between the two would tie a
// short "About me" growing to fill the page to the sidebar's own fit, with
// nothing to do with each other; searching them separately against the same
// page limit is what makes a long "About me" and a long skills list each pay
// only for their own overflow.
(() => {
  const cv = document.querySelector(".cv");
  const principal = document.querySelector(".cv-principal");
  if (!cv || !principal) return;
  const lateral = document.querySelector(".cv-lateral");

  // The ceiling is a matter of taste rather than of fit — past it a CV with
  // little in it stops reading as a document and starts reading as large
  // print. The floor is measured: it is what the longest "About me" in the
  // test sweep (1368 characters over five experiences) needs, and it is also
  // where body type reaches ~8pt, below which a CV that fits is worse than a
  // CV that doesn't.
  const MAX_SCALE = 1.2;
  const MIN_SCALE = 0.85;

  // The sidebar's own range: measured the same way, against a sidebar
  // deliberately stuffed with technical skills, personal skills and
  // languages (see `bitacora/barra-lateral-encoge.md`).
  const MAX_SCALE_LATERAL = 1;
  const MIN_SCALE_LATERAL = 0.8;

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

  function heightAt(el, property, scale) {
    cv.style.setProperty(property, scale);
    return el.getBoundingClientRect().height;
  }

  // The largest scale whose content fits, or the floor when even that
  // doesn't: the caller measures once more to tell the two apart, so there
  // is no second way of saying "it doesn't fit" to keep in step with this one.
  function largestScaleThatFits(el, property, max, min, limit) {
    if (heightAt(el, property, max) <= limit) return max;

    let fits = min;
    let overflows = max;
    while (overflows - fits > PRECISION) {
      const middle = (fits + overflows) / 2;
      if (heightAt(el, property, middle) <= limit) fits = middle;
      else overflows = middle;
    }
    return fits;
  }

  function fitToPage() {
    const limit = pageHeight() - toPixels(PRINT_GUARD_PT);
    if (!isFinite(limit)) return;

    // While measuring, the sheet is released from its one-page floor and its
    // columns from mutual stretch, so what gets measured is the height each
    // column's own content asks for, not the height the page or the other
    // column imposes on it.
    cv.classList.add("cv-midiendo");

    const scalePrincipal = largestScaleThatFits(
      principal,
      "--cv-escala",
      MAX_SCALE,
      MIN_SCALE,
      limit,
    );
    const principalFits = heightAt(principal, "--cv-escala", scalePrincipal) <= limit;

    let lateralFits = true;
    if (lateral) {
      const scaleLateral = largestScaleThatFits(
        lateral,
        "--cv-escala-lateral",
        MAX_SCALE_LATERAL,
        MIN_SCALE_LATERAL,
        limit,
      );
      lateralFits = heightAt(lateral, "--cv-escala-lateral", scaleLateral) <= limit;
    }

    cv.classList.remove("cv-midiendo");

    const warning = document.querySelector("[data-aviso-desborde]");
    if (warning) warning.hidden = principalFits && lateralFits;
  }

  // Text laid out in a font that hasn't loaded yet is text of the wrong
  // height, and a fit computed from it is a fit for a page nobody prints.
  document.fonts.ready.then(fitToPage);
})();
