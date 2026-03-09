# Frappe Japanese Translations

Japanese (ja) translation files and management tools for the Frappe/ERPNext ecosystem.

## Supported Apps

| App | Type | Status |
|-----|------|--------|
| frappe | Core | Maintained |
| erpnext | Core | Maintained |
| hrms | Core | Maintained |
| healthcare | Community | Maintained |
| hospitality | Community | Maintained |
| lending | Community | Maintained |
| posawesome | Community | Maintained |

## Quick Start

```bash
# Deploy translations to local bench
./scripts/deploy.sh --bench-path ~/work/frappe-bench

# Check translation coverage
./scripts/coverage.sh

# Full Japanese locale setup (deploy + language settings + cache clear)
./scripts/setup-locale.sh --site dev.localhost
```

## Scripts

| Script | Description |
|--------|-------------|
| `deploy.sh` | Deploy translation CSV files to a Frappe bench |
| `extract.sh` | Extract untranslated strings from apps |
| `coverage.sh` | Report translation coverage per app |
| `import-back.sh` | Import translations back from bench to this repo |
| `setup-locale.sh` | Full Japanese locale setup (deploy + settings + cache) |
| `translate-ai.py` | AI-powered batch translation using Claude API |
| `validate-csv.py` | Validate CSV format, detect duplicates, check placeholders |

## Directory Structure

```
translations/       # Translation CSV files per app
  {app}/ja.csv
scripts/            # Management scripts
glossary/           # Shared glossary for consistent terminology
  glossary.csv
config.json         # App registry and default settings
```

## Docker Support

All shell scripts support Docker environments:

```bash
# Docker mode
./scripts/deploy.sh --docker --project bench-01

# Docker with specific bench path
./scripts/setup-locale.sh --docker --project bench-01 --site admin.example.com
```

## AI Translation

Translate untranslated strings using Claude API:

```bash
# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Translate untranslated strings for an app
python3 scripts/translate-ai.py --app frappe --glossary glossary/glossary.csv

# Review mode (requires human confirmation)
python3 scripts/translate-ai.py --app frappe --review
```

## Glossary

`glossary/glossary.csv` contains standardized term mappings to ensure consistent translations across all apps. Format:

```csv
source,target,domain,notes
Invoice,請求書,Accounting,
Employee,従業員,HR,
```

## Contributing

1. Fork this repository
2. Add or improve translations in `translations/{app}/ja.csv`
3. Run `python3 scripts/validate-csv.py` to check format
4. Submit a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.
