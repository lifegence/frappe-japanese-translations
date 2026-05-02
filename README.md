# Frappe Japanese Translations

Japanese (ja) translation files and tooling for the Frappe / ERPNext ecosystem.
For the five Crowdin-managed apps the canonical contribution path is
[Crowdin](https://crowdin.com/project/frappe); the PO files in this repo are
seed data, a backup mirror, and the source for local-bench deploys.

## Status

| App | Type | Format | Source strings | Coverage | AI-fuzzy¹ |
|-----|------|--------|---------------:|---------:|----------:|
| `frappe` | Core | PO + Crowdin | 6,143 | 99.9% | 5,213 |
| `erpnext` | Core | PO + Crowdin | 9,350 | 100% | 5,981 |
| `hrms` | Core | PO + Crowdin | 2,216 | 100% | 1,982 |
| `healthcare` (`frappe/health`) | Community | PO + Crowdin | 1,947 | 100% | 1,549 |
| `lending` | Community | PO + Crowdin | 967 | 100% | 198 |
| `posawesome` | Community | Legacy CSV² | — | — | — |

Snapshot taken 2026-05-01 against the latest upstream POTs.
Refresh with `scripts/translate-all.sh`.

¹ Entries flagged `#, fuzzy` are AI-suggested (Gemini 2.5 Flash) and require
proofreader review on Crowdin before publication. They are *not* approved
translations.

² The `hospitality` app was dropped from this repo in v2.0 because its upstream
(`aakvatech/Hotel-Management`) is no longer available. The historical CSV is
preserved in git history.

## Workflows

This repo supports two parallel paths, depending on the app:

### A. PO + Crowdin (the 5 apps in the table above)

Translate / proofread on the Crowdin project; Frappe's bot syncs translations
back to upstream GitHub PRs (see each app's `crowdin.yml`). The PO files in
`translations/{app}/ja.po` here are the seed data uploaded into Crowdin.

### B. Legacy CSV (posawesome, and any local-only fork)

Edit `translations/{app}/ja.csv` directly and deploy to a local Frappe bench
using `scripts/deploy.sh`. There is no upstream contribution path for these
apps.

## Quick Start

```bash
# Deploy current translations to a local bench
./scripts/setup-locale.sh --site dev.localhost   # full ja locale bring-up

# Refresh the PO files against the latest upstream POTs and AI-fill gaps
./scripts/csv-to-po.py --pot ~/work/frappe-i18n-upstream/frappe/frappe/locale/main.pot \
                      --csv translations/frappe/ja.csv \
                      --output translations/frappe/ja.po \
                      --apply-glossary glossary/glossary.csv

export GEMINI_API_KEY=...                        # https://aistudio.google.com/apikey
./scripts/translate-all.sh                       # AI-fill empty msgstr in all 5 PO apps

# Push to Crowdin (once Japanese is enabled on the project)
crowdin upload translations -l ja --import-eq-suggestions
```

## Scripts

### PO workflow (current primary)

| Script | Purpose |
|--------|---------|
| `csv-to-po.py` | Convert legacy `ja.csv` into gettext PO using the upstream `main.pot` as the canonical msgid source; applies glossary auto-fill; emits a sub-POT of remaining gaps |
| `translate-po.py` | AI-fill empty `msgstr` via Gemini 2.5 Flash (default) or Anthropic Claude. Validates placeholders / Jinja / newlines / brackets / surrounding whitespace. Marks all AI output `#, fuzzy` |
| `translate-all.sh` | Runs `translate-po.py` over all Crowdin-managed apps |
| `fixup-po.py` | Post-pass cleanup: pads dropped leading/trailing whitespace; AI strip-translate-reattach for whitespace-bearing entries the strict validator would otherwise reject |

### Bench / CSV workflow

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Copy `translations/{app}/ja.csv` into a Frappe bench |
| `setup-locale.sh` | Full ja locale bring-up: deploy + Language doctype + System Settings + cache clear |
| `import-back.sh` | Pull `ja.csv` from a bench back into this repo |
| `extract.sh` | Run `bench get-untranslated` per app |
| `coverage.sh` | Per-app coverage report (CSV-format) |
| `validate-csv.py` | CSV format / placeholder / duplicate check |

### Legacy

| Script | Status |
|--------|--------|
| `translate-ai.py` | Anthropic Claude + CSV input. Superseded by `translate-po.py`; kept for reference and for ad-hoc CSV translation against `posawesome` |

## AI Translation

`translate-po.py` defaults to **Gemini 2.5 Flash** because the free tier
(1,500 req/day) covers a full pass over all five apps in one day at $0.

Setup:

```bash
pip install --user google-genai polib
export GEMINI_API_KEY=...           # https://aistudio.google.com/apikey
./scripts/translate-all.sh          # ~15-25 min for ~15k entries
```

Strict validation drops any AI output that fails to preserve placeholders
(`{0}`, `%(name)s`, `%s`), Jinja constructs (`{% %}`, `{{ }}`), newlines,
Japanese bracket balance (`「」`), or surrounding whitespace. Rejected entries
are left empty in the PO and surface back as gaps on the next run.

All accepted AI output is flagged `#, fuzzy` so Crowdin presents it as a
suggestion needing human review, not a published translation.

## Crowdin Upload

Once Japanese is enabled for the project on Crowdin:

```bash
crowdin upload translations -l ja --import-eq-suggestions
```

Or via the web UI: open each project, go to **Resources**, upload
`translations/{app}/ja.po` with **"Mark uploaded translations as needing
review"** enabled so the fuzzy entries land in the proofreader queue.

## Upstream POT Mirror

Refreshing PO files against the latest upstream needs the source POTs. The
recommended layout keeps a thin sparse-checkout mirror separate from any dev
benches:

```bash
mkdir -p ~/work/frappe-i18n-upstream && cd ~/work/frappe-i18n-upstream
clone_locale() {
  git clone --filter=blob:none --no-checkout --depth=1 "$2" "$1"
  git -C "$1" sparse-checkout init --cone
  git -C "$1" sparse-checkout set "$3"
  git -C "$1" checkout HEAD
}
clone_locale frappe   https://github.com/frappe/frappe   frappe/locale
clone_locale erpnext  https://github.com/frappe/erpnext  erpnext/locale
clone_locale hrms     https://github.com/frappe/hrms     hrms/locale
clone_locale health   https://github.com/frappe/health   healthcare/locale
clone_locale lending  https://github.com/frappe/lending  lending/locale
```

Refresh later with a simple `git -C <repo> pull`.

## Glossary

`glossary/glossary.csv` defines authoritative term mappings:

```csv
source,target,domain,notes
Account,勘定科目,Accounting,General ledger account
Employee,従業員,HR,
```

The glossary is injected into every AI translation prompt and used by
`csv-to-po.py --apply-glossary` for exact-match auto-fill.

## Contributing

- **Translations**: contribute via Crowdin (preferred) — the five PO apps sync
  back to upstream automatically. Direct PRs to `translations/*.po` here are
  accepted but Crowdin remains the source of truth.
- **Glossary additions**: PR to `glossary/glossary.csv`.
- **Tooling / docs**: PR to `scripts/` or `README.md`.

## License

MIT — see [LICENSE](LICENSE).
