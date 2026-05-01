#!/usr/bin/env python3
"""fixup-po.py — Post-pass cleanups on a translated PO.

Fixes two recurring issues that the main translator can't handle directly:

1. Whitespace pad: legacy human translations that dropped the source's
   leading/trailing whitespace are padded back (no re-translation needed).
2. Pure-whitespace sources: msgstr copied verbatim from msgid.
3. Strip-translate-reattach: empty entries whose msgid has leading/trailing
   whitespace are translated by stripping the whitespace, asking the AI for
   the core, and re-attaching the original whitespace. This sidesteps the
   validator's strict whitespace rule.

Usage:
    fixup-po.py --po translations/frappe/ja.po --glossary glossary/glossary.csv
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import polib

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
_spec = importlib.util.spec_from_file_location("tp", str(Path(__file__).parent / "translate-po.py"))
tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tp)


def is_pure_whitespace(s: str) -> bool:
    return bool(s) and not s.strip()


def split_whitespace(s: str) -> tuple[str, str, str]:
    core = s.strip()
    if not core:
        return s, "", ""
    lead = s[: len(s) - len(s.lstrip())]
    trail = s[len(s.rstrip()) :]
    return lead, core, trail


def fix_whitespace_pad(po: polib.POFile) -> int:
    """Pad existing translations with source's leading/trailing whitespace."""
    fixed = 0
    for e in po:
        if not e.msgstr.strip() or e.obsolete:
            continue
        ok, why = tp.validate_translation(e.msgid, e.msgstr)
        if ok or "whitespace" not in why:
            continue
        lead, _, trail = split_whitespace(e.msgid)
        e.msgstr = lead + e.msgstr.strip() + trail
        ok_after, _ = tp.validate_translation(e.msgid, e.msgstr)
        if ok_after:
            fixed += 1
    return fixed


def fill_pure_whitespace(po: polib.POFile) -> int:
    fixed = 0
    for e in po:
        if e.obsolete or e.msgstr.strip():
            continue
        if is_pure_whitespace(e.msgid):
            e.msgstr = e.msgid
            fixed += 1
    return fixed


def strip_translate_reattach(po: polib.POFile, client, model: str, system_prompt: str) -> int:
    """Translate empty entries that have leading/trailing whitespace by stripping."""
    targets = []
    for e in po:
        if e.obsolete or e.msgstr.strip():
            continue
        if e.msgid != e.msgid.strip() and e.msgid.strip():
            if not tp.is_already_japanese(e.msgid):
                targets.append(e)
    if not targets:
        return 0
    print(f"[reattach] {len(targets)} entries need strip-translate-reattach")

    fixed = 0
    batches = tp.make_batches(targets, 50, 8000)
    for bi, batch in enumerate(batches, 1):
        stripped = [polib.POEntry(msgid=e.msgid.strip(), msgstr="") for e in batch]
        try:
            translations = tp.translate_batch_gemini(client, model, system_prompt, stripped)
        except Exception as exc:
            print(f"  reattach batch {bi}/{len(batches)} FAILED: {exc}", file=sys.stderr)
            continue
        for i, original in enumerate(batch):
            ja_core = translations.get(i, "").strip()
            if not ja_core:
                continue
            lead, _, trail = split_whitespace(original.msgid)
            candidate = lead + ja_core + trail
            ok, _ = tp.validate_translation(original.msgid, candidate)
            if ok:
                original.msgstr = candidate
                if "fuzzy" not in original.flags:
                    original.flags.append("fuzzy")
                fixed += 1
        time.sleep(0.4)
    return fixed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--po", required=True, type=Path)
    p.add_argument("--glossary", type=Path)
    p.add_argument("--no-ai", action="store_true", help="Skip AI re-translate pass (whitespace pad only)")
    p.add_argument("--model", default=tp.DEFAULT_MODEL)
    args = p.parse_args()

    po = polib.pofile(str(args.po))
    pad = fix_whitespace_pad(po)
    pure = fill_pure_whitespace(po)
    reattach = 0
    if not args.no_ai:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print("warn: GEMINI_API_KEY not set; skipping AI reattach pass", file=sys.stderr)
        else:
            from google import genai
            client = genai.Client(api_key=api_key)
            glossary = tp.load_glossary(args.glossary) if args.glossary else {}
            sp = tp.SYSTEM_PROMPT_TEMPLATE.format(glossary_block=tp.format_glossary(glossary))
            reattach = strip_translate_reattach(po, client, args.model, sp)

    po.save(str(args.po))
    print(f"[fixup] {args.po.name}: ws_pad={pad} pure_ws={pure} reattach={reattach}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
