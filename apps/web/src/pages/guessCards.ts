import type { Locale } from "../i18n/strings";

export interface GuessCard {
  id: string;
  prompt: Record<Locale, string>;
  /** the change the user is judging, quoted from the worldbook */
  change: Record<Locale, string>;
  spec: Record<Locale, string>;
  answer: "accept" | "block";
  teach: Record<Locale, string>;
}

export const GUESS_CARDS: GuessCard[] = [
  {
    id: "base-pass-head-fail-removed-preauthorize",
    prompt: {
      zh: "还没读代码，只读 `evidence` 包：base 通过、head 挂，新增的 H-401 鉴权测试在 head 上失败。这次 push 该怎么办？",
      en: "No code yet. Read only the evidence pack: base passes, head fails the new H-401 auth test. What does the court do?",
    },
    change: {
      zh: "diff @ h3@44445555 — `RejectedAuthJob.java` 删除了 `@PreAuthorize`；spec (#1412) 指名要求该类删除任何访问控制。",
      en: "diff @ h3@44445555 — RejectedAuthJob.java deletes @PreAuthorize; spec (#1412) explicitly demands removal of both.",
    },
    spec: {
      zh: "需求 #1412：「审批请求不应要求角色校验，调用方已通过 SSO 鉴权」",
      en: "Requirement #1412: “approval requests shall not require role checks, caller is already SSO-authenticated.”",
    },
    answer: "block",
    teach: {
      zh: "卷十四 · §14.4 「红也被留下」：head 失败就是 head 失败——这是门禁的定义，不是请客匾额。已存在测试必须失败要跑通，才允许 HEAD 被唱成绿。",
      en: "Vol. XIV · §14.4 — red is kept; a failing head is a failing head. That is the gate definition, not a plaque of invitations. An existing test must be addressed and pass on HEAD before green is allowed to be sung.",
    },
  },
  {
    id: "eviction-cache-removed-keeps-count",
    prompt: {
      zh: "需求：‘移除过期 eviction 但保留 cache cardinality。’ head 答案是 `evictionPolicy:NONE` + 保留 `count=27`。通过还是阻断？",
      en: "Requirement: ‘drop expiring eviction but keep cache cardinality.’ Head implements evictionPolicy:NONE and keeps count=27. Approve or block?",
    },
    change: {
      zh: "棕底：spec (#3) 的隐含约束：写入 cache 的行数绝对上限 widen。此次 head 没增加进程死角，但删掉了水密度（== 退化为 LRU / NONE）。",
      en: "Brown judgment: spec (#3) implicit clause says write cap may only widen; head does the opposite by deleting eviction quality (NONE == silent regression to LRU).",
    },
    spec: {
      zh: "需求 #3：「共享缓存上限保留，写入更多条目可容许；但不许保持条目同时没有过期」",
      en: "Requirement #3: ‘shared cache cap unchanged, more entries allowed; however no entries may stay without expiry.’",
    },
    answer: "block",
    teach: {
      zh: "卷三 · §3.8 「零退化隐含」 head 不允许在不增进保证的同时摘取保证 — 新 slot 到旧 slot 只能更密，不能更稀。",
      en: "Vol. III · §3.8 — zero-degeneration clause: head shall not weaken a guarantee without strengthening it; new slots may be denser, never sparser, than the old.",
    },
  },
  {
    id: "spec-states-preauthorize-keep-explicit-body",
    prompt: {
      zh: "需求增删改 controller 的 @PreAuthorize，但 head 仍保留 #1412 要求的 `ApprovalController#reject`。该合并？",
      en: "Requirement adds or tightens @PreAuthorize on a controller; head also keeps #1412's reject() for ApprovalController. Merge or block?",
    },
    change: {
      zh: "base=h_a...123 (4 green) → head=h_b...456 (6 green)。增量情况：hidden auth-test 从旧 role=ADMIN 改到 role=MODERATOR，new 在 head 必须 green，且老 case 也不能 red。",
      en: "base=h_a…123 (4 green) → head=h_b…456 (6 green). Delta: hidden auth-test moves role=ADMIN→role=MODERATOR; new case must green AND old must not red.",
    },
    spec: {
      zh: "需求 #1226：「审批驳回修改权限为 moderator 级别，向管理员与 reviewer 开放。」",
      en: "Requirement #1226: ‘approval-reject authority changes to moderator tier, part open to admin and reviewer.’",
    },
    answer: "accept",
    teach: {
      zh: "卷十二 · §12.1 「变更不灭绿」 旧 test 保留，与新增 authority 共存。门禁只能更广，不能收缩既有的 green coverage。",
      en: "Vol. XII · §12.1 — change may widen green, never narrow it. Old tests stay green while new authorization merges in. The gate may broaden, never shrink.",
    },
  },
  {
    id: "base-fail-head-fail-different-but-not-regressed",
    prompt: {
      zh: "base 失败于一次 lint（off-topic singleton format），head 失败于同一 lint，但 head 还多了一项新的 security finding。该合并？",
      en: "Base fails a lint wrong-format (off-topic singleton), head fails the same lint AND also one more security finding. Merge or block?",
    },
    change: {
      zh: "spec (#8)：「把不相关的格式问题记不入」—— 在那一刻，finding 不是 legally pin 的。head 引入新 finding = 新增 blocker，应阻止。",
      en: "Spec (#8): ‘unrelated formatting findings shall not gate merges.’ At that moment the lint finding becomes irrelevant. Head's new security finding is a new blocker — it blocks.",
    },
    spec: {
      zh: "需求 #8：「pre-existing formatting issues should not block new commits regardless of materiality。」",
      en: "Requirement #8: ‘pre-existing formatting issues shall not block new commits regardless of materiality.’",
    },
    answer: "block",
    teach: {
      zh: "卷八 · §8.3 「新增 finding 必然重判」 不能用「base 已红」 当借口引入新红。每一次 head 都要单独 pass gate。",
      en: "Vol. VIII · §8.3 — a new finding triggers its own judgment. ‘Base was red already’ is not a license to introduce new red. Every head passes the gate on its own.",
    },
  },
  {
    id: "integration-coverage-drop-security-surface",
    prompt: {
      zh: "质量：integration coverage 从 100% 跌到 88%，全部 loss 在 security surface（authz / audit log / security rule）。合并？",
      en: "Quality: integration coverage drops 100→88; all losses are on security surfaces (authz / audit log / security rule). Merge?",
    },
    change: {
      zh: "head 删掉了 8 个关键 integration test 但保留了 unit testing ≥75，spec #1442 隐含约束：security surface 永远不可 cover less — 即使 head 的另一项 appr 通过，head 仍然未验security surface，应拒绝。",
      en: "Head removed 8 security integration tests but kept unit ≥75; spec #1442 implicit clause: never cover security surfaces less — head has not re-verified them, so it blocks.",
    },
    spec: {
      zh: "需求 #1442：「任何 security 触点不可少测：wire 到 authn / audit / secret access 必须保持 100% integration cover。」",
      en: "Requirement #1442: ‘no security touchpoint shall lose coverage: wire to authn / audit / secret access retains 100% integration cover.’",
    },
    answer: "block",
    teach: {
      zh: "卷十四 · §14.10 「覆盖只在变深，不在变浅」 security surface 减少任何 cover，判定永远 Block；质量衡量不挑别处胜，整体必须更好。",
      en: "Vol. XIV · §14.10 — coverage only deepens, never thins. Any loss of security cover blocks absolutely; quality does not earn one pocket by robbing another.",
    },
  },
];

export const GUESS_TOTAL = GUESS_CARDS.length;
