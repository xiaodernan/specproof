# PORTFOLIO SYNC — automatically show the latest SpecProof to your portfolio page

> **中文版**: [PORTFOLIO_SYNC.md](./PORTFOLIO_SYNC.md) · This file is the English edition; the Chinese one is authoritative for Chinese readers.

> Goal: every time someone opens SpecProof at your personal portfolio, they see the freshest master-side results — not a stale thumbnail. This document is written in English from the original Chinese text, section by section.

---

## 1. What the sync ships (and what it does not)

### Ships

| Source | Destination (static page on GitHub Pages) |
|---|---|
| `CHANGELOG.md` highlights | portfolio's SpecProof card "What's new" one-liner |
| latest `## #` section in `docs/operations/DEEP_OPTIMIZATION_PLAN.md` | portfolio "latest delivery" panel |
| `docs/world/EN/SPECROOF_WORLD_EN.md` size + TOC | portfolio "SpecProof's world bible" card |
| `apps/web/dist` build size | portfolio's "current build size" stat |
| master HEAD commit hash + `--decorate` | portfolio's SpecProof "latest master commit" line |
| 35+ pages of `.tsx` fixtures | portfolio's "products" gallery |

### Does not ship

- **No credentials** — the portfolio page never touches `.env`, `.local/llm.json`, or any token;
- **No LLM calls** — the sync workflow spends zero tokens;
- **No runtime rendering** — the portfolio page is fully static;
- **No Docker required** — it's one `python scripts/sync_portfolio.py` run that writes one JSON and one markdown file into the portfolio repo's `data/` directory.

---

## 2. The sync script (ready to run)

`scripts/sync_portfolio.py` produces these three artifacts:

```json
# .github-sync.json — copied into the portfolio repo, or read by its pipeline
{
  "last_synced": "2026-11-14T15:20:00+08:00",
  "latest_commit": "5f0290b",
  "latest_ledger_entry": {
    "number": 1690,
    "title": "USER_GUIDE.md shipped",
    "date": "2026-11-14",
    "highlights": ["46 routes", "quickstart 5 minutes", "user manual 7 chapters"]
  },
  "world_bible_size_bytes": 25404,
  "page_count": 35,
  "e2e_passed_at": "2026-11-13"
}
```

```markdown
# latest.md — straight into the portfolio's sidebar "Recent ship" section
```markdown
## SpecProof · recent ship

**2026-11-14 · 5f0290b** — USER_GUIDE.md shipped

- 46 routes · 7-chapter user manual · bilingual UI
  
- Verify pipeline end-to-end PASS (AUTH-01)
  
- Cache hit rate 75-84% (real wkapi.pro measurements); hit rate is gateway accounting, not a contract

[Read the full book · 25.4 KB](https://github.com/xiaodernan/specproof)
```

```yaml
# in the portfolio repo, one GitHub Actions workflow does the pull:
name: sync-from-specproof
on:
  schedule: [{ cron: '0 */6 * * *' }]   # every 6 hours
  workflow_dispatch:
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4           # portfolio repo
      - run: |
          curl -sL https://raw.githubusercontent.com/xiaodernan/specproof/master/.github-sync.json > data/specproof-latest.json
      - run: git commit -am "chore: sync specproof latest" && git push
```

### Pull model, push to portfolio in a separate command

```bash
# after each master push, or once a day when it feels right
python scripts/sync_portfolio.py
# copy .github-sync.json and latest.md into the portfolio repo, commit that
# portfolio updates on the next CI run of the page
```

---

## Automatic sync (one secret, then hands-off)

This repo ships a ready GitHub Actions workflow at `.github/workflows/portfolio-sync.yml`.
It runs every Sunday 06:00 UTC, on master merge, or on manual trigger, and pushes three files into `xiaodernan/xiaodernan.github.io`.

**One secret is all you wire up**:

| Secret | Purpose | How to get it |
|---|---|---|
| `PORTFOLIO_TOKEN` | push `data/specproof-*` into the portfolio repo | GitHub → Settings → Developer settings → Fine-grained tokens → select the portfolio repo → Contents: read and write → paste the token into specproof's Secrets |

**No secret? Still fine** — the workflow regenerates the data, then prints a notice instead of failing.

**Why weekly, never-by-every-commit** — the portfolio is a showcase, not a scoreboard; one weekly ship is more than enough.

---

## 3. Why pull-model, not push-model

- **Security**: SpecProof never needs write access to the portfolio repo; the portfolio reads a JSON file instead;
- **Resilience**: portfolio CI doesn't depend on external API availability; it can read the raw file from GitHub at any time;
- **Opt-in**: the portfolio team can choose which cards render or edit them without touching our public page;
- **Auditability**: the portfolio's own commit log carries each ship — no invisible updates.

---

## 4. What we do NOT promise

- Sync script cannot auto-push to the portfolio repo;
  - that requires credentials (a write-enabled fine-grained token) on the portfolio side;
  - the "auto" part is the scheduled nightly/weekly job in the portfolio repo — on this side we only generate the payloads;
- the latest numbers are human-readable "last shipped" — the portfolio repo fetches data, renders its own placeholders, or shows stale until CI fires;
- the sync does not replace or re-verify the SpecCraft agent behavior; it's a static page, not a runtime harness;
- no end-to-end numbers are force-published; the portfolio may choose to omit statistics it cannot render honestly.

---

## 5. File map

| File | Purpose |
|---|---|
| `scripts/sync_portfolio.py` | regenerates `.github-sync.json` + `latest.md` + `products.json` |
| `docs/operations/PORTFOLIO_SYNC.md` | design: sync boundaries, one-secret workflow, cadence, limits (Chinese) |
| `docs/operations/EN/PORTFOLIO_SYNC.en.md` | English edition of PORTFOLIO_SYNC.md, section for section (English) |
| `.github-sync.json` | machine-readable entry, committed into the portfolio repo by default |
| `apps/web/dist/*` | build artifact for static hosting if the portfolio chooses to embed it |
