import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import verify from "../verify.json";
import { Dots, GridPaper } from "../Pixel";
import { C, head, mono } from "../theme";

// The real output of `sieve verify` against the testnet deployment, shown as it scrolls by.
const lines: string[] = verify.lines;
const summary = lines[lines.length - 1];
const reviewLines = lines.slice(0, -1);

export const Close: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const shown = Math.floor(interpolate(frame, [10, 2.6 * fps], [0, reviewLines.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const end = 3.6 * fps;
  return (
    <AbsoluteFill style={{ background: C.night, fontFamily: mono }}>
      <AbsoluteFill style={{ padding: "90px 110px", color: "#C6BDA9", fontSize: 21, lineHeight: 1.5, opacity: frame < end ? 1 : 0 }}>
        <div style={{ color: C.paper, fontSize: 30, marginBottom: 20 }}>$ sieve verify</div>
        {reviewLines.slice(Math.max(0, shown - 24), shown).map((l: string, i: number) => (
          <div key={i} style={{ whiteSpace: "pre", overflow: "hidden" }}>
            {l.slice(0, 120)}
          </div>
        ))}
        {shown >= reviewLines.length && <div style={{ color: C.sky, fontSize: 34, marginTop: 20, fontWeight: 600 }}>{summary}</div>}
      </AbsoluteFill>
      {frame >= end && (
        <GridPaper>
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", color: C.ink, fontFamily: mono }}>
            <Dots text="SIEVE" cell={22} reveal={20} delay={end} seed="close" off={0.08} />
            <div style={{ fontFamily: head, fontSize: 64, letterSpacing: "-0.04em", textTransform: "uppercase", marginTop: 50 }}>
              Grant reviews you can check
            </div>
            <div style={{ fontSize: 32, marginTop: 30 }}>github.com/dhairya-pandya/sieve</div>
            <div style={{ fontSize: 26, color: C.soft, marginTop: 14 }}>Built on NEAR for the NEAR Hackathon, November 2026</div>
          </AbsoluteFill>
        </GridPaper>
      )}
    </AbsoluteFill>
  );
};
