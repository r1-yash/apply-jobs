#!/usr/bin/env python3
"""Fact-check a tailored resume against the original, then compile it to a one-page PDF.

  python3 scripts/build_resume.py <job_id>              # check + build jobs/<job_id>/resume.tex
  python3 scripts/build_resume.py <job_id> --check-only # fact-check only
  python3 scripts/build_resume.py --tex path/to/x.tex   # check + build any file

The tailored .tex may only REORDER and REWORD what is already in resume/yash.tex.
ERRORS (block the PDF):
  - header (name/contacts) or EDUCATION section differs from the original
  - more \\item bullets than the original
  - a number not present in the original resume or facts.yaml
  - a URL not present in the original
  - a tech/proper term (has a capital, digit or symbol, e.g. Kubernetes, C++, Node.js)
    not present in the original or facts.yaml
WARNINGS (printed for review, do not block):
  - ordinary lowercase words that are new (rewording)
Layout changes in the preamble (margins, spacing) are allowed and not checked.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "resume" / "yash.tex"
FACTS = ROOT / "facts.yaml"
JOBS = ROOT / "jobs"

# Words allowed in rewording without review noise (connectives etc.)
COMMON = set("""
a an the and or of to in on for with by from at as into via over under using use used
that which who while is are was were be been this these those its it their our my
across through within without than then also both each per all any new more most
""".split())

# New words that would add leadership / scale / impact claims -> ERROR if not in the original.
RISKY = set("""
led lead leading managed manager mentored mentoring team teams founded co-founded owned
users customers clients million millions billion thousand thousands scaled scalable scale
revenue saved increased improved boosted grew growth accelerated award awarded winner won
published patent senior expert
""".split())


def items(tex: str) -> list[str]:
    """Each \\item's text (up to the next \\item or \\end)."""
    return re.findall(r"\\item(.*?)(?=\\item|\\end\{itemize\})", strip_comments(tex), re.S)


def overlap(a: str, b: str) -> float:
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return len(wa & wb) / (len(wa | wb) or 1)


# ---------------------------------------------------------------- text helpers
def body(tex: str) -> str:
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", tex, re.S)
    if not m:
        sys.exit("No \\begin{document}...\\end{document} found")
    return m.group(1)


def strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)


def urls(tex: str) -> set[str]:
    return set(re.findall(r"\\href\{([^}]*)\}", tex)) | set(re.findall(r"\\url\{([^}]*)\}", tex))


def plain(tex: str) -> str:
    """LaTeX body -> roughly the visible text."""
    t = strip_comments(tex)
    t = re.sub(r"\\href\{[^}]*\}", "", t)                 # drop URL arg, keep link text
    t = re.sub(r"\\projhead\{([^}]*)\}\{[^}]*\}\{([^}]*)\}", r"\1 \2", t)
    t = re.sub(r"\\begin\{tabular\}\{(?:[^{}]|\{[^{}]*\})*\}", " ", t)   # column spec is layout
    t = re.sub(r"\\(begin|end)\{[^}]*\}(\[[^\]]*\])?(\{[^}]*\})?", " ", t)
    t = re.sub(r"\\fontsize\{[^}]*\}\{[^}]*\}", " ", t)
    t = re.sub(r"\\(vspace|hspace)\*?\{[^}]*\}", " ", t)
    t = re.sub(r"\\\\(\[[^\]]*\])?", " ", t)
    t = t.replace("\\%", "%").replace("\\&", "&").replace("\\#", "#").replace("\\_", "_")
    t = t.replace("--", "-").replace("\\textbar{}", "|").replace("\\textbar", "|")
    t = re.sub(r"\\[a-zA-Z]+\*?", " ", t)                 # remaining commands
    t = re.sub(r"[{}]", " ", t)
    return re.sub(r"\s+", " ", t)


def section(tex: str, name: str) -> str:
    m = re.search(rf"\\section\*?\{{{re.escape(name)}\}}(.*?)(?=\\section\*?\{{|\\end\{{document\}})", tex, re.S)
    return m.group(1).strip() if m else ""


def header(tex: str) -> str:
    b = body(tex)
    return b.split("\\section", 1)[0].strip()


NUM_RE = re.compile(r"\d+(?:[.,/]\d+)*")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#./\-]*[A-Za-z0-9+#]|[A-Za-z0-9]")


def numbers(text: str) -> set[str]:
    return set(NUM_RE.findall(text))


def tokens(text: str) -> list[tuple[str, bool]]:
    """(token, sentence_initial) pairs."""
    out = []
    for m in TOKEN_RE.finditer(text):
        before = text[: m.start()].rstrip()
        initial = before == "" or before[-1] in ".:;|•"
        out.append((m.group(0).strip(".-/"), initial))
    return out


def is_term(tok: str) -> bool:
    return bool(re.search(r"[A-Z0-9+#]", tok[1:] if tok else "") or re.search(r"[0-9+#./]", tok))


