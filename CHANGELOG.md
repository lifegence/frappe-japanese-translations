# Changelog

All notable changes to this project are recorded here.

## [Unreleased]

### Added
- **PO-format translation files** (`translations/{app}/ja.po`) for the five
  Crowdin-managed apps: `frappe`, `erpnext`, `hrms`, `healthcare`, `lending`.
- `scripts/csv-to-po.py` — converts legacy `ja.csv` into gettext PO using the
  upstream `main.pot` as the authoritative source of msgids; applies glossary
  auto-fill on exact matches; emits a sub-POT of untranslated entries.
- `scripts/translate-po.py` — AI-fill empty `msgstr` via Gemini 2.5 Flash
  (default) or Anthropic Claude. Strict validation of placeholders, Jinja,
  newlines, Japanese bracket balance, and surrounding whitespace. All AI
  output is flagged `#, fuzzy` for proofreader review.
- `scripts/fixup-po.py` — post-pass that pads dropped leading/trailing
  whitespace in legacy translations and runs an AI strip-translate-reattach
  cycle for whitespace-bearing entries that the strict validator would
  otherwise reject.
- `scripts/translate-all.sh` — orchestrates `translate-po.py` over all
  Crowdin-managed apps.
- `CHANGELOG.md` — this file.

### Changed
- `config.json` bumped to **v2.0.0**:
  - explicit `format` (`po` | `csv`) and `crowdin` (boolean) per app,
  - added `defaults.pot_root` for the upstream POT mirror location,
  - clarified app types (core / community).
- `README.md` rewritten around the **PO + Crowdin** workflow as the primary
  contribution path; legacy CSV / bench-deploy path is documented as the
  parallel track for `posawesome` and local-only forks.

### Removed
- `hospitality` app entry from `config.json` — its upstream repository
  (`aakvatech/Hotel-Management`) is no longer reachable (HTTP 404). The
  historical `translations/hospitality/ja.csv` is preserved in git history;
  the directory may be removed in a future release.

### Coverage snapshot (2026-05-01)

| App | Source strings | Coverage | AI-fuzzy |
|---|---:|---:|---:|
| frappe | 6,143 | 99.9% | 5,213 |
| erpnext | 9,350 | 100% | 5,981 |
| hrms | 2,216 | 100% | 1,982 |
| healthcare | 1,947 | 100% | 1,549 |
| lending | 967 | 100% | 198 |
| **TOTAL** | **20,623** | **99.9%** | **14,923** |

Eleven entries (long HTML / Jinja Print Format help blocks) remain untranslated;
they are left for human review on Crowdin. All five PO files validate cleanly
with `msgfmt --check`.

## 1.0.0 — 2026-03-09

### Added
- Initial release of the toolkit: legacy CSV translations for seven apps,
  glossary, AI translator (Anthropic Claude, CSV input), bench-deploy and
  validation scripts.
