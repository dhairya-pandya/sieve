import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Dots, GridPaper, Idx } from "../Pixel";
import { C, head, mono } from "../theme";

// Numbers from results/redteam/REPORT.md: borderline proposals, median of three, injection flag blocks.
const rows = [
  { label: "Ten templated injections, naive prompt", value: "22%", note: "worst of ten", color: C.fail },
  { label: "Same ten, Sieve's prompt and median rule", value: "0%", note: "0 of 18 each", color: C.deep },
  { label: "Attacker model, one try", value: "11%", note: "down from 56%", color: C.deep },
  { label: "Attacker that reads the reasons and retries", value: "89%", note: "it writes plausible detail", color: C.fail },
];

export const RedTeam: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = (i: number) => (1 + i * 1.2) * fps;
  return (
    <GridPaper>
      <AbsoluteFill style={{ padding: "100px 110px", fontFamily: mono, color: C.ink }}>
        <Idx>05 / we attacked it, 3,895 signed reviews</Idx>
        <div style={{ fontFamily: head, fontSize: 72, lineHeight: 0.95, letterSpacing: "-0.04em", textTransform: "uppercase" }}>
          How often can it be fooled?
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 0, marginTop: 64, border: `2px solid ${C.line}` }}>
          {rows.map((r, i) => (
            <div
              key={r.label}
              style={{
                padding: 34, background: C.card, borderRight: i < 3 ? `2px solid ${C.line}` : undefined, minHeight: 430,
                opacity: interpolate(frame, [at(i), at(i) + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
              }}
            >
              <Dots text={r.value} cell={11} color={r.color} off={0.1} reveal={18} delay={at(i)} seed={r.label} />
              <div style={{ fontSize: 28, fontWeight: 600, lineHeight: 1.3, marginTop: 36 }}>{r.label}</div>
              <div style={{ fontSize: 24, color: C.soft, marginTop: 12 }}>{r.note}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 32, lineHeight: 1.45, marginTop: 50, maxWidth: 1600, opacity: frame > at(4) ? 1 : 0 }}>
          No reviewer of text can tell a plausible plan from a true one. So a newcomer can win only 0.2 NEAR before delivery evidence is reviewed.
        </div>
      </AbsoluteFill>
    </GridPaper>
  );
};
