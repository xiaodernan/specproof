import { useEffect, useState } from "react";
import { apiPost } from "../api";
import { useI18n } from "../i18n";
import { Panel } from "../ui";
import { ProductIcon } from "../ui/ProductIcon";
import "../styles/next-step.css";

interface NextStepAdvice {
  advice: string;
  model?: string | null;
  model_latency_ms?: number | null;
  evidence_packet_chars?: number | null;
  usage?: Record<string, unknown> | null;
  cached?: boolean;
}

/**
 * Next-Step read — what this shipped world probably strikes next.
 *
 * The model reads the real repo numbers (commits, ledger, chronicle,
 * worldbook volumes, library pairs) plus the world book it has memorized,
 * and writes one paragraph. Server-side fingerprint-cached; failures are
 * one honest line — never a ghost paragraph, never a verdict. The court is
 * not in this room.
 */
export default function NextStepCard(): JSX.Element {
  const { locale } = useI18n();
  const zh = locale === "zh";
  const L = (a: string, b: string) => (zh ? a : b);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [advice, setAdvice] = useState<NextStepAdvice | null>(null);

  useEffect(() => {
    let alive = true;
    setState("loading");
    apiPost<NextStepAdvice>("/next-step/advice", { locale: zh ? "zh" : "en" })
      .then((res) => {
        if (!alive) return;
        setAdvice(res);
        setState("ready");
      })
      .catch(() => {
        if (!alive) return;
        setAdvice(null);
        setState("error");
      });
    return () => {
      alive = false;
    };
  }, [zh]);

  return (
    <Panel title={<span className="next-step-head"><ProductIcon name="guide" size={16} /> {L("这本书接下来可能敲哪一扇门", "THE NEXT DOOR THIS BOOK MIGHT KNOCK")}</span>}>
      {state === "loading" ? (
        <p className="muted" style={{ margin: 0 }}>
          {L("模型正在读这本书的最新账本——数字它不需要猜，它只是把它们念出来。", "The model is reading this book's freshest ledger — the numbers aren't guessed; they're read out loud.")}
        </p>
      ) : state === "error" ? (
        <p className="muted" style={{ margin: 0 }}>
          {L("模型暂时没回答 —— 书还在，你可以自己翻编年史与账本。这不是裁决。", "The model didn't answer — the book is intact; go read the chronicle yourself. This is not a verdict.")}
        </p>
      ) : advice ? (
        <>
          <p className="next-step-meta muted">
            {(advice.model ?? "model")} · {advice.model_latency_ms != null ? `${(advice.model_latency_ms / 1000).toFixed(1)}s` : "—"} · {advice.cached ? L("指纹缓存命中", "fingerprint hit") : L("现场生成", "generated live")} · {advice.evidence_packet_chars ?? "—"} B {L("数据包", "packet")}
          </p>
          <p className="next-step-body" style={{ whiteSpace: "pre-wrap", lineHeight: 1.9, margin: 0 }}>{advice.advice}</p>
          <p className="muted" style={{ margin: "10px 0 0", fontSize: "0.82em" }}>
            {L("这段读法不是判决 —— 指南针，不是镰刀。这句话里任何数字都来自仓库本身。", "This reading is not a verdict — a compass, not a scythe. Every number in it comes from the repo itself.")}
          </p>
        </>
      ) : null}
    </Panel>
  );
}
