import { useEffect, useMemo, useState } from "react";
import { useI18n, type Locale } from "../i18n";
import stats from "./repoStats.json";
import { buildStations, NIGHT_OIL, BEST_KEY, type NightBest } from "./nightwatch.copy";
import "../styles/nightwatch.css";

/**
 * 巡夜 · 子时之后 — The Night Watch.
 *
 * A walking tour of the whole product at night as the ledger's keeper.
 * Seven stations, three drops of lantern oil, every question answered from
 * real repository arithmetic — the game cannot lie to you. Beat your own
 * best time; the dawn is there when you reach it.
 */

const pick = (rec: Record<Locale, string>, locale: Locale) => rec[locale];

function loadBest(): NightBest | null {
  try {
    const raw = window.localStorage.getItem(BEST_KEY);
    return raw ? (JSON.parse(raw) as NightBest) : null;
  } catch {
    return null;
  }
}

function saveBest(best: NightBest) {
  try {
    window.localStorage.setItem(BEST_KEY, JSON.stringify(best));
  } catch {
    /* storage unavailable */
  }
}

export default function NightWatch() {
  const { locale } = useI18n();
  const zh = locale === "zh";

  const stations = useMemo(
    () => buildStations(stats as unknown as Parameters<typeof buildStations>[0]),
    [],
  );

  const [phase, setPhase] = useState<"intro" | "playing" | "won" | "lost">("intro");
  const [stationIndex, setStationIndex] = useState(0);
  const [oil, setOil] = useState(NIGHT_OIL);
  const [moves, setMoves] = useState(0);
  const [wrongPick, setWrongPick] = useState<number | null>(null);
  const [startedAt, setStartedAt] = useState(0);
  const [finishedMs, setFinishedMs] = useState(0);
  const [best, setBest] = useState<NightBest | null>(() => loadBest());
  const [newBest, setNewBest] = useState(false);

  const station = stations[stationIndex];

  // Options are shuffled once per station arrival.
  const order = useMemo(() => {
    const ids = [0, 1, 2, 3];
    for (let i = ids.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [ids[i], ids[j]] = [ids[j], ids[i]];
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stationIndex, phase]);

  useEffect(() => {
    if (wrongPick === null) return;
    const t = window.setTimeout(() => setWrongPick(null), 650);
    return () => window.clearTimeout(t);
  }, [wrongPick]);

  function begin() {
    setPhase("playing");
    setStationIndex(0);
    setOil(NIGHT_OIL);
    setMoves(0);
    setWrongPick(null);
    setStartedAt(Date.now());
    setNewBest(false);
  }

  function choose(pickedDisplayIndex: number) {
    if (phase !== "playing" || wrongPick !== null) return;
    const sourceIndex = order[pickedDisplayIndex];
    setMoves((m) => m + 1);
    if (sourceIndex === station.correctIndex) {
      if (stationIndex === stations.length - 1) {
        const ms = Date.now() - startedAt;
        setFinishedMs(ms);
        setPhase("won");
        const candidate = { timeMs: ms, oilLeft: oil, moves: moves + 1, date: new Date().toISOString().slice(0, 10) };
        if (!best || ms < best.timeMs) {
          setBest(candidate);
          saveBest(candidate);
          setNewBest(true);
        }
      } else {
        setStationIndex((i) => i + 1);
      }
      setWrongPick(null);
    } else {
      setOil((v) => {
        const next = v - 1;
        if (next <= 0) setPhase("lost");
        return Math.max(next, 0);
      });
      setWrongPick(pickedDisplayIndex);
    }
  }

  const hourLabel = (i: number) => stations[i]?.hourZh ?? "";

  return (
    <div className="nightwatch-page">
      {/* ── Celestial backdrop ─────────────────────────────────── */}
      <div className="night-sky" aria-hidden="true">
        <div className="night-moon" />
        <div className="night-stars" />
        <div className="night-fog" />
      </div>

      <header className="night-header">
        <p className="night-kicker">{zh ? "史 官 守 夜 · 铁 证 巡 夜" : "THE LEDGER'S KEEPER · NIGHT WATCH"}</p>
        <h1 className="night-title">{zh ? "子时之后" : "After the Hour of the Rat"} <span className="night-title-en">{zh ? "AFTER THE HOUR OF THE RAT" : "子时之后"}</span></h1>
        {best && phase !== "playing" && (
          <p className="night-best">
            {zh
              ? `最好的一夜：${Math.round(best.timeMs / 1000)} 秒 · 余灯 ${best.oilLeft} 滴 · ${best.date}`
              : `Best night: ${Math.round(best.timeMs / 1000)}s · ${best.oilLeft} oil left · ${best.date}`}
          </p>
        )}
      </header>

      {/* ── Intro ───────────────────────────────────────────────── */}
      {phase === "intro" && (
        <section className="night-panel night-intro">
          <p className="night-lead">
            {zh
              ? "子时三刻，万籁俱寂。你，史官，提灯上岗——这片大陆的每一格铁证，都归你今夜守护。"
              : "Three quarters past midnight, all silent. You, the chronicler, take the lamp — every square of iron evidence on this isle is yours to keep until dawn."}
          </p>
          <p className="night-body">
            {zh
              ? "七站守夜人，演一遍要走过的路：差分之炉、编年之柱、铁样寨地、铁证书房、缓存圣断、印章庭、证据群岛。灯油只有三滴——答错一站就少一滴。走到戌时，天就亮了。"
              : "Seven stations, the road in order: the Foundry, the Chronicle Pillar, the Census Yard, the Reading Room, the Cache Sanctum, the Cartouche Court, the Archipelago. You carry three drops of oil — every wrong answer burns one. Reach the hour of the Dog, and dawn breaks."}
          </p>
          <p className="night-body night-rule">
            {zh
              ? "本卷每一问的答案都从仓库现推：编年史几节、文件几块、书房几卷、缓存报了多少——全是 git 与账本的现场结论，不是编出来的题。"
              : "Every answer in this round is derived live from the repository: how many chronicle entries, how many tracked files, how many sections in the book, what the gateway reported. No question is invented."}
          </p>
          <button className="night-begin" onClick={begin}>
            {zh ? "提灯上岗 →" : "Take the lamp →"}
          </button>
        </section>
      )}

      {/* ── Night walk progress rail ────────────────────────────── */}
      {phase === "playing" && (
        <>
          <ol className="night-rail" aria-label={zh ? "守夜进度" : "Watch progress"}>
            {stations.map((_, i) => (
              <li key={i} className={i < stationIndex ? "is-done" : i === stationIndex ? "is-current" : "is-todo"}>
                <span className="night-rail-hour">{hourLabel(i)}</span>
                <span className="night-rail-dot" aria-hidden="true" />
              </li>
            ))}
          </ol>

          <div className="night-oil" aria-label={zh ? `剩余灯油 ${oil} 滴` : `${oil} drops of oil left`}>
            {Array.from({ length: NIGHT_OIL }, (_, i) => (
              <span key={i} className={i < oil ? "oil-flame is-alive" : "oil-flame is-dead"} aria-hidden="true" />
            ))}
            <span className="night-oil-label">{zh ? `灯油 ${oil}/${NIGHT_OIL}` : `OIL ${oil}/${NIGHT_OIL}`}</span>
          </div>

          <section className="night-panel night-station" key={stationIndex}>
            <p className="night-station-hour">{zh ? station.hourZh : station.hourEn}<span className="night-station-sep">·</span><span className="night-station-place">{zh ? station.placeZh : station.placeEn}</span></p>
            <p className="night-lore">{zh ? station.loreZh : station.loreEn}</p>
            <h2 className="night-question">{pick(station.q, locale)}</h2>
            <div className="night-options">
              {order.map((sourceIndex, displayIndex) => (
                <button
                  key={displayIndex}
                  className={wrongPick === displayIndex ? "night-option is-wrong" : "night-option"}
                  onClick={() => choose(displayIndex)}
                >
                  <span className="night-option-mark" aria-hidden="true">{["①", "②", "③", "④"][displayIndex]}</span>
                  {station.options[locale][sourceIndex]}
                </button>
              ))}
            </div>
          </section>
        </>
      )}

      {/* ── Dawn ────────────────────────────────────────────────── */}
      {phase === "won" && (
        <section className="night-panel night-dawn">
          <p className="night-dawn-kicker">{zh ? "戌 时 已 满" : "THE HOUR OF THE DOG IS FULL"}</p>
          <h2>{zh ? "天亮了" : "Dawn breaks"}</h2>
          <p className="night-lore">
            {zh
              ? "守夜人把最后一滴灯油浇给黎明。总策（判词）都盖上了；编年史又多了一个你没写下、但你走过的早晨。"
              : "The keeper spends the last drop on the dawn. Every verdict is sealed; the Chronicle gains one more morning you never wrote — because you walked it."}
          </p>
          <div className="night-dawn-stats">
            <div><p>{Math.round(finishedMs / 1000)}s</p><span>{zh ? "用时" : "time"}</span></div>
            <div><p>{oil}</p><span>{zh ? "余灯" : "oil left"}</span></div>
            <div><p>{moves}</p><span>{zh ? "尝试" : "tries"}</span></div>
          </div>
          {newBest && <p className="night-newbest">{zh ? "⚑ 最好的一夜——已入册" : "⚑ Your best night — recorded"}</p>}
          <div className="night-dawn-actions">
            <button className="night-begin" onClick={begin}>{zh ? "再守一夜 →" : "Another night →"}</button>
            <a className="night-ghost" href="#/chronicle">{zh ? "去编年史看那一夜 →" : "See that night in the Chronicle →"}</a>
          </div>
        </section>
      )}

      {/* ── Darkness ────────────────────────────────────────────── */}
      {phase === "lost" && (
        <section className="night-panel night-dusk">
          <p className="night-dusk-kicker">{zh ? "灯 油 尽 了" : "THE OIL IS GONE"}</p>
          <h2>{zh ? "夜还是夜" : "The night is still the night"}</h2>
          <p className="night-lore">
            {zh
              ? "三滴灯油，三次答错。这不是惩罚——是铁证给守夜人的提醒：没看懂的，就别签字。"
              : "Three drops, three misses. Not a punishment — iron evidence reminding its keeper: what you did not understand, you do not sign."}
          </p>
          <div className="night-dawn-actions">
            <button className="night-begin" onClick={begin}>{zh ? "重来一夜 →" : "Try this night again →"}</button>
            <a className="night-ghost" href="#/tour">{zh ? "先去巡览补课 →" : "Catch up with the Tour first →"}</a>
          </div>
        </section>
      )}
    </div>
  );
}
