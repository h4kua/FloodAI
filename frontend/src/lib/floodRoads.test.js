import { test } from "node:test";
import assert from "node:assert/strict";

import {
  activeFloodPoints,
  distanceToSegmentM,
  riversForPost,
  riversOnAlert,
  safestRouteIndex,
  splitRouteByRisk,
} from "./floodRoads.js";

const ANGKE_POINT = { kelurahan: "KAPUK", lat: -6.14, lon: 106.74, rivers: ["ANGKE"] };
const CILIWUNG_POINT = { kelurahan: "BIDARA CINA", lat: -6.23, lon: 106.865, rivers: ["CILIWUNG"] };
const NO_RIVER_POINT = { kelurahan: "X", lat: -6.2, lon: 106.8, rivers: [] };
const POINTS = [ANGKE_POINT, CILIWUNG_POINT, NO_RIVER_POINT];

const post = (nama, status) => ({ nama, status_siaga: `Status : ${status}` });

test("posts map to the BPBD rivers they feed", () => {
  assert.deepEqual(riversForPost("P.A. Cengkareng Drain"), ["ANGKE", "PESANGGRAHAN & ANGKE"]);
  assert.ok(riversForPost("Bendung. Katulampa 2").includes("CILIWUNG ARAH ISTANA NEGARA"));
  assert.deepEqual(riversForPost("P.A. Hek Kramat Jati 1"), []);
});

test("only posts at Siaga put their river on alert", () => {
  const rivers = riversOnAlert([post("P.A. Cengkareng Drain", "Siaga 3"), post("P.A. Manggarai 2", "Normal")]);
  assert.ok(rivers.has("ANGKE"));
  assert.ok(!rivers.has("CILIWUNG"));
});

test("a Siaga post activates only the flood-prone points on its river", () => {
  const active = activeFloodPoints(POINTS, [post("P.A. Cengkareng Drain", "Siaga 3")], 0);
  assert.deepEqual(active.map((p) => p.kelurahan), ["KAPUK"]);
});

test("heavy rain activates every flood-prone point", () => {
  assert.equal(activeFloodPoints(POINTS, [], 25).length, POINTS.length);
});

test("nothing is active when posts are normal and it is dry", () => {
  assert.equal(activeFloodPoints(POINTS, [post("P.A. Manggarai 2", "Normal")], 2).length, 0);
});

test("distance to a segment is measured to its nearest point", () => {
  // ~0.0045° of latitude ≈ 500 m north of a west–east segment.
  const d = distanceToSegmentM([-6.1955, 106.8], [-6.2, 106.79], [-6.2, 106.81]);
  assert.ok(Math.abs(d - 501) < 5, d);
});

test("a route is split into risky and safe runs around an active point", () => {
  const route = [[-6.14, 106.70], [-6.14, 106.72], [-6.14, 106.74], [-6.14, 106.76], [-6.14, 106.78]];
  const { runs, riskyM, totalM, pointsHit } = splitRouteByRisk(route, [ANGKE_POINT]);
  assert.deepEqual(runs.map((r) => r.risky), [false, true, false]);
  assert.ok(riskyM > 3500 && riskyM < 5000, riskyM);
  assert.ok(totalM > 8500);
  assert.equal(pointsHit.length, 1);
});

test("the safest alternative wins; near-ties go to the faster one", () => {
  assert.equal(safestRouteIndex([{ riskyM: 1200, duration: 600 }, { riskyM: 0, duration: 900 }]), 1);
  assert.equal(safestRouteIndex([{ riskyM: 50, duration: 600 }, { riskyM: 0, duration: 900 }]), 0);
  assert.equal(safestRouteIndex([]), -1);
});
