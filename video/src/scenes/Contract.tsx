import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import data from "../data.json";
import { Dots, GridPaper, Idx } from "../Pixel";
import { C, head, mono } from "../theme";

const steps = [
  "Rebuild the exact prompt from the rubric stored in the round",
  "Hash request and answer with SHA-256",
  "Check each signature against the model key registered after attestation",
  "Read the score from the signed answer and take the median",
  "Any model flagged injection: the proposal cannot pass",
];

// One cell per score from 0 to 10, three rows: the same strip the page draws.
const Strip: React.FC<{ scores: number[]; threshold: number; show: number }> = ({ scores, threshold, show }) => (
  <div style={{ display: "grid", gridTemplateColumns: "repeat(11, 56px)", gap: 8 }}>
    {Array.from({ length: 11 }, (_, v) => {
      const n = scores.slice(0, show).filter((s) => s === v).length;
      return (
        <div key={v} style={{ display: "grid", gap: 8 }}>
          {[2, 1, 0].map((k) => (
            <div key={k} style={{ width: 56, height: 56, background: v >= threshold ? C.blue : C.ink, opacity: k < n ? 1 : v >= threshold ? 0.22 : 0.1 }} />
          ))}
          <div style={{ fontSize: 22, color: C.soft, textAlign: "center" }}>{v}</div>
        </div>
      );
    })}
  </div>
);

export const Contract: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const scores = data.attack.reviews.map((r) => r.score);
  const tick = (i: number) => (1 + i * 1.1) * fps;
  return (
    <GridPaper>
      <AbsoluteFill style={{ padding: "100px 110px", fontFamily: mono, color: C.ink }}>
        <Idx>03 / the NEAR contract checks</Idx>
        <div style={{ fontFamily: head, fontSize: 72, lineHeight: 0.95, letterSpacing: "-0.04em", textTransform: "uppercase" }}>
          Nothing counts until the contract checks it
        </div>
        <div style={{ display: "flex", gap: 90, marginTop: 56 }}>
          <div style={{ flex: "0 0 860px" }}>
            {steps.map((s, i) => (
              <div
                key={s}
                style={{
                  display: "flex", gap: 22, alignItems: "baseline", fontSize: 30, lineHeight: 1.35, padding: "16px 0",
                  borderBottom: `2px solid ${C.line}`,
                  opacity: interpolate(frame, [tick(i), tick(i) + 8], [0.2, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                }}
              >
                <span style={{ width: 22, height: 22, flex: "none", background: i === 4 ? C.fail : C.deep, translate: "0px 3px" }} />
                {s}
              </div>
            ))}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 26, color: C.soft, marginBottom: 16 }}>Proposal {data.attack.id}, median</div>
            <Dots text="0" cell={22} color={C.fail} reveal={15} delay={tick(3)} />
            <div style={{ marginTop: 40 }}>
              <Strip scores={scores} threshold={7} show={Math.floor(interpolate(frame, [tick(3), tick(3) + 20], [0, 3], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }))} />
            </div>
            <div style={{ fontSize: 28, fontWeight: 600, color: C.fail, marginTop: 30, opacity: frame > tick(4) + 10 ? 1 : 0 }}>
              Did not pass. Flagged injection by all three models.
            </div>
          </div>
        </div>
      </AbsoluteFill>
    </GridPaper>
  );
};
