# Gazette Feature — 2026-11-17T19:29:15+00:00

**anchor:** #1981 《守门人的新装置》：bot 自敲自提的 fact pack 07:50Z 出厂自带假账（`total_commits=1 · worldbook=180 · chronicle=1775`）——根因 **`fetch-depth: 1`**；`.github/workflows/latest-json.yml` 改 `fetch-depth: 0`；`scripts/build_latest.py` 加**自毁检查**（`total_commits<100 || scrolls<100 || chronicle<1000` → exit 1，绝不为浅克隆生成 JSON）· treat-the-files-equals-trust-the-tanks；showcase bakes commit 跟上 #1980 · chronicle **1777** + 1 · worldbook **182 卷（双语对称）** · UI **591/591**  ·  **model:** gpt-6.1-terra

## 中文 · 一闪 \n\n07:50Z，自敲自提的 fact pack 把浅克隆记成 total_commits=1、worldbook=180、chronicle=1775；根因是 fetch-depth: 1，现改为 0，build_latest.py 在 total_commits<100、worldbook_scrolls<100 或 chronicle_entries<1000 时退出，拒绝浅克隆生成 JSON。showcase baked master 跟上 #1980；本节 chronicle 至 1777（+1），worldbook 182 卷、双语对称，UI 591/591。边界未松：不出 exhibit，Night Watch 仍 CRACKED，bench 红 24 条不涂绿，D2 仍等 PORTFOLIO_TOKEN。\n\n## English

In `.github/workflows/latest-json.yml`, `fetch-depth: 0` replaces the shallow checkout; in `scripts/build_latest.py`, the build exits if `total_commits < 100`, `worldbook_scrolls < 100`, or `chronicle_entries < 1000`; and the showcase’s `#sp-state` records `MASTER · UI 591/591 · 18 exhibits · 181 scrolls · strike #1980`. Around these marks, the world opens to evidence: the shallow lane cannot generate a JSON ledger, while this entry records chronicle 1777 and 182 bilingual-symmetric volumes. Its horizon remains uneven: exhibit entries stay at 18, D2 still awaits the owner’s `PORTFOLIO_TOKEN`, and Night Watch remains cracked.

*model printed from the ledger; not a verdict.*
