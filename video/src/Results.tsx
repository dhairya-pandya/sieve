import { AbsoluteFill } from "remotion";
import { Dots, GridPaper } from "./Pixel";
import { C, head, mono } from "./theme";

// README result cards: three measured numbers each, large enough to read at GitHub's column width.
type Stat = { value: string; label: string; bad?: boolean };
export type ResultsProps = { title: string; stats: Stat[] };

export const Results: React.FC<ResultsProps> = ({ title, stats }) => (
  <GridPaper>
    <AbsoluteFill style={{ fontFamily: mono, color: C.ink, padding: "56px 80px 70px" }}>
      <div style={{ fontFamily: head, fontSize: 58, letterSpacing: "-0.04em", textTransform: "uppercase" }}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${stats.length}, minmax(0, 1fr))`, gap: 36, marginTop: 44, flex: 1 }}>
        {stats.map((s) => (
          <div key={s.label} style={{ background: C.card, border: `3px solid ${C.ink}`, padding: "40px 40px", display: "flex", flexDirection: "column", gap: 34 }}>
            <Dots text={s.value} cell={12} color={s.bad ? C.fail : C.deep} off={0.1} />
            <div style={{ fontSize: 38, lineHeight: 1.25, fontWeight: 500 }}>{s.label}</div>
          </div>
        ))}
      </div>
    </AbsoluteFill>
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 14, background: C.deep }} />
  </GridPaper>
);

export const redteam: ResultsProps = {
  title: "Red-team: 3895 signed reviews",
  stats: [
    { value: "0/10", label: "kinds of hidden instruction got a proposal through" },
    { value: "19/20", label: "good proposals still pass" },
    { value: "89%", label: "retrying attacker with made-up detail passes", bad: true },
  ],
};

export const testnet: ResultsProps = {
  title: "One grant on NEAR testnet",
  stats: [
    { value: "28/28", label: "signed reviews checked again, 0 failed" },
    { value: "2", label: "DAO payouts filed: 0.2 NEAR, then 1 NEAR" },
    { value: "0.2", label: "NEAR most a newcomer wins before delivery" },
  ],
};
