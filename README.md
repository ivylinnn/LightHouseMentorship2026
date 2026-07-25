# 领航计划 · Lighthouse Mentorship — Homepage

Redesigned homepage for **领航计划 (Lighthouse Mentorship)** — a nine-month deep
mentorship program and a lifelong Chinese-professional community, serving the Bay
Area, Seattle, New York, and Boston. Registered 501(c)(3) nonprofit, founded 2015.

This is a single, self-contained static page (`index.html`) with an inline
stylesheet and vanilla JS — no build step, no dependencies. Just open it.

## View it

- **Locally:** open [`index.html`](index.html) in any modern browser.
- **Or serve it:** `python3 -m http.server 8000` then visit
  <http://localhost:8000/>.

## Design highlights

A dark "moonlight / voyager" aesthetic built around the 领航 (navigation) metaphor:

- **Live deadline countdown** in the hero and final CTA (days until the cohort
  deadline, computed client-side).
- **Informative hero** — a concrete lead line and credibility row under the
  poetic headline, so the value proposition reads in seconds.
- **Four-city constellation** brand art (Silicon Valley · Seattle · New York ·
  Boston) drawn in SVG.
- **Status-aware CTAs** with a pulsing "open for applications" indicator.
- **Attributed-testimonial structure**, **semantic horizontal `<nav>`**,
  scroll-margin anchoring, `:focus-visible` states, a single `<h1>` with clean
  heading order, and `prefers-reduced-motion` support.

## Page sections

Hero → stats → about → how it works → tracks → mentors → stories →
community & events → testimonials → FAQ → final CTA → footer.

## Before going live — real data to swap in

The trust-critical content currently uses clearly-marked placeholders (see the
`<!-- -->` comments in the markup):

1. **Mentor photos, names, and companies** (currently single-character avatars).
2. **Testimonial attribution** — replace placeholder names with
   permission-cleared real ones.
3. **Confirm the stats** (11 years / 1,000+ alumni / 300+ mentors / 4 cities).
4. **Point CTAs at real destinations** (`/apply/west`, `/mentors`, `/stories`)
   once those pages exist — they're same-page anchors for now.

## License / ownership

© 领航计划组织 · Lighthouse Mentorship · 501(c)(3) nonprofit, EIN 99-1905606.
Internal project asset — not for redistribution.
