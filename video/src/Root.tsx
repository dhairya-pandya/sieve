import { Composition } from "remotion";
import { Sieve } from "./Sieve";

// 75 seconds of scenes minus seven half-second pixel wipes: 71.5 seconds at 30 fps.
export const RemotionRoot: React.FC = () => (
  <Composition id="Sieve" component={Sieve} durationInFrames={2145} fps={30} width={1920} height={1080} />
);
