import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { useVideoConfig } from "remotion";
import { pixelWipe } from "./Pixel";
import { Close } from "./scenes/Close";
import { Contract } from "./scenes/Contract";
import { Enclaves } from "./scenes/Enclaves";
import { Milestones } from "./scenes/Milestones";
import { Problem } from "./scenes/Problem";
import { Product } from "./scenes/Product";
import { RedTeam } from "./scenes/RedTeam";
import { Title } from "./scenes/Title";

// Each pixel wipe overlaps two scenes by half a second.
const WIPE = 0.5;

export const Sieve: React.FC = () => {
  const { fps } = useVideoConfig();
  const wipe = <TransitionSeries.Transition presentation={pixelWipe()} timing={linearTiming({ durationInFrames: WIPE * fps })} />;
  return (
    <TransitionSeries>
      <TransitionSeries.Sequence name="Title" durationInFrames={5 * fps}><Title /></TransitionSeries.Sequence>
      {wipe}
      <TransitionSeries.Sequence name="Problem" durationInFrames={10 * fps}><Problem /></TransitionSeries.Sequence>
      {wipe}
      <TransitionSeries.Sequence name="Enclaves" durationInFrames={11 * fps}><Enclaves /></TransitionSeries.Sequence>
      {wipe}
      <TransitionSeries.Sequence name="Contract" durationInFrames={10 * fps}><Contract /></TransitionSeries.Sequence>
      {wipe}
      <TransitionSeries.Sequence name="Milestones" durationInFrames={11 * fps}><Milestones /></TransitionSeries.Sequence>
      {wipe}
      <TransitionSeries.Sequence name="Red-team" durationInFrames={11 * fps}><RedTeam /></TransitionSeries.Sequence>
      {wipe}
      <TransitionSeries.Sequence name="Product" durationInFrames={9 * fps}><Product /></TransitionSeries.Sequence>
      {wipe}
      <TransitionSeries.Sequence name="Close" durationInFrames={8 * fps}><Close /></TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
