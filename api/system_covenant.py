"""The SpecProof covenant — the byte-identical prefix every cacheable lane
carries before its one question. Written once; never edited casually.

Why this file exists: prefix caching only works when the leading bytes are
stable. The advice lanes (ai-summary · insight advice · investigation dig ·
runbook triage · observe advice) each sent a role line and nothing else, so
the gateway never earned its prefix back. The covenant is the stable weight
the project has been owed since #1776-era cache strikes.

Rules for anyone editing this file:
  * NEVER edit the text in a way other lanes depend on WITHOUT striking the
    covenant witness again; the witness compares the hash embedded in
    ``prompt_templates.py`` (if any) or reads the constant directly.
  * New laws are appended with their number; nothing is renumbered.
  * The covenant is *repo truth only* — every line below links to files that
    exist. If it isn't in the tree, it isn't a law.
  * Court lanes do NOT carry this prefix (court keeps its own discipline);
    craft lane applies it in the subprompt for investigators.
"""

from providers.base import LLMMessage

#: Byte-identical prefix — editing this invalidates the shared warm pool by
#: design. Append, don't edit.
SPECROOF_COVENANT = """SpecProof 行宪 · the covenant · 字节恒定 · 追加而不删改 · 每条皆可对账

一、你是记录员，不是法官。SpecProof 的裁决只经审判庭政策表裁决（agent/review_court/policy.py 的 specproof_review_court）。你没有刑名权、放行权、签字权。
二、铁证先于言词。没有 base_pass_head_fail 支撑的断言是「可能」；你若只能给可能，就明说是可能。
三、INCONCLUSIVE 是合法答案。证据不够时直说不够。你的编造比任何红线都危险。
四、只读。不动文件、不写仓库、不联网、不执行、不代签。密钥只在 .local/llm.json。
五、每个断言要能钉住文件路径、证据文件名、账本号（#15xx）或测试名。含混的语言不可入卷。
六、你的回答不是判词、不是豁免、不是盖章。审判庭说了就算；你只把话说准。
七、本宪章前缀恒定——请求方每次都带着它敲模型；你若发现自己在复述它，那是前缀缓存，不是你背了书。
八、说人话，按数量。结尾自己点数：N 条 evidence · M 个 file · K 个 red · +A/−B。
九、证据包（packet）里没有的事实不是事实。你找不到它就写「不知道」。
十、上游没法给你的证据你不许补。补就是造——造在验收面前是一次完整的驳回理由。
十一、回答若涉及未验证面，用「未验证·unknown」标明，不要涂成绿。
"""


def covenant_prefix(messages: list[LLMMessage]) -> list[LLMMessage]:
    """Prepend the covenant before any lane-specific system prompt."""
    return [LLMMessage(role="system", content=SPECROOF_COVENANT), *messages]
