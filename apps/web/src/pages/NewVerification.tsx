import { useState, type FormEvent } from "react";
import { createVerification, prepareDemoRepo, type ApiError, type VerificationRequest } from "../api";
import { DEMO_VERIFY, DEMO_VERIFY_REPO_NOTE } from "../demo";
import { Breadcrumbs, Button, ErrorBox, Input, Term } from "../ui";
import { useI18n } from "../i18n";
import { NEW_VERIFICATION_BY_LOCALE, type NewVerificationCopy } from "./newVerification.copy";
import "../styles/verification.css";
import "./onboarding.css";

const initial: VerificationRequest = {
  repo_path: "", spec_path: "", base_ref: "main", head_ref: "HEAD", depth: "FAST",
};

// Demo coordinates default to whatever the host wire know as demo; when unset
// the demo paragraph and fill button degrade honestly instead of offering a
// button that cannot work.
const demoEnv = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>;
}).env ?? {};
const DEMO = {
  repo: demoEnv.VITE_DEMO_REPO_PATH,
  spec: demoEnv.VITE_DEMO_SPEC_PATH,
  base: demoEnv.VITE_DEMO_BASE_REF,
  head: demoEnv.VITE_DEMO_HEAD_REF,
};
const demoAvailable = Boolean(DEMO.repo && DEMO.spec);

function describeSubmitError(e: unknown, c: NewVerificationCopy): string {
  const err = e as { status?: number; code?: string; message?: string };
  if (err?.status === 503 || err?.code === "PROVIDER_UNAVAILABLE") {
    return c.error503;
  }
  // A transport failure (backend down, wrong API base, offline, CORS) surfaces
  // as a TypeError with no status/code — the browser's raw "Failed to fetch"
  // would otherwise leak English to the user.
  if (
    err?.status === undefined &&
    /failed to fetch|networkerror|load failed|err_network|econn|timed out|timeout/i.test(err?.message || "")
  ) {
    return c.errorNetwork;
  }
  return err?.message || c.errorFallback;
}

function readPrefill(search: string): VerificationRequest | null {
  const params = new URLSearchParams(search);
  const repo = params.get("repo");
  if (!repo) return null;
  return {
    repo_path: repo,
    spec_path: params.get("spec") ?? "",
    base_ref: params.get("base") ?? "main",
    head_ref: params.get("head") ?? "HEAD",
    depth: "FAST",
  };
}

