"""Turns a proposal into a laid-out CV, two ways.

`fill.py` + `templates.py` fill a `.docx` the user opens in Word;
`html_layout.py` + `html_templates.py` lay the same content out as a page
the user's browser prints to PDF. Neither generates a file format the app
would have to design from scratch, and both share one field catalog — see
`docx-templates/README.md` for the contract and `html-templates/README.md`
for what changes on the HTML side.
"""
