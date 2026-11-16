import type { Locale } from "../i18n/strings";

/**
 * 更正卷轴 · The Corrections Scroll — the 15 errata on file, rendered as an
 * in-app reference page (the way a new engineer is told, at onboarding, this
 * project is not a triumphalist brochure).
 *
 * Just as with the museum's exhibits, nothing here is lore. Each entry is a
 * specific fact this project once got wrong, struck by its own `build_corrections`
 * pass over `docs/world/APPENDIX_CORRECTIONS.md`. Both locales are rendered;
 * neither is a translation of the other's truth — they report the same fact.
 */

export interface ErratumEntry {
  id: string;
  category: Record<Locale, string>;
  gloss: Record<Locale, string>;
  detail: Record<Locale, string>;
  anchor: string;
}

export const ERRATA: ErratumEntry[] = [
  {
    id: "R01", category: { zh: "账本数字", en: "ledger arithmetic" },
    gloss: { zh: "chronicle 计数偏差", en: "chronicle count drift" },
    detail: {
      zh: "统计的是 \"ledger sections\"（通过 `## #\\d+` 标题现场抓的），但自己的百看不如一敲——数字被漂到 1,644 才对。",
      en: "The chronicle count led to a flattering number; the real sections-count parse sees 1,644 entries. The count is now re-derivable by a script, never by eye.",
    },
    anchor: "#1845",
  },
  {
    id: "R02", category: { zh: "世界书双语", en: "world-book bilingual" },
    gloss: { zh: "zh / en 书目页差别不为零", en: "zh/en catalogue mismatch" },
    detail: {
      zh: "第六卷登记时只看 en 没看 zh，导致卷数看似 73 vs 72；本卷对照了两边的卷名清单，强制同步入平账。",
      en: "Two files drifted in the count (one page was originally added only to zh). Both now alert each other on every rebuild; the count never blanks out silently.",
    },
    anchor: "#1855",
  },
  {
    id: "R03", category: { zh: "计数硬编码", en: "hard-coded count" },
    gloss: { zh: "CrewCard 打印了定值", en: "printed CrewCard count" },
    detail: {
      zh: "\"commits 2,499\" 漂移到人；东西的真值被刷新为从 repoStats 读走，不再由人靠眼打印。",
      en: "The printed card carried a baked-in constant. The generator now reads repoStats at print time; the number is always struck now, never guessed.",
    },
    anchor: "#1858",
  },
  {
    id: "R04", category: { zh: "子图自说自话", en: "audit · subgraph" },
    gloss: { zh: "scratch residue 误判为垃圾", en: "test-scratch dismissed as garbage" },
    detail: {
      zh: "之前说 ~1000 个 hash 是 scratch；实际审计显示是 21 个 pycache 被误判；本轮 audit_scratch_residue.py 落地，scratch-index 归类清晰，不再把「evaluation evidence」当渗漏。",
      en: "An earlier suspicion labelled test scratch land as leaked residue; the live audit proved 21 cache files, the rest are evaluation evidence files. They were never deleted.",
    },
    anchor: "#1865",
  },
  {
    id: "R05", category: { zh: "court 锁", en: "court · the lock" },
    gloss: { zh: "audit_court_lock 首次判决 BROKEN", en: "first court-lock fix" },
    detail: {
      zh: "audit 脚本第一轮敲出 `verdict: BROKEN`，到处都说错了——但那是从 regex 抓不到 `kwargs[\"stream_options\"]=...` 引起的错判；先修 audit 脚本才锁住 `LOCKED`。",
      en: "The audit script parsed the wrong pattern for `stream_options`; going on retry-only, it produced a false BROKEN. The real fix was in the checker, not the code lock.",
    },
    anchor: "#1866",
  },
  {
    id: "R06", category: { zh: "时序排序", en: "ordering" },
    gloss: { zh: "evidence 按文件名排序", en: "exhibit ordering by file name" },
    detail: {
      zh: "Exhibit 按文件名倒序选 `latest`；名字含 -2/-3 却没比原始 -warm 排得后——直到 `started_utc` 字典序成为唯一键。",
      en: "Lexicographic file-name ties broke the correct \"latest\" exhibit; iso datetime lexicographic order now works deterministically for concurrent writes.",
    },
    anchor: "#1854",
  },
  {
    id: "R07", category: { zh: "硬编码", en: "hard-coded" },
    gloss: { zh: "Archive 写死的 50 卷世界书", en: "Archive hard-coded world book" },
    detail: {
      zh: "/archive 的 worldbook KPI 写死为 50 卷；当时 actual 已经 81+。后来所有 KPI 都改为直接 import `repoStats.json`。",
      en: "A static \"50 volumes\" survived eight rebuilds while the actual count climbed into the hundreds; KPIs are now struck live from locked JSON.",
    },
    anchor: "#1863",
  },
  {
    id: "R08", category: { zh: "审计脚本", en: "audit script" },
    gloss: { zh: "branch-cleanliness 默认 no-upstream", en: "branch detection reported no-upstream" },
    detail: {
      zh: "audit_unsigned.py 之前看不到 `origin`，全数报成 no-upstream；本轮补了 `import subprocess` 得到 rev-list 输出。",
      en: "The unsigned-lamp process silently failed to import subprocess, therefore produced a constant no-upstream reading; it now calls git directly and emits dirty-tree/clean correctly.",
    },
    anchor: "#1863",
  },
  {
    id: "R09", category: { zh: "构建脚本", en: "build script" },
    gloss: { zh: "ROADMAP 生成器本身未进库", en: "roadmap generator shipped without its own source" },
    detail: {
      zh: "`27d632b` 这个 commit 本身做了一件事：把生成的 `docs/ROADMAP-LIVE.md` 进库了，但它的生成器脚本没有——这不是什么 `git status` 就能发现的问题；本轮补 `scripts/build_roadmap_live.py` 进库。",
      en: "The generator script had not been merged when its output had been; today both are on master in the same commit family.",
    },
    anchor: "#1865",
  },
  {
    id: "R10", category: { zh: "RageCoach 规则", en: "tour keyboard map" },
    gloss: { zh: "tour-seal 而规则归 approve", en: "test expected wrong tour lane" },
    detail: {
      zh: "测试写死期望 `approve`，但 RageCoach 实际是要 `seal` —— 命名自始如此；不是代码错，是断言错，修测试。",
      en: "The test suite demanded the approve path; the rulebook actually owns `seal`. The fix was on the test side; the rulemap never changed.",
    },
    anchor: "#1846",
  },
  {
    id: "R11", category: { zh: "flaky 测试", en: "flaky spec" },
    gloss: { zh: "evidence_graph mtime tie flikering", en: "evidence graph mtime instability" },
    detail: {
      zh: "`collect_series.py` 用 mtime 排序，两个文件同秒写会 randomize 顺序；本轮换成 `started_utc` 的 ISO 字典序 → 稳定性 100% 锁门。",
      en: "Intake previously sorted by mtime causing tie instability; the current one sorts by ISO timestamps and pins flake-out to a thing of the past.",
    },
    anchor: "#1872",
  },
  {
    id: "R12", category: { zh: "换钥的通道", en: "gateway/key lane" },
    gloss: { zh: "换钥后不敲就以为通了", en: "replaced key ≠ lane proven" },
    detail: {
      zh: "把 `.local/llm.json` 切到 aizzz.xyz 之后，我一度把它当作「已 live」。事实是：同一句话敲出去 6 次，6 次都回答「本站不对您所在的国家及地区进行商业服务」——这不是工程通，是区域封锁。",
      en: "Swapped keys begged the question; 6/6 probes came back region-blocked. Recorded as R12; recovery lane: a Verge proxy or a different egress point, not wishing harder.",
    },
    anchor: "#1881",
  },
  {
    id: "R13", category: { zh: "样式表分类", en: "component CSS" },
    gloss: { zh: "chain banner 颜色不生效", en: "banner colour class mismatch" },
    detail: {
      zh: "组件向外发 `chain-banner--ok`（双破折号），CSS 写的却是 `.chain-banner-ok`（单破折号），所有人(`CRITICAL/bad`)(`\x60`)看绿绿全部一样灰。本轮改双向对称命名。",
      en: "Component emitted `chain-banner--ok` (double dash) while CSS defined `chain-banner-ok` (single dash) — a silent classification collapse. Both sides now read one token.",
    },
    anchor: "#1882",
  },
  {
    id: "R14", category: { zh: "出网归因", en: "egress diagnosis" },
    gloss: { zh: "出网没走本机梯子", en: "proxy not set on egress" },
    detail: {
      zh: "不走 Clash Verge(7897) 的直连 HTTP 永远被区域封锁；走了之后 `POST /v1/chat/completions` 真的 HTTP 200、cached=4224→6400。R12 的判断是「关死了」—— 事实是「出网没挂梯子，这一扇门对从本机直逼的访问全是死的」。",
      en: "Direct TLS hits return regional Chinese restriction; routing the same request over the host's Clash Verge (127.0.0.1:7897) returns 200 with cache climbing from 4224→6400 tokens. R14 was the ladder we missed on the first climb.",
    },
    anchor: "#1884",
  },
  {
    id: "R15", category: { zh: "测试环;境", en: "test isolation" },
    gloss: { zh: "suite 被宿主 8888 接管", en: "stale config-server shadow" },
    detail: {
      zh: "本机 localhost:8888 上有旧的 config-server 一直serving `health,info`（无 gateway/prometheus/refresh），gateway 测试 7 例一并扑红。没把 8888 做依赖，而是把 integration 测试全迁到 discard 口 `127.0.0.1:9/`。",
      en: "A stale config-server image served a two-key exposure on the host's 8888, seven gateway tests dropped out. Tests now pin the config import to a discard port `127.0.0.1:9/`.",
    },
    anchor: "#1886",
  },
  {
    id: "R16", category: { zh: "缓存归因", en: "cache attribution" },
    gloss: { zh: "我把一次 cached=4224 写得像改善了命中率", en: "one cached strike is not a higher hit rate" },
    detail: {
      zh: "Volume CXV 与多处文档把一次 live_lane_probe 敲出（HTTP 200 · cached 4224）写得像缓存命中率已改善。事实上：scripts/two_strike_probe.py（同一 prompt 连敲两次，本部署 aizzz/gpt-6.1-terra）两次都报 prompt_cache_hit_tokens=0（全 4676 未命中）；4224 很可能是网关的 tenant-shared 前缀，不是本应用的前缀。本仓车道已全流式 + include_usage；缓存是否命中不可控、不可宣称、不可写数。",
      en: "Volume CXV and several documents wrote one cached=4224 strike from live_lane_probe as if the cache hit rate had already improved. Struck live: scripts/two_strike_probe.py (same prompt twice, this deployment) reported prompt_cache_hit_tokens=0/0 (all 4676 tokens missed, both times); the 4224 was likely the gateway's tenant-shared default prefix, not this app's. Every lane now rides stream+include_usage with a resident prefix — all we can control; whether the gateway caches us at all is not our claim to make.",
    },
    anchor: "#1915",
  },
  {
    id: "R17", category: { zh: "账页真值", en: "stale engine account" },
    gloss: { zh: "/engine 上还挂着 wkapi 时代的旧账", en: "the wkapi-era account hung on /engine after the ledger moved on" },
    detail: {
      zh: "页脚写着「41 次真实敲 wkapi.pro …… total tokens 147,767 …… 51.2 % exact static-prefix hit rate」——那是 2026-11-13 的快照。当晚 .local/llm_usage.jsonl 已含 17 行 aizzz/gpt-6.1-terra（2026-11-16 经本机代理）。账于 2026-11-16 重建：63 行、cached 105,206、prompt 238,221 = 44.2%；四处文案与 lanes 备注（direct 29 · policy 12 → 实况 direct 46 · policy 17，本机统计）全数替换，并新增「前缀缓存 · 双敲见证」面板（cache_witness_graph：cached 4224×2 · hit_rate 95.3% · HIT）。守门测试 EngineWitness.test.tsx：页内不许再次出现 wkapi.pro / 147,767 / 51.2 / 75,638 / direct 29 · policy 12。",
      en: "The footer claimed '41 calls to wkapi.pro … total tokens 147,767 … 51.2% exact static-prefix hit rate' — a 2026-11-13 snapshot. The same night .local/llm_usage.jsonl had 17 rows of aizzz/gpt-6.1-terra appended (through the local proxy). The account was rebuilt on 2026-11-16: 63 rows, cached 105,206, prompt 238,221 = 44.2%; the four stale copy spots and the lanes note (direct 29 · policy 12 → measured direct 46 · policy 17, counted on this host) were replaced, and a prefix-cache double-strike witness panel was added (cache_witness_graph: cached 4224×2 · hit_rate 95.3% · HIT). Gate: EngineWitness.test.tsx — the page must never again render wkapi.pro / 147,767 / 51.2 / 75,638 / direct 29 · policy 12.",
    },
    anchor: "#1934",
  },
];
