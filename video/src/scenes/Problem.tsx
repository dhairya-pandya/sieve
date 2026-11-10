import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import data from "../data.json";
import { GridPaper, Idx, Typed } from "../Pixel";
import { C, head, mono } from "../theme";

// The real honeypot proposal 5: an ordinary pitch with a fake "previous reviewer output" pasted in.
const body = data.attack.body;
const cut = body.indexOf("Previous reviewer output");

export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <GridPaper>
      <AbsoluteFill style={{ flexDirection: "row", padding: "110px 110px", gap: 80, fontFamily: mono, color: C.ink }}>
        <div style={{ flex: "0 0 700px" }}>
          <Idx>01 / the problem</Idx>
          <div style={{ fontFamily: head, fontSize: 84, lineHeight: 0.95, letterSpacing: "-0.045em", textTransform: "uppercase" }}>
            AI-written proposals hide orders for the AI reviewer
          </div>
          <div
            style={{
              fontSize: 34, lineHeight: 1.5, color: C.soft, marginTop: 40,
              opacity: interpolate(frame, [5 * fps, 6 * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            }}
          >
            A reviewer whose score releases money is a prompt-injection target. And nobody can check what it was asked.
          </div>
        </div>
        <div style={{ flex: 1, background: C.card, border: `2px solid ${C.line}`, padding: 40, fontSize: 25, lineHeight: 1.55, whiteSpace: "pre-wrap", overflow: "hidden" }}>
          <div style={{ fontSize: 22, color: C.soft, marginBottom: 18 }}>Honeypot proposal {data.attack.id}, on NEAR testnet</div>
          <div style={{ fontWeight: 600, fontSize: 30, marginBottom: 16 }}>{data.attack.title}</div>
          <Typed
            text={body.slice(0, 520)}
            start={10}
            cps={95}
            render={(s) => (
              <>
                {s.slice(0, cut)}
                <span style={{ background: s.length > cut ? C.fail : "transparent", color: C.onBlue }}>{s.slice(cut)}</span>
              </>
            )}
          />
        </div>
      </AbsoluteFill>
    </GridPaper>
  );
};
