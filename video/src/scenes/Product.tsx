import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { GridPaper, Idx } from "../Pixel";
import { C, head, mono } from "../theme";

// Screenshots of the live page (video/scripts/capture.mjs), scrolled inside a browser frame.
const Shot: React.FC<{ src: string; from: number; to: number; scrollTo: number }> = ({ src, from, to, scrollTo }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute", inset: 0,
        opacity: interpolate(frame, [from, from + 8, to - 8, to], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
      }}
    >
      <Img
        src={staticFile(src)}
        style={{
          width: "175%",
          marginLeft: "-37.5%",
          translate: interpolate(frame, [from + 20, to - 10], ["0px 0px", `0px ${-scrollTo}px`], {
            extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic),
          }),
        }}
      />
    </div>
  );
};

export const Product: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <GridPaper>
      <AbsoluteFill style={{ padding: "80px 110px", fontFamily: mono, color: C.ink, flexDirection: "row", gap: 70 }}>
        <div style={{ flex: "0 0 520px", paddingTop: 20 }}>
          <Idx>06 / the page</Idx>
          <div style={{ fontFamily: head, fontSize: 64, lineHeight: 0.95, letterSpacing: "-0.04em", textTransform: "uppercase" }}>
            Your browser re-checks every review
          </div>
          <div style={{ fontSize: 28, lineHeight: 1.5, color: C.soft, marginTop: 34 }}>
            It reads the proposal and the model key from a NEAR RPC node, rebuilds the request and verifies the enclave's signature. Applicants submit with a NEAR wallet.
          </div>
        </div>
        <div style={{ flex: 1, border: `2px solid ${C.ink}`, background: C.card, display: "flex", flexDirection: "column" }}>
          <div style={{ height: 48, borderBottom: `2px solid ${C.ink}`, display: "flex", alignItems: "center", gap: 10, padding: "0 18px" }}>
            {[0, 1, 2].map((i) => <div key={i} style={{ width: 14, height: 14, background: C.ink, opacity: 0.3 }} />)}
            <div style={{ fontSize: 20, color: C.soft, marginLeft: 16 }}>sieve, on NEAR testnet</div>
          </div>
          <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
            <Shot src="shots/home.png" from={0} to={3.6 * fps} scrollTo={420} />
            <Shot src="shots/proposal.png" from={3.4 * fps} to={9 * fps} scrollTo={2250} />
          </div>
        </div>
      </AbsoluteFill>
    </GridPaper>
  );
};
