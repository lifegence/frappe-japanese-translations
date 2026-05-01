#!/usr/bin/env python3
"""translate-po.py — AI-fill empty msgstr in a gettext PO file.

Defaults to Gemini 2.5 Flash (cheap/free tier friendly). Reads <po>, batches
entries with empty msgstr, asks the model to translate them while preserving
placeholders / HTML / Jinja, validates the output against a placeholder check,
and writes back into the same PO with the entry marked `#, fuzzy` so the
upstream Crowdin proofreader workflow treats it as a suggestion to review.

Usage:
    # Dry-run: show what would be translated, no API calls
    translate-po.py --po translations/frappe/ja.po --dry-run

    # First 100 entries only (for sanity check)
    translate-po.py --po translations/frappe/ja.po \\
        --glossary glossary/glossary.csv --limit 100

    # Full run
    translate-po.py --po translations/frappe/ja.po \\
        --glossary glossary/glossary.csv

Requires:
    pip install google-genai polib
    export GEMINI_API_KEY=...   # https://aistudio.google.com/apikey
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import polib

PLACEHOLDER_RE = re.compile(r"\{[\w.]*\}|%\([\w.]+\)s|%[sd]")
JINJA_RE = re.compile(r"\{%-?.*?-?%\}|\{\{.*?\}\}", re.DOTALL)
JA_CHAR_RE = re.compile(r"[぀-ヿ一-鿿]")

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_BATCH_SIZE = 100
DEFAULT_BATCH_CHAR_BUDGET = 18000   # cap source chars per batch to keep latency sane
MAX_RETRIES = 3
PER_REQUEST_SLEEP = 0.4             # ~150 RPM, safely under free tier 100 RPM

SYSTEM_PROMPT_TEMPLATE = """You translate Frappe/ERPNext ERP system UI strings from English to natural business Japanese.

Rules (apply strictly):
- Use formal business Japanese (です・ます調) for sentences; for short UI labels prefer concise noun forms.
- Preserve placeholders EXACTLY as in source: {{0}}, {{name}}, %(name)s, %s, %d, etc. Do not translate inside braces.
- Preserve HTML tags, attributes, and Jinja constructs ({{% %}} and {{{{ }}}}). Translate only the natural-language text inside.
- Preserve newline characters (\\n) exactly. Do NOT convert \\n to <br> and do NOT drop \\n. The output MUST contain the same number of newlines as the input, in the same positions relative to surrounding text.
- Preserve leading/trailing whitespace exactly as in source.
- Balance any brackets you add. If you use Japanese quotes 「 you MUST close with 」 in the same string. Never emit unmatched 「 or 」.
- Keep brand names (Frappe, ERPNext, etc.), URLs, file paths, code identifiers, and field/DocType names in their original form.
- If the source already contains Japanese, return it unchanged.
- Apply the glossary below as the authoritative term mapping (highest priority — overrides any other choice).
- For ambiguous business terms, prefer the ERP / accounting / inventory / HR domain meaning.
- Do NOT add explanations, quotes, or surrounding whitespace that wasn't in the source.

Glossary (source → target):
{glossary_block}

