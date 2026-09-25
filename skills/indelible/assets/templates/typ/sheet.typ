// indelible sheet template (typst 0.11 or newer).
// scripts/lib/render.py fills the placeholders and writes the body. Every
// learner-facing string arrives as a typst string literal, so nothing inside it
// is read as markup. Unicode maths only (no math mode) in v0.1.
#set document(title: $title_str)
#set page(
  paper: "a4",
  margin: (x: 17mm, top: 15mm, bottom: 20mm),
  footer: context align(center, text(size: 9pt, fill: luma(85))[page #counter(page).display("1 of 1", both: true)]),
)
#set text(font: ("Noto Serif", "Libertinus Serif", "New Computer Modern"), size: 12pt, lang: "$lang")
#set par(leading: 0.7em, justify: false)
#show heading.where(level: 1): set text(size: 18pt)
#show heading.where(level: 2): set text(size: 13.5pt)
#show heading: set block(above: 1.2em, below: 0.7em)
#show raw.where(block: true): it => block(width: 100%, fill: luma(245), stroke: 0.5pt + luma(180),
  inset: (x: 8pt, y: 6pt), radius: 2pt, breakable: false, text(size: 10pt, it))

#let hint(body) = text(size: 9.5pt, fill: luma(70), body)
#let boxed(body) = block(width: 100%, stroke: 0.9pt + luma(30), inset: (x: 10pt, y: 8pt), radius: 3pt, body)
#let shaded(body) = block(width: 100%, fill: luma(238), inset: (x: 10pt, y: 8pt), radius: 3pt, body)
#let answer(h) = rect(width: 100%, height: h, stroke: 0.9pt + luma(30), radius: 2pt)
#let fillin(w) = box(width: w, height: 1.4em, stroke: (bottom: 0.6pt + luma(40)))
#let checkline() = [Check: #box(width: 1fr, height: 1.8em, stroke: (bottom: 0.6pt + luma(40)))]

$body
