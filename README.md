# Frappe Japanese Translations

Japanese (ja) translation files and tooling for the Frappe / ERPNext ecosystem.
For the five Crowdin-managed apps the canonical contribution path is
[Crowdin](https://crowdin.com/project/frappe); the PO files in this repo are
seed data, a backup mirror, and the source for local-bench deploys.

## Status

| App | Type | Format | Source strings | Coverage | AI-fuzzy¹ |
|-----|------|--------|---------------:|---------:|----------:|
| `frappe` | Core | PO + Crowdin | 6,226 | 100% | 5,305 |
| `erpnext` | Core | PO + Crowdin | 9,937 | 100% | 6,646 |
| `hrms` | Core | PO + Crowdin | 2,239 | 100% | 2,006 |
| `healthcare` (`frappe/health`) | Community | PO + Crowdin | 1,947 | 100% | 1,549 |
| `lending` | Community | PO + Crowdin | 974 | 100% | 205 |
| `posawesome` | Community | Legacy CSV² | — | — | — |

Snapshot taken 2026-06-12 against the latest upstream POTs.
Refresh with `scripts/translate-all.sh`.

Each PO app additionally ships a `version-16/` set (100% coverage, seeded
from the develop set) for stable benches — see
[Version-specific translations](#version-specific-translations).

¹ Entries flagged `#, fuzzy` are AI-suggested (Gemini 2.5 Flash) and require
proofreader review on Crowdin before publication. They are *not* approved
translations.

² The `hospitality` app was dropped from this repo in v2.0 because its upstream
(`aakvatech/Hotel-Management`) is no longer available. The historical CSV is
preserved in git history.

## Two formats, one source of truth

The PO file is the **source of truth** (matches the upstream POT and the
Crowdin project). The CSV file is **derived** for bench-side deployment via
`scripts/deploy.sh` and the Frappe bench's
`apps/{app}/{app}/translations/{lang}.csv` loader. Both are first-class
artifacts and both are kept in sync.

```
upstream main.pot ──► ja.po ──► Crowdin upload (upstream contribution)
                       │
                       └──► ja.csv ──► bench deploy (local / internal patch)
```

`scripts/sync-csv.sh` regenerates ja.csv from ja.po after every translate /
fixup pass.

For `posawesome` (no upstream PO / Crowdin path), CSV is edited directly and
remains the source of truth for that app alone.

## Version-specific translations

`translations/{app}/ja.po` tracks the upstream **develop** branch (matching
the Crowdin develop branch). Stable releases have their own POTs, so each
supported release gets a subdirectory seeded from the develop set:

```
translations/{app}/ja.po                 # develop (Crowdin contribution path)
translations/{app}/version-16/ja.po      # v16 stable (bench deploy path)
translations/{app}/version-16/ja.csv     # derived, deployed via deploy.sh --version
```

`config.json` maps each local version directory to its upstream branch
(`apps.{app}.versions`); note `lending` has no `version-16` branch, so its
v16 set tracks `version-16-hotfix`.

To refresh (or add) a version set, merge the develop ja.po — which acts as
the translation memory — with the version branch's POT, then AI-fill the
small remainder:

```bash
for app in frappe erpnext hrms healthcare lending; do
  src=$app; [ "$app" = healthcare ] && src=health
  br=$(python3 -c "import json;print(json.load(open('config.json'))['apps']['$app']['versions']['version-16'])")
  git -C ~/work/frappe-i18n-upstream/$src fetch --depth=1 origin "+refs/heads/$br:refs/remotes/origin/$br"
  git -C ~/work/frappe-i18n-upstream/$src show "origin/$br:$app/locale/main.pot" > /tmp/$app-v16.pot
  mkdir -p translations/$app/version-16
  msgmerge --no-fuzzy-matching --quiet -o translations/$app/version-16/ja.po \
    translations/$app/ja.po /tmp/$app-v16.pot
  msgattrib --no-obsolete -o translations/$app/version-16/ja.po translations/$app/version-16/ja.po
done
./scripts/translate-all.sh      # picks up version-*/ja.po automatically
./scripts/sync-csv.sh           # regenerates version-*/ja.csv too
```

Only the develop ja.po goes to Crowdin; version sets exist for bench deploy.

## Quick Start

### Deploy current translations to a Frappe bench

```bash
./scripts/setup-locale.sh --site dev.localhost   # full ja locale bring-up
# or
./scripts/deploy.sh                              # CSV deploy only
# v16 bench: use the version-16 CSV set
./scripts/deploy.sh --version version-16
```

### Refresh PO + CSV against the latest upstream POTs

```bash
# 1. Update the upstream POT mirror (see "Upstream POT Mirror" below)
for d in ~/work/frappe-i18n-upstream/*/; do git -C "$d" pull --quiet; done

# 2. Merge the latest POT into the existing PO (preserves translations AND
#    fuzzy flags, drops obsolete strings). Do NOT rebuild via csv-to-po.py —
#    the CSV round-trip cannot carry fuzzy flags, so AI suggestions would be
#    silently promoted to approved translations.
for app in frappe erpnext hrms healthcare lending; do
  src=$app; [ "$app" = healthcare ] && src=health
  msgmerge --no-fuzzy-matching --backup=none --quiet --update \
    translations/$app/ja.po \
    ~/work/frappe-i18n-upstream/$src/$app/locale/main.pot
  msgattrib --no-obsolete -o translations/$app/ja.po translations/$app/ja.po
done

# 3. AI-fill remaining empty msgstr (all 5 PO apps)
export GEMINI_API_KEY=...                        # https://aistudio.google.com/apikey
./scripts/translate-all.sh

# 4. Post-pass cleanup (whitespace pad + strip-translate-reattach)
for app in frappe erpnext hrms healthcare lending; do
  ./scripts/fixup-po.py --po translations/$app/ja.po --glossary glossary/glossary.csv
done

# 5. Sync ja.po back into ja.csv for bench deploy
./scripts/sync-csv.sh

# 6. Push to Crowdin (once Japanese is enabled on the project)
crowdin upload translations -l ja --import-eq-suggestions
```

## Scripts

### PO ⇄ CSV pipeline

| Script | Purpose |
|--------|---------|
| `csv-to-po.py` | CSV → PO using upstream `main.pot` as the canonical msgid source; applies glossary auto-fill; emits a sub-POT of remaining gaps |
| `translate-po.py` | Fill empty `msgstr` via Gemini 2.5 Flash (default) or Anthropic Claude; strict placeholder / Jinja / newline / bracket / whitespace validation; marks AI output `#, fuzzy` |
| `translate-all.sh` | Runs `translate-po.py` over all Crowdin-managed apps |
| `fixup-po.py` | Post-pass cleanup: pads dropped surrounding whitespace; AI strip-translate-reattach for whitespace-bearing entries |
| `po-to-csv.py` | PO → CSV (legacy Frappe shape). The PO is the source of truth; the CSV is regenerated for bench deploy |
| `sync-csv.sh` | Run `po-to-csv.py` over all PO apps in one go |

### Bench deploy / locale setup

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Copy `translations/{app}/ja.csv` into a Frappe bench |
| `setup-locale.sh` | Full ja locale bring-up: deploy + Language doctype + System Settings + cache clear |
| `import-back.sh` | Pull `ja.csv` from a bench back into this repo |
| `extract.sh` | Run `bench get-untranslated` per app |
| `coverage.sh` | Per-app coverage report against a bench |
| `validate-csv.py` | CSV format / placeholder / duplicate check |

### Alternative AI provider

| Script | Status |
|--------|--------|
| `translate-ai.py` | Anthropic Claude + CSV input. Kept as an alternative provider and for ad-hoc CSV-only translation (e.g. `posawesome`); the PO workflow above is preferred for the five Crowdin-managed apps |

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
