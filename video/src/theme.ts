import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";
import { loadFont as loadPixel } from "@remotion/google-fonts/PixelifySans";

// The NEAR Hackathon palette, the same tokens as the Sieve page.
export const C = {
  paper: "#E7DFCA",
  card: "#EEE7D6",
  ink: "#322E25",
  soft: "#655D4F",
  line: "#B7AC94",
  grid: "#DCD2BA",
  blue: "#0091FD",
  deep: "#005FB0",
  sky: "#83DCFF",
  fail: "#B53124",
  onBlue: "#FFF7E9",
  night: "#161A15",
};

export const mono = loadMono("normal", { weights: ["400", "500", "600"], subsets: ["latin"] }).fontFamily;
export const pixel = loadPixel("normal", { weights: ["500"], subsets: ["latin"] }).fontFamily;
export const head = '"Arial Black", "Helvetica Neue", Arial, sans-serif';
