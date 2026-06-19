import React from "react";
import { AbsoluteFill, Sequence, Audio, useCurrentFrame, staticFile } from "remotion";
import { IntroScene }           from "./scenes/Intro";
import { DeviceShowcaseScene }  from "./scenes/DeviceShowcase";
import { DashboardScene }       from "./scenes/Dashboard";
import { ChatScene }            from "./scenes/Chat";
import { EvacScene }            from "./scenes/Evac";
import { OutroScene }           from "./scenes/Outro";
import { NarrationOverlay }     from "./components/Narration";
import { FilmGrain }            from "./components/FX";
import { SceneProgress }        from "./components/SceneProgress";

/**
 * deFlood.ai Product Demo — 21 seconds @ 30fps = 630 frames
 *
 * Frame map:
 *   0   –  89  → Intro           ( 3s,  90f)
 *   90  – 164  → Device Showcase ( 2.5s, 75f)
 *  165  – 284  → Dashboard       ( 4s, 120f)
 *  285  – 374  → Chat            ( 3s,  90f)
 *  375  – 449  → Evac            ( 2.5s, 75f)
 *  450  – 629  → Outro           ( 6s, 180f)
 */
function GlobalOverlays() {
  const frame = useCurrentFrame();
  return (
    <>
      <SceneProgress frame={frame} />
      <NarrationOverlay frame={frame} />
      <FilmGrain frame={frame} opacity={0.045} />
    </>
  );
}

export function MockupVideo() {
  return (
    <AbsoluteFill style={{ background: "#040710" }}>

      {/* Background music */}
      <Audio src={staticFile("bgmusic.mp3")} volume={0.40} startFrom={0} />

      {/* Scene 1 – Intro */}
      <Sequence from={0} durationInFrames={90} name="Intro">
        <IntroScene />
      </Sequence>

      {/* Scene 2 – Device Showcase */}
      <Sequence from={90} durationInFrames={75} name="DeviceShowcase">
        <DeviceShowcaseScene />
      </Sequence>

      {/* Scene 3 – Dashboard */}
      <Sequence from={165} durationInFrames={120} name="Dashboard">
        <DashboardScene />
      </Sequence>

      {/* Scene 4 – Chat */}
      <Sequence from={285} durationInFrames={90} name="Chat">
        <ChatScene />
      </Sequence>

      {/* Scene 5 – Evac */}
      <Sequence from={375} durationInFrames={75} name="Evac">
        <EvacScene />
      </Sequence>

      {/* Scene 6 – Outro */}
      <Sequence from={450} durationInFrames={180} name="Outro">
        <OutroScene />
      </Sequence>

      {/* Global narration subtitles + chapter rail + film grain */}
      <GlobalOverlays />

    </AbsoluteFill>
  );
}
