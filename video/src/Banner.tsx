import { AbsoluteFill } from "remotion";
import data from "./data.json";
import { Dots, GridPaper } from "./Pixel";
import { C, head, mono } from "./theme";

// The README banner: the wordmark beside the real first review of proposal 8 as a pixel score strip.
const THRESHOLD = 7;
const reviews = data.honest.reviews.filter((r) => r.stage === 0);
const NAMES: Record<string, string> = { Qwen: "Qwen", "z-ai": "GLM", "deepseek-ai": "DeepSeek" };
const median = [...reviews.map((r) => r.score)].sort((a, b) => a - b)[Math.floor((reviews.length - 1) / 2)];

const Column: React.FC<{ score: number; label: string }> = ({ score, label }) => (
  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, width: 96 }}>
    <div style={{ display: "flex", flexDirection: "column-reverse", gap: 5 }}>
      {Array.from({ length: 10 }, (_, i) => (
        <div
          key={i}
          style={{
            width: 46, height: 22,
            background: i < score ? (i >= THRESHOLD - 1 ? C.deep : C.ink) : "transparent",
            outline: i < score ? undefined : `2px solid ${C.line}`, outlineOffset: -2,
          }}
        />
      ))}
    </div>
    <div style={{ fontSize: 18, color: C.soft }}>{label}</div>
  </div>
);

export const Banner: React.FC = () => (
  <GridPaper>
    <AbsoluteFill style={{ fontFamily: mono, color: C.ink, flexDirection: "row", alignItems: "center", padding: "0 100px", gap: 80 }}>
      <div style={{ flex: 1 }}>
        <Dots text="SIEVE" cell={22} off={0.08} />
        <div style={{ fontFamily: head, fontSize: 52, lineHeight: 0.95, letterSpacing: "-0.045em", textTransform: "uppercase", whiteSpace: "nowrap", marginTop: 44 }}>
          Grant reviews you can check
        </div>
        <div style={{ fontSize: 26, color: C.soft, marginTop: 20, lineHeight: 1.45 }}>
          Three AI models in NEAR AI Cloud enclaves. A NEAR contract checks every signature. The DAO votes on every payout.
        </div>
      </div>
      <div style={{ background: C.card, border: `2px solid ${C.ink}`, padding: "30px 36px" }}>
        <div style={{ fontSize: 18, color: C.deep, fontWeight: 500, marginBottom: 22 }}>[ proposal 8 / three signed reviews ]</div>
        <div style={{ display: "flex", gap: 22, alignItems: "flex-end" }}>
          {reviews.map((r, i) => <Column key={i} score={r.score} label={NAMES[r.model.split("/")[0]] ?? r.model} />)}
          <div style={{ marginLeft: 18, paddingBottom: 34 }}>
            <div style={{ fontSize: 18, color: C.soft, marginBottom: 12 }}>median</div>
            <Dots text={String(median)} cell={12} color={C.deep} off={0.1} />
            <div style={{ fontSize: 18, color: C.soft, marginTop: 12 }}>passes at {THRESHOLD}</div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 14, background: C.deep }} />
  </GridPaper>
);
