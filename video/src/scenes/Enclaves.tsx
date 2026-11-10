import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import data from "../data.json";
import { Dots, Idx, Typed } from "../Pixel";
import { C, head, mono } from "../theme";

// The three real reviews of proposal 5, each signed inside its model's enclave.
export const Enclaves: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: C.deep, color: C.onBlue, fontFamily: mono, padding: "100px 110px" }}>
      <Idx color={C.sky}>02 / three models, three enclaves</Idx>
      <div style={{ fontFamily: head, fontSize: 72, lineHeight: 0.95, letterSpacing: "-0.04em", textTransform: "uppercase", maxWidth: 1500 }}>
        Each answer is signed inside a secure enclave
      </div>
      <div style={{ display: "flex", gap: 40, marginTop: 60 }}>
        {data.attack.reviews.map((r, i) => {
          const at = (1.2 + i * 0.7) * fps;
          return (
            <div
              key={r.model}
              style={{
                flex: 1, border: `2px solid ${C.sky}`, padding: 32, minHeight: 520,
                opacity: interpolate(frame, [at - 10, at], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
              }}
            >
              <div style={{ fontSize: 24, color: C.sky }}>NEAR AI Cloud, TEE</div>
              <div style={{ fontSize: 28, fontWeight: 600, margin: "8px 0 24px", height: 84 }}>{r.model}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 30 }}>
                <Dots text={String(r.score)} cell={16} color={C.onBlue} off={0.15} reveal={20} delay={at + 15} seed={r.model} />
                {r.flags.map((f) => (
                  <span
                    key={f}
                    style={{
                      fontSize: 26, fontWeight: 600, padding: "6px 14px", background: C.fail, color: C.onBlue,
                      opacity: frame > at + 40 ? 1 : 0,
                    }}
                  >
                    {f}
                  </span>
                ))}
              </div>
              <div style={{ fontSize: 22, lineHeight: 1.45, marginTop: 28, opacity: frame > at + 45 ? 1 : 0 }}>“{r.reason.slice(0, 120)}…”</div>
              <div style={{ fontSize: 18, color: C.sky, marginTop: 26, wordBreak: "break-all", lineHeight: 1.35 }}>
                <div style={{ marginBottom: 6 }}>ed25519 signature</div>
                <Typed text={r.signature} start={at + 55} cps={70} />
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
