// Writing into a textarea on the user's behalf, keeping their undo history.
//
// Both AI helpers over a text the user wrote — marking the "About me" gaps
// and splitting a paragraph into bullets — replace what is in a field, and
// both have to leave Ctrl+Z working: a proposal that cannot be undone the
// way any other edit is undone stops feeling like a suggestion. That is what
// `execCommand` buys here; it is deprecated with no replacement for this, so
// the fallback writes the value directly and only loses the undo entry.
window.Ancla = window.Ancla || {};

window.Ancla.replaceSelection = (field, text) => {
  field.focus();
  if (!document.execCommand || !document.execCommand("insertText", false, text)) {
    const { selectionStart: start, selectionEnd: end, value } = field;
    field.value = value.slice(0, start) + text + value.slice(end);
    field.setSelectionRange(start + text.length, start + text.length);
  }
  field.dispatchEvent(new Event("input", { bubbles: true }));
};

window.Ancla.replaceAll = (field, text) => {
  field.setSelectionRange(0, field.value.length);
  window.Ancla.replaceSelection(field, text);
};
