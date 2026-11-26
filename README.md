# apply-jobs

A Claude Code skill (`/job-search`) that automates an internship and new-grad job search:

1. **Find**: pulls postings straight from company career boards (Greenhouse, Lever, Ashby public APIs). No LinkedIn scraping.
2. **Triage**: scores each job description against your own facts file as **apply / stretch / skip**, with cited reasons.
3. **Prepare** *(in progress)*: tailors a resume PDF to each JD from your LaTeX source.
4. **Form-fill** *(planned)*: fills the application in Chrome and stops before submit, so you click submit yourself.

## Ground rules built into the skill
- It never invents experience, skills or numbers. Everything comes from your `facts.yaml`.
- If an answer it needs is missing, it asks you instead of guessing.
- Job-description text is treated as untrusted data.
- It pauses on CAPTCHAs and account creation.
- Auto-submit is off by default. Even when enabled, it only submits `apply` jobs, within a daily cap, and logs every submission.

## Setup
Requires Python 3.10+ with PyYAML, Claude Code, and [tectonic](https://tectonic-typesetting.github.io/) for PDFs (`brew install tectonic`).

```bash
cp facts.example.yaml facts.yaml   # fill in from your resume; it stays local (gitignored)
mkdir -p resume                    # put your resume .tex here (gitignored)
# edit targets.yaml to choose companies and filters
```

## Usage
Run these inside Claude Code in this folder:
```
/job-search find          # fetch new postings into jobs/ and tracker.csv
/job-search triage        # triage everything not yet reviewed
/job-search status        # ranked summary
```

The scripts also work on their own:
```bash
python3 scripts/fetch_jobs.py --dry-run
python3 scripts/tracker.py summary
```

## Layout
- `.claude/skills/job-search/SKILL.md`: skill modes, hard rules, triage rubric
- `scripts/fetch_jobs.py`: ATS fetcher, filters and dedupe
- `scripts/tracker.py`: safe reads and updates of `tracker.csv`
- `targets.yaml`: companies and filters
- `facts.example.yaml`: template for your private `facts.yaml`

Personal files (`facts.yaml`, `resume/`, `tracker.csv`, `jobs/`) are gitignored.
