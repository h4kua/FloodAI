import React from "react";
import { Composition } from "remotion";
import { MockupVideo }          from "./MockupVideo";
import { IntroScene }           from "./scenes/Intro";
import { DeviceShowcaseScene }  from "./scenes/DeviceShowcase";
import { DashboardScene }       from "./scenes/Dashboard";
import { ChatScene }            from "./scenes/Chat";
import { EvacScene }            from "./scenes/Evac";
import { OutroScene }           from "./scenes/Outro";

export const RemotionRoot = () => (
  <>
    {/* Full 21-second product demo */}
    <Composition
      id="MockupVideo"
      component={MockupVideo}
      durationInFrames={630}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{}}
    />

    {/* Individual scene previews */}
    <Composition id="Scene01-Intro"          component={IntroScene}          durationInFrames={90}  fps={30} width={1920} height={1080} defaultProps={{}} />
    <Composition id="Scene02-DeviceShowcase" component={DeviceShowcaseScene} durationInFrames={75}  fps={30} width={1920} height={1080} defaultProps={{}} />
    <Composition id="Scene03-Dashboard"      component={DashboardScene}      durationInFrames={120} fps={30} width={1920} height={1080} defaultProps={{}} />
    <Composition id="Scene04-Chat"           component={ChatScene}           durationInFrames={90}  fps={30} width={1920} height={1080} defaultProps={{}} />
    <Composition id="Scene05-Evac"           component={EvacScene}           durationInFrames={75}  fps={30} width={1920} height={1080} defaultProps={{}} />
    <Composition id="Scene06-Outro"          component={OutroScene}          durationInFrames={180} fps={30} width={1920} height={1080} defaultProps={{}} />
  </>
);
