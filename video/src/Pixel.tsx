import type React from "react";
import type { TransitionPresentationComponentProps } from "@remotion/transitions";
import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { C } from "./theme";

// 5 by 7 dot-matrix glyphs, as on the Sieve page and the hackathon site.
const GLYPHS: Record<string, string> = {
  "0": "01110100011000110001100011000101110", "1": "00100011000010000100001000010001110",
  "2": "01110100010000100010001000100011111", "3": "11111000100010000010000011000101110",
  "4": "00010001100101010010111110001000010", "5": "11111100001111000001000011000101110",
  "6": "00110010001000011110100011000101110", "7": "11111000010001000100010000100001000",
  "8": "01110100011000101110100011000101110", "9": "01110100011000101111000010001001100",
  "/": "00001000010001000100010001000010000", ".": "00000000000000000000000000110001100",
  "%": "11000110010001000100010001001100011", "-": "00000000000000011111000000000000000",
  " ": "00000000000000000000000000000000000",
  S: "01111100001000001110000010000111110", I: "01110001000010000100001000010001110",
  E: "11111100001000011110100001000011111", V: "10001100011000110001100010101000100",
};

type DotProps = {
  text: string;
  cell: number;
  color?: string;
  off?: number;
  // Frames over which the lit cells switch on, in a seeded random order; 0 shows everything at once.
  reveal?: number;
  delay?: number;
  seed?: string;
};

// Kept as a component of its own so only the digits re-render each frame.
export const Dots: React.FC<DotProps> = ({ text, cell, color = C.ink, off = 0.12, reveal = 0, delay = 0, seed = text }) => {
  const frame = useCurrentFrame();
  const gap = Math.max(1, Math.round(cell / 3));
  return (
    <div style={{ display: "inline-flex", gap: cell + gap }}>
      {[...text].map((ch, k) => (
        <div key={k} style={{ display: "grid", gridTemplateColumns: `repeat(5, ${cell}px)`, gap }}>
          {[...(GLYPHS[ch] ?? GLYPHS[" "])].map((b, i) => {
            const at = delay + (reveal ? random(`${seed}-${k}-${i}`) * reveal : 0);
            const on = b === "1" && frame >= at;
            return <div key={i} style={{ width: cell, height: cell, background: color, opacity: on ? 1 : off }} />;
          })}
        </div>
      ))}
    </div>
  );
};

// Graph paper, the hackathon hero's ground.
export const GridPaper: React.FC<{ size?: number; color?: string; children?: React.ReactNode; style?: React.CSSProperties }> = ({
  size = 40, color = C.grid, children, style,
}) => (
  <AbsoluteFill
    style={{
      backgroundColor: C.paper,
      backgroundImage: `linear-gradient(${color} 1px, transparent 1px), linear-gradient(90deg, ${color} 1px, transparent 1px)`,
      backgroundSize: `${size}px ${size}px`,
      ...style,
    }}
  >
    {children}
  </AbsoluteFill>
);

// A scene cut that dissolves the old frame block by block: cells of the incoming scene switch on in a
// seeded random order, so the change reads as pixels rather than a crossfade.
export const PixelWipe: React.FC<TransitionPresentationComponentProps<Record<string, never>>> = ({
  children, presentationDirection, presentationProgress,
}) => {
  if (presentationDirection === "exiting") return <AbsoluteFill>{children}</AbsoluteFill>;
  const cols = 24, rows = 14;
  let rects = "";
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      if (random(`wipe-${x}-${y}`) < presentationProgress) rects += `<rect x='${x}' y='${y}' width='1.02' height='1.02'/>`;
    }
  }
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 ${cols} ${rows}' preserveAspectRatio='none' shape-rendering='crispEdges'>${rects}</svg>`;
  const mask = `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
  return <AbsoluteFill style={{ WebkitMaskImage: mask, maskImage: mask, WebkitMaskSize: "100% 100%", maskSize: "100% 100%" }}>{children}</AbsoluteFill>;
};

export const pixelWipe = () => ({ component: PixelWipe, props: {} as Record<string, never> });

// Types one character per frame step, for the proposal text and terminal lines.
export const Typed: React.FC<{ text: string; start?: number; cps?: number; style?: React.CSSProperties; render?: (s: string) => React.ReactNode }> = ({
  text, start = 0, cps = 60, style, render,
}) => {
  const frame = useCurrentFrame();
  const n = Math.floor(interpolate(frame, [start, start + (text.length / cps) * 30], [0, text.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const shown = text.slice(0, n);
  return <span style={style}>{render ? render(shown) : shown}</span>;
};

// A bracketed index label, the hackathon page's section marker.
export const Idx: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = C.deep }) => (
  <div style={{ fontSize: 26, fontWeight: 500, color, marginBottom: 18 }}>[ {children} ]</div>
);
