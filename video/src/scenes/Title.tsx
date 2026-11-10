import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Dots, GridPaper } from "../Pixel";
import { C, head, mono } from "../theme";

export const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <GridPaper>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", fontFamily: mono, color: C.ink }}>
        <Dots text="SIEVE" cell={30} reveal={1.4 * fps} seed="title" off={0.08} />
        <div
          style={{
            fontFamily: head, fontSize: 92, letterSpacing: "-0.045em", textTransform: "uppercase", marginTop: 70,
            opacity: interpolate(frame, [1.5 * fps, 2.2 * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            translate: interpolate(frame, [1.5 * fps, 2.2 * fps], ["0px 30px", "0px 0px"], {
              extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          Grant reviews you can check
        </div>
        <div
          style={{
            fontSize: 34, color: C.soft, marginTop: 24,
            opacity: interpolate(frame, [2.4 * fps, 3 * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          }}
        >
          Verifiable AI review for NEAR DAOs
        </div>
      </AbsoluteFill>
    </GridPaper>
  );
};
