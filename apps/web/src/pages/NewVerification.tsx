import { useState, type FormEvent } from "react";
import { createVerification, type VerificationRequest } from "../api";
import { Breadcrumbs, Button, ErrorBox, Input } from "../ui";
import "../styles/verification.css";

const initial: VerificationRequest = {
  repo_path: "", spec_path: "", base_ref: "main", head_ref: "HEAD", depth: "FAST",
};

export default function NewVerification() {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<Partial<Record<keyof VerificationRequest, string>>>({});
  const [error, setError] = useState<Error | string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const update = (field: keyof VerificationRequest, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    setError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    const payload: VerificationRequest = {
      repo_path: form.repo_path.trim(), spec_path: form.spec_path.trim(),
      base_ref: form.base_ref.trim(), head_ref: form.head_ref.trim(), depth: "FAST",
    };
    const nextErrors: typeof errors = {};
    if (!payload.repo_path) nextErrors.repo_path = "请填写执行服务可访问的 Git 仓库路径。";
    if (!payload.spec_path) nextErrors.spec_path = "请填写描述预期行为的需求文件路径。";
    if (!payload.base_ref) nextErrors.base_ref = "请填写用于比较的基准分支或提交。";
    if (!payload.head_ref) nextErrors.head_ref = "请填写待检查的分支或提交。";
    if (payload.base_ref && payload.base_ref === payload.head_ref) nextErrors.head_ref = "请选择与基准不同的版本，才能检查代码变化。";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createVerification(payload);
      if (!result.job_id) throw new Error("服务未返回任务编号，请刷新验证记录，确认是否已创建后再重试。");
      window.location.hash = "#/jobs/" + encodeURIComponent(result.job_id);
    } catch (e) {
      setError(e instanceof Error ? e : "任务创建失败，请检查服务连接后重试。");
      setSubmitting(false);
    }
  };

  return (
    <div className="verification-page">
      <Breadcrumbs items={[{ label: "验证记录", href: "#/jobs" }, { label: "新建验证" }]} />
      <div className="page-head verification-heading">
        <div><span className="verification-eyebrow">START A VERIFICATION</span><h1>这次改动，符合需求吗？</h1>
        <p className="verification-description">选择代码的两个版本，再提供需求文件。SpecProof 会检查改动，并把结论与可追溯的证据放在一起。</p></div>
      </div>
      <div className="verification-layout">
        <form className="verification-form" onSubmit={submit} noValidate aria-label="新建验证">
          <fieldset disabled={submitting}>
            <section className="verification-form-section">
              <div className="verification-section-title"><span>01</span><div><h2>选择项目</h2><p>路径由执行服务读取，请使用服务端可访问的路径。</p></div></div>
              <Input label="Git 仓库路径" required value={form.repo_path} onChange={(e) => update("repo_path", e.target.value)} placeholder="例如 /workspace/my-service" maxLength={512} error={errors.repo_path} hint="仓库需已存在于执行服务所在环境，且包含要比较的提交。" autoComplete="off" />
              <Input label="需求文件路径" required value={form.spec_path} onChange={(e) => update("spec_path", e.target.value)} placeholder="例如 /workspace/my-service/spec.md" maxLength={1024} error={errors.spec_path} hint="建议填写绝对路径。文件中写明改动必须满足的行为和验收条件。" autoComplete="off" />
            </section>
            <section className="verification-form-section">
              <div className="verification-section-title"><span>02</span><div><h2>确定比较范围</h2><p>从基准版本到待检查版本，定位本次代码变化。</p></div></div>
              <div className="verification-ref-grid">
                <Input label="基准版本" required value={form.base_ref} onChange={(e) => update("base_ref", e.target.value)} placeholder="main" maxLength={255} error={errors.base_ref} hint="通常为 main，也可使用提交 SHA。" />
                <Input label="待检查版本" required value={form.head_ref} onChange={(e) => update("head_ref", e.target.value)} placeholder="HEAD" maxLength={255} error={errors.head_ref} hint="通常为 HEAD 或功能分支名。" />
              </div>
            </section>
          </fieldset>
          <ErrorBox error={error} />
          <div className="verification-submit"><span>使用当前可用的快速验证模式</span><Button type="submit" variant="primary" size="lg" loading={submitting}>{submitting ? "正在创建验证…" : "开始验证 →"}</Button></div>
        </form>
        <aside className="verification-guide">
          <span className="verification-eyebrow">WHAT YOU GET</span><h2>从“看起来没问题”<br />到有证据的判断。</h2>
          <ol className="verification-benefits">
            <li><strong>需求逐条对应</strong><p>看到每条验收条件的检查结果，以及尚未覆盖的部分。</p></li>
            <li><strong>问题有据可查</strong><p>查看风险描述、影响位置与可用的复现证据。</p></li>
            <li><strong>评审更有依据</strong><p>用验证报告支持代码评审；证据不足会明确标注。</p></li>
          </ol>
          <div className="verification-example"><strong>需求可以这样写</strong><p>未登录用户调用 <code>POST /orders</code> 时应返回 401，且不得创建订单。</p><span>明确条件、预期结果和禁止行为，比“优化订单功能”更容易验证。</span></div>
          <p className="verification-note">当前验收主要依赖已有 Java / Spring 检查器；不支持的需求会标记覆盖不足。提交后需由执行服务处理。验证耗时取决于改动范围、模型服务和项目环境。</p>
          <a href="#/guide">查看完整使用指南 ↗</a>
        </aside>
      </div>
    </div>
  );
}
