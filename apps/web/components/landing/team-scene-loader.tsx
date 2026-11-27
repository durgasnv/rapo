"use client";

import dynamic from "next/dynamic";

// `ssr: false` must live in a Client Component; this keeps three.js out of
// the server render and off the critical path for first paint.
const TeamScene = dynamic(() => import("./team-scene"), { ssr: false });

export function TeamSceneLoader() {
  return <TeamScene />;
}