Output format: JSON only. Schema:
{{"translations": [{{"id": <int>, "ja": "<japanese>"}}, ...]}}
The output array must contain exactly one entry per input id, in any order.
"""


@dataclass
class Stats:
    total: int = 0
    requested: int = 0
    translated: int = 0
    placeholder_failed: int = 0
    json_failed: int = 0
    skipped_already_ja: int = 0
    api_calls: int = 0


def load_glossary(path: Path | None, max_terms: int = 300) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    import csv
    g: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            src = (row.get("source") or "").strip()
            tgt = (row.get("target") or "").strip()
            if src and tgt:
                g[src] = tgt
            if len(g) >= max_terms:
                break
    return g


def format_glossary(glossary: dict[str, str]) -> str:
    if not glossary:
        return "(none)"
    return "\n".join(f"- {k} → {v}" for k, v in glossary.items())


def placeholders_of(text: str) -> tuple[list[str], list[str]]:
    return sorted(PLACEHOLDER_RE.findall(text)), sorted(JINJA_RE.findall(text))


def validate_translation(src: str, dst: str) -> tuple[bool, str]:
    if not dst.strip():
        return False, "empty translation"
    src_ph, src_jinja = placeholders_of(src)
    dst_ph, dst_jinja = placeholders_of(dst)
    if src_ph != dst_ph:
        return False, f"placeholder mismatch: {src_ph} → {dst_ph}"
    if src_jinja != dst_jinja:
        return False, f"jinja mismatch"
    if src.count("\n") != dst.count("\n"):
        return False, f"newline count: {src.count(chr(10))} → {dst.count(chr(10))}"
    if dst.count("「") != dst.count("」"):
        return False, f"unbalanced brackets: 「={dst.count(chr(0x300c))} 」={dst.count(chr(0x300d))}"
    if src.startswith(" ") != dst.startswith(" ") or src.endswith(" ") != dst.endswith(" "):
        return False, "leading/trailing whitespace mismatch"
    return True, ""


def is_already_japanese(text: str) -> bool:
    return bool(JA_CHAR_RE.search(text))


def collect_targets(po: polib.POFile, include_fuzzy: bool) -> list[polib.POEntry]:
    targets = []
    for e in po:
        if e.obsolete:
            continue
        if not e.msgstr.strip():
            targets.append(e)
        elif include_fuzzy and "fuzzy" in e.flags:
            targets.append(e)
    return targets


def make_batches(entries: list[polib.POEntry], size: int, char_budget: int) -> list[list[polib.POEntry]]:
    batches, cur, cur_chars = [], [], 0
    for e in entries:
        n = len(e.msgid)
        if cur and (len(cur) >= size or cur_chars + n > char_budget):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(e)
        cur_chars += n
    if cur:
        batches.append(cur)
    return batches


def translate_batch_gemini(client, model: str, system_prompt: str, batch: list[polib.POEntry]) -> dict[int, str]:
    from google.genai import types

    payload = [{"id": i, "src": e.msgid} for i, e in enumerate(batch)]
    user_msg = "Translate each item below. Return JSON only.\n\n" + json.dumps(payload, ensure_ascii=False)

    response_schema = {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "ja": {"type": "string"},
                    },
                    "required": ["id", "ja"],
                },
            },
        },
        "required": ["translations"],
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=user_msg,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=0.2,
                ),
            )
            data = json.loads(resp.text)
            return {item["id"]: item["ja"] for item in data["translations"]}
        except Exception as exc:
            last_err = exc
            wait = 2 ** attempt
            print(f"  retry {attempt}/{MAX_RETRIES} after error: {exc}; sleep {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"batch failed after {MAX_RETRIES} retries: {last_err}")


def run(args) -> int:
    po_path = args.po
    po = polib.pofile(str(po_path))

    glossary = load_glossary(args.glossary)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(glossary_block=format_glossary(glossary))

    targets = collect_targets(po, include_fuzzy=args.retry_fuzzy)
    stats = Stats(total=len(po), requested=len(targets))

    # Filter out already-Japanese sources (rare but possible) — keep msgstr empty,
    # we don't want to "translate" them.
    targets = [e for e in targets if not is_already_japanese(e.msgid)]
    stats.skipped_already_ja = stats.requested - len(targets)

    if args.limit:
        targets = targets[: args.limit]

    print(f"[plan] po entries={stats.total} untranslated={stats.requested} "
          f"skipped(already-ja)={stats.skipped_already_ja} this-run={len(targets)}")

    if args.dry_run or not targets:
        print("[dry-run] no API calls made" if args.dry_run else "[done] nothing to translate")
        return 0

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("error: GEMINI_API_KEY not set", file=sys.stderr)
        return 2

    from google import genai
    client = genai.Client(api_key=api_key)

    batches = make_batches(targets, args.batch, args.char_budget)
    print(f"[run] {len(batches)} batches, model={args.model}")

    fuzzy_flag = "fuzzy"
    for bi, batch in enumerate(batches, 1):
        t0 = time.time()
        try:
            translations = translate_batch_gemini(client, args.model, system_prompt, batch)
        except Exception as exc:
            print(f"  batch {bi}/{len(batches)} FAILED: {exc}", file=sys.stderr)
            stats.json_failed += len(batch)
            continue
        stats.api_calls += 1

        applied, ph_fail = 0, 0
        for i, entry in enumerate(batch):
            ja = translations.get(i, "").strip()
            ok, why = validate_translation(entry.msgid, ja)
            if not ok:
                ph_fail += 1
                if args.verbose:
                    print(f"    skip [{why}] id={i} src={entry.msgid[:60]!r}")
                continue
            entry.msgstr = ja
            if fuzzy_flag not in entry.flags:
                entry.flags.append(fuzzy_flag)
            applied += 1
        stats.translated += applied
        stats.placeholder_failed += ph_fail

        dt = time.time() - t0
        print(f"  batch {bi}/{len(batches)} size={len(batch)} ok={applied} ph_fail={ph_fail} ({dt:.1f}s)")

        # Periodic save so a crash doesn't lose work
        if bi % args.save_every == 0:
            po.save(str(po_path))

        time.sleep(PER_REQUEST_SLEEP)

    po.save(str(po_path))
    print("[done]",
          f"translated={stats.translated} ph_fail={stats.placeholder_failed}",
          f"json_fail={stats.json_failed} api_calls={stats.api_calls}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--po", required=True, type=Path, help="PO file to fill")
    p.add_argument("--glossary", type=Path, help="Glossary CSV (source,target,domain,notes)")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model (default: {DEFAULT_MODEL})")
    p.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="Max entries per batch")
    p.add_argument("--char-budget", type=int, default=DEFAULT_BATCH_CHAR_BUDGET, help="Max source chars per batch")
    p.add_argument("--limit", type=int, help="Stop after N entries (for sanity runs)")
    p.add_argument("--retry-fuzzy", action="store_true", help="Also re-translate entries flagged fuzzy")
    p.add_argument("--save-every", type=int, default=5, help="Save PO every N batches")
    p.add_argument("--dry-run", action="store_true", help="Plan only, no API calls")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if not args.po.exists():
        p.error(f"po not found: {args.po}")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