export default function NewVerification() {
  const { locale } = useI18n();
  const c = NEW_VERIFICATION_BY_LOCALE[locale];
  // The route hash may carry ?repo=&spec=&base=&head= prefill params
  // (e.g. from the Guide page's demo button). Parsed once on mount.
  const [prefill] = useState<VerificationRequest | null>(() => {
    const queryIndex = window.location.hash.indexOf("?");
    return queryIndex >= 0 ? readPrefill(window.location.hash.slice(queryIndex + 1)) : null;
  });
  const [form, setForm] = useState<VerificationRequest>(prefill ?? initial);
  const [errors, setErrors] = useState<Partial<Record<keyof VerificationRequest, string>>>({});
  const [error, setError] = useState<Error | string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [demoFilled, setDemoFilled] = useState(prefill !== null);
  // #241b: one-click create of the demo repo (base / head-v1 refs) so a first
  // run no longer requires the CLI. The backend call is idempotent; the handler
  // fills the demo form on success regardless of whether the refs were just
  // created or already present.
  const [preparing, setPreparing] = useState(false);
  const [prepareStatus, setPrepareStatus] = useState<string | null>(null);
  const [prepareError, setPrepareError] = useState<string | null>(null);

  const fillDemo = () => {
    setForm({
      repo_path: DEMO_VERIFY.repo_path,
      spec_path: DEMO_VERIFY.spec_path,
      base_ref: DEMO_VERIFY.base_ref,
      head_ref: DEMO_VERIFY.head_ref,
      depth: "FAST",
    });
    setErrors({});
    setError(null);
    setDemoFilled(true);
  };

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
    if (!payload.repo_path) nextErrors.repo_path = c.repoRequired;
    if (!payload.spec_path) nextErrors.spec_path = c.specRequired;
    if (!payload.base_ref) nextErrors.base_ref = c.baseRequired;
    if (!payload.head_ref) nextErrors.head_ref = c.headRequired;
    if (payload.base_ref && payload.base_ref === payload.head_ref) nextErrors.head_ref = c.headSameAsBase;
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createVerification(payload);
      if (!result.job_id) throw new Error(c.noJobId);
      window.location.hash = "#/jobs/" + encodeURIComponent(result.job_id);
    } catch (e) {
      setError(describeSubmitError(e, c));
      setSubmitting(false);
    }
  };

  const prepareDemo = async () => {
    if (preparing) return;
    setPreparing(true);
    setPrepareError(null);
    setPrepareStatus(null);
    try {
      const result = await prepareDemoRepo();
      // Success: refs are now present (newly created or already there). The
      // demo can be filled no matter which — the endpoint is idempotent and the
      // user's goal is to reach a fillable form, not to learn which branch ran.
      fillDemo();
      setPrepareStatus(
        result.created
          ? c.createdOk(result.refs.join(" / "))
          : c.alreadyPresent,
      );
    } catch (e) {
      const err = e as ApiError;
      if (err?.status === 401) {
        setPrepareError(c.needApiKey);
      } else {
        setPrepareError(err?.detail || err?.message || c.prepareFailed);
      }
    } finally {
      setPreparing(false);
    }
  };

  return (
    <div className="verification-page">
      <Breadcrumbs items={[{ label: c.breadcrumbJobs, href: "#/jobs" }, { label: c.breadcrumbNew }]} />
      <div className="page-head verification-heading">
        <div><span className="verification-eyebrow">{c.eyebrow}</span><h1>{c.title}</h1>
        <p className="verification-description">{c.description}</p></div>
      </div>
      <div className="verification-layout">
        <form className="verification-form" onSubmit={submit} noValidate aria-label={c.demoFormAria}>
          {demoAvailable && (
            <div className="demo-fill-banner" role="note">
              <span>{c.demoBannerBody}</span>
              <Button
                type="button"
                size="sm"
                onClick={() => {
                  setForm({
                    repo_path: DEMO.repo || "", spec_path: DEMO.spec || "",
                    base_ref: DEMO.base || DEMO_VERIFY.base_ref,
                    head_ref: DEMO.head || DEMO_VERIFY.head_ref,
                    depth: "FAST",
                  });
                  setErrors({});
                  setError(null);
                  setDemoFilled(true);
                }}
              >
                {c.demoBannerButton}
              </Button>
            </div>
          )}
          <fieldset disabled={submitting}>
            <section className="verification-form-section">
              <div className="verification-section-title"><span>01</span><div><h2>{c.section01Title}</h2><p>{c.section01Body}</p></div></div>
              <Input label={c.repoLabel} required value={form.repo_path} onChange={(e) => update("repo_path", e.target.value)} placeholder={c.repoPlaceholder} maxLength={512} error={errors.repo_path} hint={c.repoHint} autoComplete="off" />
              <Input label={c.specLabel} required value={form.spec_path} onChange={(e) => update("spec_path", e.target.value)} placeholder={c.specPlaceholder} maxLength={1024} error={errors.spec_path} hint={c.specHint} autoComplete="off" />
            </section>
            <section className="verification-form-section">
              <div className="verification-section-title"><span>02</span><div><h2>{c.section02Title}</h2><p>{c.section02Body}</p></div></div>
              <div className="verification-ref-grid">
                <Input label={c.baseLabel} required value={form.base_ref} onChange={(e) => update("base_ref", e.target.value)} placeholder={c.basePlaceholder} maxLength={255} error={errors.base_ref} hint={c.baseHint} />
                <Input label={c.headLabel} required value={form.head_ref} onChange={(e) => update("head_ref", e.target.value)} placeholder={c.headPlaceholder} maxLength={255} error={errors.head_ref} hint={c.headHint} />
              </div>
            </section>
          </fieldset>
          <ErrorBox error={error} />
          <div className="verification-submit"><Button type="button" variant="ghost" onClick={fillDemo} disabled={submitting}>{c.demoFill}</Button><span>{c.submitNote}</span><Button type="submit" variant="primary" size="lg" loading={submitting}>{submitting ? c.submitting : c.submit}</Button></div>
        </form>
        <aside className="verification-guide">
          <span className="verification-eyebrow">WHAT YOU GET</span><h2>{c.benefitsTitle}</h2>
          <ol className="verification-benefits">
            <li><strong>{c.benefitContractsStrong}</strong><p>{c.benefitContractsBefore}<Term id="contract">{c.benefitContractsTerm}</Term>{c.benefitContractsAfter}</p></li>
            <li><strong>{c.benefitFindingsStrong}</strong><p>{c.benefitFindingsBefore}<Term id="finding">{c.benefitFindingsTerm}</Term>{c.benefitFindingsAfter}</p></li>
            <li><strong>{c.benefitJudgesStrong}</strong><p>{c.benefitJudgesBody}</p></li>
          </ol>
          <div className="verification-example"><strong>{c.exampleTitle}</strong><p>{c.exampleBodyBefore}<code>{c.exampleBodyCode}</code>{c.exampleBodyAfter}</p><span>{c.exampleTail}</span></div>
          <div className="demo-prefill">
            <strong>{c.prefillTitle}</strong>
            <p>{c.prefillBodyBefore}<strong>{c.prefillStrong}</strong>{c.prefillBodyAfter}<code>{c.prefillBodyCode}</code>{c.prefillBodyTail}</p>
            <div className="demo-prefill-row">
              <Button type="button" size="sm" onClick={fillDemo}>{c.prefillFill}</Button>
              <Button type="button" size="sm" variant="secondary" onClick={prepareDemo} disabled={preparing}>
                {preparing ? c.preparing : c.prepareDemo}
              </Button>
              {demoFilled ? <span className="demo-prefill-status" role="status">{c.prefillPrepared}</span> : null}
            </div>
            {prepareStatus ? <span className="demo-prefill-status" role="status">{prepareStatus}</span> : null}
            {prepareError ? <span className="demo-prefill-error" role="alert">{prepareError}</span> : null}
            <code className="demo-prefill-code">{DEMO_VERIFY_REPO_NOTE}</code>
          </div>
          <p className="verification-note">{c.note}</p>
          <a href="#/guide">{c.openGuide}</a>
        </aside>
      </div>
    </div>
  );
}
