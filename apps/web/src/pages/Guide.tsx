import { useState } from "react";
import { useNavigate } from "../hooks/navigate";
import { DEMO_AGENT, DEMO_VERIFY, DEMO_VERIFY_ABS_PATH_NOTE } from "../demo";
import { EMPTY_WIZARD_DRAFT, saveWizardDraft } from "../agent/util";
import { Button, GLOSSARY } from "../ui";
import "./onboarding.css";

const START_COMMAND = "pwsh scripts/start_local.ps1";

export default function Guide() {
  const [copyState, setCopyState] = useState("");
  const navigate = useNavigate();

  function startDemoVerify() {
    const query = new URLSearchParams({
      repo: DEMO_VERIFY.repo_path,
      spec: DEMO_VERIFY.spec_path,
      base: DEMO_VERIFY.base_ref,
      head: DEMO_VERIFY.head_ref,
    });
    navigate("/jobs/new?" + query.toString());
  }

  function startDemoAgent() {
    saveWizardDraft({
      ...EMPTY_WIZARD_DRAFT,
      task_name: DEMO_AGENT.task_name,
      spec_text: DEMO_AGENT.spec_text,
    });
    navigate("/agent/new/spec");
  }

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(START_COMMAND);
      setCopyState("启动命令已复制");
    } catch {
      setCopyState("请选中下方命令手动复制");
    }
  }

  return (
    <div className="guide-page">
      <div className="page-head">
        <div className="welcome-eyebrow">认识 SpecProof</div>
        <h1>从“代码能跑”到“需求有证据”</h1>
        <p className="guide-intro">Spec 是你期望软件做到的事，Proof 是验证这些要求的证据。SpecProof 把两者连起来，让开发者、评审人和交付负责人用同一份结果做决定。</p>
        <div className="guide-actions"><a href="#/jobs/new" className="ui-btn ui-btn-primary ui-btn-md">新建验证</a><a href="#/dashboard" className="ui-btn ui-btn-secondary ui-btn-md">前往工作区</a></div>
      </div>

      <div className="degraded"><strong>开发完成和验收通过是两种结果。</strong><p>AI 开发在你批准后修改当前仓库。独立验收主要依赖已有 Java / Spring 检查器；其他项目或无法形成检查的需求会显示覆盖不足，不能据此认定全部正确。</p></div>
      <section className="guide-choices" aria-label="选择使用方式">
        <article className="guide-choice"><span className="guide-kicker">我已经有代码变更</span><h2>验证这次改动</h2><p>提供代码仓库、改动前后的版本和需求文件，检查这次改动是否破坏约定。</p><a href="#/jobs/new">进入变更验证 <span aria-hidden="true">→</span></a></article>
        <article className="guide-choice"><span className="guide-kicker">我希望 AI 帮我开发</span><h2>从需求生成实现</h2><p>在开发助手中描述任务，审阅执行计划并批准，再查看代码差异和执行结果。</p><a href="#/agent/new">进入开发助手 <span aria-hidden="true">→</span></a></article>
        <article className="guide-choice"><span className="guide-kicker">我要评审或交付</span><h2>用证据做决定</h2><p>打开验证任务，按需求查看通过项、风险发现和证据；证据不足的项目继续确认。</p><a href="#/jobs">查看验证任务 <span aria-hidden="true">→</span></a></article>
      </section>

      <section className="guide-section" aria-labelledby="guide-start">
        <div className="guide-section-head"><span className="guide-section-number">01</span><div><h2 id="guide-start">第一次使用，按这四步走</h2><p>先用项目提供的演示案例理解结果，再接入自己的仓库。</p></div></div>
        <ol className="guide-steps">
          <li><strong>启动并连接工作区</strong><p>本机运行启动命令，用终端提供的凭据登录。团队部署则向管理员获取凭据。工作区登录密钥用于进入 SpecProof；模型服务商的 API Key 用于调用 AI，可由部署管理员在<a href="#/agent/settings">模型连接</a>中配置并测试。</p></li>
          <li><strong>准备一份可验收的需求</strong><p>把“改进用户管理”写成“非管理员修改邮箱应被拒绝，管理员可以修改，邮箱必须符合格式”。需求越明确，越容易验证。</p></li>
          <li><strong>新建验证，选定比较范围</strong><p>填入后端能够访问的仓库路径、基准版本 Base、待验证版本 Head，以及需求文件路径。提交后可查看排队、执行和结果。</p></li>
          <li><strong>看结论，也看依据</strong><p>先看任务结论，再进入需求矩阵与风险发现。失败时查看证据和受影响位置，修复后提交新的验证任务。</p></li>
        </ol>
      </section>

      <section className="guide-section guide-example" aria-labelledby="guide-example">
        <div className="guide-section-head"><span className="guide-section-number">02</span><div><h2 id="guide-example">用一次权限改动理解它</h2><p>仓库自带 Spring 后端示例，可在完成本地启动后填写到新建验证表单。</p></div></div>
        <div className="guide-example-grid"><dl><div><dt>代码仓库</dt><dd><code>demo/spring-backend</code></dd></div><div><dt>改动前 → 改动后</dt><dd><code>{DEMO_VERIFY.base_ref} → {DEMO_VERIFY.head_ref}</code></dd></div><div><dt>需求文件</dt><dd><code>demo/requirement.txt</code></dd></div></dl><div className="guide-example-outcome"><span className="guide-kicker">这个案例要回答的问题</span><h3>权限检查被移除后，谁还能修改邮箱？</h3><p>需求要求所有接口都必须认证。演示仓库的 <code>{DEMO_VERIFY.head_ref}</code> 版本移除了邮箱修改接口的权限检查 — 验证预期得到 <code>BLOCKED</code> 结论，并给出风险描述与证据。</p><div className="guide-example-actions"><Button variant="primary" onClick={startDemoVerify}>用它开始一次真实验证 →</Button><span>首次使用先运行 <code>pwsh scripts/prepare_demo_repo.ps1</code> 创建演示仓库的 git 版本；{DEMO_VERIFY_ABS_PATH_NOTE}</span></div></div></div>
        <div className="demo-prefill"><strong>想体验 AI 开发？</strong><p>也可以把预置的「修复 double 函数」示例需求带进开发助手，审阅计划并批准后，让 AI 在你的仓库里完成修复。</p><div className="demo-prefill-row"><Button size="sm" onClick={startDemoAgent}>用示例需求开始 AI 开发 →</Button><span className="demo-prefill-status">会打开向导第 2 步，你仍需填写仓库路径并审阅计划</span></div></div>
      </section>

      <section className="guide-section" aria-labelledby="guide-results">
        <div className="guide-section-head"><span className="guide-section-number">03</span><div><h2 id="guide-results">这些结果分别意味着什么？</h2><p>执行完成与验证通过是不同的状态，不能只看一个绿色标记。</p></div></div>
        <div className="guide-result-grid">
          <article><span className="guide-result-dot guide-result-ok" /><h3>验证通过 <code>VERIFIED</code></h3><p>当前范围内的检查满足要求。打开矩阵确认覆盖范围，查看可用的签名证书。</p></article>
          <article><span className="guide-result-dot guide-result-bad" /><h3>发现风险 <code>BLOCKED</code></h3><p>有检查阻断了本次变更。先查看问题与证据，修复后再验证。</p></article>
          <article><span className="guide-result-dot guide-result-warn" /><h3>执行失败 <code>FAILED</code></h3><p>环境或执行发生错误，尚不能对代码是否正确下结论。检查错误详情和服务状态。</p></article>
          <article><span className="guide-result-dot" /><h3>尚未验证 <code>UNVERIFIED</code></h3><p>某条需求缺少足够证据。补充需求、检查器或运行环境后再确认。</p></article>
        </div>
      </section>

      <section className="guide-section" aria-labelledby="guide-glossary">
        <div className="guide-section-head"><span className="guide-section-number">04</span><div><h2 id="guide-glossary">不用记住术语，也能读懂结果</h2></div></div>
        <dl className="guide-glossary">{GLOSSARY.map((entry) => <div key={entry.id}><dt>{entry.label}</dt><dd>{entry.definition}</dd></div>)}</dl>
      </section>

      <section className="guide-startup" aria-labelledby="guide-local"><div><h2 id="guide-local">在自己的电脑上体验</h2><p>先安装 Python 3.12、Node.js 18+、Docker Desktop，并在项目根目录安装 Python 依赖。完整步骤见项目文档 <code>docs/operations/LOCAL_EXPERIENCE.md</code>。</p><code className="guide-command">python -m pip install -e ".[dev]"<br />{START_COMMAND}</code><span role="status" className="guide-copy-status">{copyState}</span></div><Button onClick={() => { void copyCommand(); }}>复制启动命令</Button></section>
    </div>
  );
}
