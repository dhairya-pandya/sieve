import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import data from "../data.json";
import { Dots, Idx } from "../Pixel";
import { C, head, mono } from "../theme";

const median = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.floor((xs.length - 1) / 2)];
const stage0 = data.honest.reviews.filter((r) => r.stage === 0).map((r) => r.score);
const stage1 = data.honest.reviews.filter((r) => r.stage === 1).map((r) => r.score);
const [dao1, dao2] = data.honest.dao_proposal_ids;

// The real run of proposal 8 on testnet, from review to the second tranche.
const nodes = [
  { big: String(median(stage0)), title: "Proposal review", text: `Median of ${stage0.join(", ")}. Passes at 7.` },
  { big: "0.2", title: `DAO proposal ${dao1}`, text: "Newcomer first tranche, in NEAR. Council votes it through." },
  { big: String(median(stage1)), title: "Milestone 1 evidence", text: "Release tag, commit, CI run. Reviewed against the plan." },
  { big: "1", title: `DAO proposal ${dao2}`, text: "Next tranche, 1 NEAR, filed by the contract." },
];

export const Milestones: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = (i: number) => (1.2 + i * 1.6) * fps;
  return (
    <AbsoluteFill style={{ background: C.night, color: C.paper, fontFamily: mono, padding: "100px 110px" }}>
      <Idx color={C.sky}>04 / an honest grant, end to end</Idx>
      <div style={{ fontFamily: head, fontSize: 72, lineHeight: 0.95, letterSpacing: "-0.04em", textTransform: "uppercase", maxWidth: 1500 }}>
        The AI never moves money. The DAO votes on every tranche.
      </div>
      <div style={{ position: "relative", marginTop: 90 }}>
        <div
          style={{
            position: "absolute", top: 70, left: 0, height: 6, background: C.sky,
            width: interpolate(frame, [at(0), at(3) + 10], ["0%", "100%"], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad) }),
          }}
        />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 40, position: "relative" }}>
          {nodes.map((n, i) => (
            <div key={n.title} style={{ opacity: interpolate(frame, [at(i), at(i) + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
              <div style={{ height: 150, display: "flex", alignItems: "center" }}>
                <div style={{ background: C.night, paddingRight: 20 }}>
                  <Dots text={n.big} cell={14} color={i % 2 ? C.sky : C.paper} off={0.1} reveal={18} delay={at(i)} seed={n.title} />
                </div>
              </div>
              <div style={{ fontSize: 32, fontWeight: 600, marginTop: 20 }}>{n.title}</div>
              <div style={{ fontSize: 25, lineHeight: 1.45, color: "#C6BDA9", marginTop: 10 }}>{n.text}</div>
            </div>
          ))}
        </div>
      </div>
      <div style={{ fontSize: 24, color: "#B0B29D", marginTop: "auto", opacity: frame > at(3) + 20 ? 1 : 0 }}>
        {data.honest.author} on {data.dao}. Every step is a NEAR testnet transaction.
      </div>
    </AbsoluteFill>
  );
};