# ---------------------------------------------------------------- check
def check(tailored_path: Path) -> tuple[list[str], list[str]]:
    orig = ORIGINAL.read_text()
    new = tailored_path.read_text()
    facts_text = FACTS.read_text() if FACTS.exists() else ""
    if FACTS.exists():
        facts_text = yaml.safe_dump(yaml.safe_load(facts_text), allow_unicode=True)

    errors, warnings = [], []

    if header(new) != header(orig):
        errors.append("Header (name/contacts) differs from resume/yash.tex. It must be identical.")
    if section(new, "EDUCATION") != section(orig, "EDUCATION"):
        errors.append("EDUCATION section differs from resume/yash.tex. It must be identical.")

    n_orig, n_new = body(orig).count("\\item"), body(new).count("\\item")
    if n_new > n_orig:
        errors.append(f"{n_new} bullets vs {n_orig} in the original. Bullets may be dropped, never added.")

    bad_urls = urls(body(new)) - urls(body(orig))
    for u in sorted(bad_urls):
        errors.append(f"New URL not in original: {u}")

    src_plain = plain(body(orig)) + " " + facts_text
    new_plain = plain(body(new))

    src_nums = numbers(src_plain)
    for n in sorted(numbers(new_plain) - src_nums):
        errors.append(f"Number '{n}' is not in the original resume or facts.yaml")

    # Numbers must stay in the bullet they came from (no moving "5" into a new claim).
    orig_items = [plain(i) for i in items(body(orig))]
    for item in items(body(new)):
        p = plain(item)
        nums = numbers(p)
        if not nums or not orig_items:
            continue
        best = max(orig_items, key=lambda o: overlap(o, p))
        moved = nums - numbers(best)
        if moved:
            errors.append(f"Number(s) {sorted(moved)} not in the matching original bullet: \"{p.strip()[:90]}...\"")

    src_vocab = {t.lower() for t, _ in tokens(src_plain)}
    for tok, _ in tokens(new_plain):
        low = tok.lower()
        if low in RISKY and low not in src_vocab:
            errors.append(f"Claim word '{tok}' is not in the original. Leadership/scale/impact claims can't be added.")
    new_terms, new_words = set(), set()
    for tok, initial in tokens(new_plain):
        low = tok.lower()
        if low in src_vocab or low in COMMON or low in RISKY or NUM_RE.fullmatch(tok):
            continue
        if is_term(tok) or (tok[:1].isupper() and not initial):
            new_terms.add(tok)
        else:
            new_words.add(low)
    for t in sorted(new_terms):
        errors.append(f"Term '{t}' is not in the original resume or facts.yaml (possible invented skill)")
    if new_words:
        warnings.append("New wording to review: " + ", ".join(sorted(new_words)))
    return errors, warnings


# ---------------------------------------------------------------- build
def page_count(log: Path) -> int | None:
    m = re.search(r"Output written on .*?\((\d+) pages?", log.read_text(errors="ignore")) if log.exists() else None
    return int(m.group(1)) if m else None


def build(tex_path: Path, out_pdf: Path) -> int:
    if not shutil.which("tectonic"):
        sys.exit("tectonic not found. Install it with: brew install tectonic")
    build_dir = tex_path.parent / ".build"
    build_dir.mkdir(exist_ok=True)
    r = subprocess.run(["tectonic", "--keep-logs", "--outdir", str(build_dir), str(tex_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit("LaTeX compile failed")
    pages = page_count(build_dir / (tex_path.stem + ".log"))
    shutil.move(str(build_dir / (tex_path.stem + ".pdf")), out_pdf)
    shutil.rmtree(build_dir, ignore_errors=True)
    return pages or 0


def pdf_name() -> str:
    name = "Resume"
    if FACTS.exists():
        n = (yaml.safe_load(FACTS.read_text()).get("profile") or {}).get("name")
        if n:
            name = re.sub(r"\W+", "_", n).strip("_") + "_Resume"
    return name + ".pdf"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job_id", nargs="?")
    ap.add_argument("--tex", help="explicit .tex path instead of jobs/<job_id>/resume.tex")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()
    if not (args.job_id or args.tex):
        ap.error("give a job_id or --tex")
    tex = Path(args.tex) if args.tex else JOBS / args.job_id / "resume.tex"
    if not tex.exists():
        sys.exit(f"{tex} not found")

    errors, warnings = check(tex)
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    if errors:
        print(f"\nFact-check FAILED ({len(errors)} error(s)). No PDF built.")
        return 1
    print("Fact-check passed.")
    if args.check_only:
        return 0

    out = tex.parent / pdf_name()
    pages = build(tex, out)
    print(f"Built {out} ({pages} page{'s' if pages != 1 else ''})")
    if pages != 1:
        print("ERROR Resume must be exactly 1 page. Tighten spacing or drop the least relevant bullet.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
