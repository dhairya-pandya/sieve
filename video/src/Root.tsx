import { Composition } from "remotion";
import { Banner } from "./Banner";
import { Results, redteam, testnet } from "./Results";
import { Sieve } from "./Sieve";

// 75 seconds of scenes minus seven half-second pixel wipes: 71.5 seconds at 30 fps.
export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Sieve" component={Sieve} durationInFrames={2145} fps={30} width={1920} height={1080} />
    <Composition id="Banner" component={Banner} durationInFrames={1} fps={30} width={1800} height={600} />
    <Composition id="ResultsRedteam" component={Results} defaultProps={redteam} durationInFrames={1} fps={30} width={1800} height={600} />
    <Composition id="ResultsTestnet" component={Results} defaultProps={testnet} durationInFrames={1} fps={30} width={1800} height={600} />
  </>
);
