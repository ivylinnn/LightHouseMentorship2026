# 领航计划 · Lighthouse Mentorship — Website (2026 redesign)

Redesigned site for **领航计划 (Lighthouse Mentorship)** — a nine-month deep
mentorship program and a lifelong Chinese-professional community, serving the Bay
Area, Seattle, New York, and Boston. Registered 501(c)(3) nonprofit, founded 2015,
EIN 99-1905606.

Static, self-contained HTML pages with inline CSS and vanilla JS — no build step,
no dependencies.

## Pages

| File | Page | Notes |
|---|---|---|
| `index.html` | Homepage | Hero, About, Program Format, Cohort Groups, Mentors, In Their Words, Journal, Organizers, CTA |
| `groups.html` | 学员组别 / Cohort Groups | Four groups with requirements, outcomes and sample mentors |
| `mentors.html` | 导师团队 / Our Mentors | West / East region toggle, grouped mentor cards, sticky side nav |
| `docs/linghang_website_text_ZH_EN.xlsx` | Copy deck | All strings, Chinese + English (live-site extraction + mockup strings) |

## Bilingual (中文 / EN)

Every page has an **EN / 中文** toggle in the header.

- Static copy: Chinese is the source in the markup; English lives in `data-en`
  attributes (`data-en-alt` for image alt text).
- JS-rendered data (groups, timeline, quotes, posts, orgs, mentor bios): Chinese
  fields plus matching `*_en` fields; `render()` / `renderAll()` re-draws on switch.
- The choice persists across pages via `localStorage` (`lh-lang`) and updates
  `<title>` and `<html lang>`.
- The full string inventory is in the spreadsheet under `docs/`.

## View it

- **Locally:** open [`index.html`](index.html) in any modern browser.
- **Or serve it:** `python3 -m http.server 8000` then visit
  <http://localhost:8000/>.

## Assets

Pages reference `web_assets/` (logo, hero images, mentor photos, dimension
photos) — all committed. Note: `web_assets/dims/` holds the smaller,
page-referenced versions of the four dimension photos (深度/广度/高度/圈子); the
larger same-named files at the `web_assets/` root are unused by the pages and
can be removed if you want to trim the repo.

## Before going live — real data to swap in

1. **Mentor names, titles, photos, bios** — currently a mix of Airtable snippets
   and placeholders (`职位待补` / `Title TBD`, `简介待从 Airtable 导入`).
2. **Journal posts** — third card is a placeholder; sync from the WeChat account or CMS.
3. **Confirm organization names** (e.g. `THAA-NC` vs `THUAA-NC`; live site lists
   USTCIF / MIT CEO where the mockup lists USTCSVAA / Stanford CEO).
4. **Point CTAs at real destinations** — apply links and community login are `#` for now.

## License / ownership

© 领航计划组织 · Lighthouse Mentorship · 501(c)(3) nonprofit, EIN 99-1905606.
Internal project asset — not for redistribution.
