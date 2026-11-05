import { test } from "node:test";
import assert from "node:assert/strict";

import {
  activeFloodPoints,
  areasByPost,
  postKey,
  riverForPost,
  distanceToSegmentM,
  googleMapsUrl,
  inFloodArea,
  rankSheltersByFlood,
  riversForPost,
  riskyOnlyAtEnds,
  riversOnAlert,
  safestRouteIndex,
  splitRouteByRisk,
} from "./floodRoads.js";

test("risk only at the ends of a route is flagged as unavoidable", () => {
  const run = (risky) => ({ risky, positions: [] });
  assert.equal(riskyOnlyAtEnds([run(true), run(false), run(true)]), true);
  assert.equal(riskyOnlyAtEnds([run(false), run(true)]), true);
  assert.equal(riskyOnlyAtEnds([run(false), run(true), run(false)]), false);
  assert.equal(riskyOnlyAtEnds([run(false)]), false);
});

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

test("each active area names the posts that activated it, once each", () => {
  const point = { kelurahan: "KEDOYA", lat: -6.17, lon: 106.76, rivers: ["ANGKE", "PESANGGRAHAN & ANGKE"] };
  const posts = [post("P.A. Cengkareng Drain", "Siaga 3"), post("P.S. Angke Hulu 1", "Siaga 2")];
  const [area] = activeFloodPoints([point], posts, 0);
  assert.deepEqual(area.causes.map((s) => s.nama), ["P.A. Cengkareng Drain", "P.S. Angke Hulu 1"]);
});

test("a Siaga post on a river BPBD does not list marks the area around itself", () => {
  const hek = { nama: "P.A. Hek Kramat Jati 1", status_siaga: "Status : Siaga 3", lat: -6.27, lon: 106.87 };
  const active = activeFloodPoints(POINTS, [hek], 0);
  assert.equal(active.length, 1);
  assert.deepEqual([active[0].reason, active[0].lat, active[0].lon], ["post", -6.27, 106.87]);
  assert.equal(active[0].causes[0].nama, "P.A. Hek Kramat Jati 1");
});

test("a Siaga post whose river has BPBD points gets no extra area", () => {
  const drain = { nama: "P.A. Cengkareng Drain", status_siaga: "Status : Siaga 3", lat: -6.13, lon: 106.73 };
  const active = activeFloodPoints(POINTS, [drain], 0);
  assert.deepEqual(active.map((p) => p.reason), ["river"]);
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

test("the Google Maps link follows the chosen route through waypoints", () => {
  const coords = Array.from({ length: 11 }, (_, i) => [-6.1 - i * 0.01, 106.7 + i * 0.01]);
  const url = new URL(googleMapsUrl({ lat: -6.1, lng: 106.7 }, { lat: -6.2, lng: 106.8 }, coords, 9));
  assert.equal(url.origin + url.pathname, "https://www.google.com/maps/dir/");
  assert.equal(url.searchParams.get("api"), "1");
  assert.equal(url.searchParams.get("origin"), "-6.10000,106.70000");
  assert.equal(url.searchParams.get("destination"), "-6.20000,106.80000");
  // Phones take at most 3 waypoints, whatever is asked for.
  assert.equal(url.searchParams.get("waypoints").split("|").length, 3);
});

test("a GPS start is left to Google's live location", () => {
  const url = new URL(googleMapsUrl({ lat: -6.1, lng: 106.7, isGPS: true }, { lat: -6.2, lng: 106.8 }, []));
  assert.equal(url.searchParams.get("origin"), null);
  assert.equal(url.searchParams.get("destination"), "-6.20000,106.80000");
});

test("a two-point route needs no waypoints", () => {
  const url = new URL(googleMapsUrl({ lat: -6.1, lng: 106.7 }, { lat: -6.2, lng: 106.8 }, [[-6.1, 106.7], [-6.2, 106.8]]));
  assert.equal(url.searchParams.get("waypoints"), null);
});

test("the safest alternative wins; near-ties go to the faster one", () => {
  assert.equal(safestRouteIndex([{ riskyM: 1200, duration: 600 }, { riskyM: 0, duration: 900 }]), 1);
  assert.equal(safestRouteIndex([{ riskyM: 50, duration: 600 }, { riskyM: 0, duration: 900 }]), 0);
  assert.equal(safestRouteIndex([]), -1);
});

test("a shelter within 500 m of an active flood point is in a flood area", () => {
  assert.equal(inFloodArea(-6.2320, 106.865, [CILIWUNG_POINT]), true);   // ~220 m away
  assert.equal(inFloodArea(-6.2400, 106.865, [CILIWUNG_POINT]), false);  // ~1.1 km away
  assert.equal(inFloodArea(-6.2320, 106.865, []), false);
});

test("shelters outside active flood areas come first, nearest first within each group", () => {
  const shelters = [
    { id: "near-river", lat: -6.2302, lng: 106.8652 },
    { id: "dry-1", lat: -6.2400, lng: 106.8650 },
    { id: "dry-2", lat: -6.2450, lng: 106.8650 },
  ];
  const ranked = rankSheltersByFlood(shelters, [CILIWUNG_POINT]);
  assert.deepEqual(ranked.map((s) => s.id), ["dry-1", "dry-2", "near-river"]);
  assert.equal(ranked[2].inFloodArea, true);
  assert.deepEqual(rankSheltersByFlood(shelters, []).map((s) => s.id), ["near-river", "dry-1", "dry-2"]);
});

test("BPBD evacuation sites within 1 km come first; flood-prone schools go last", () => {
  const shelters = [
    { id: "school-floods", lat: -6.2400, lng: 106.8650, distanceKm: 0.1, floodProneSchool: true },
    { id: "mosque", lat: -6.2410, lng: 106.8650, distanceKm: 0.2 },
    { id: "bpbd-near", lat: -6.2420, lng: 106.8650, distanceKm: 0.8, bpbdSite: { people: 204 } },
    { id: "bpbd-far", lat: -6.2500, lng: 106.8650, distanceKm: 2.4, bpbdSite: { people: 50 } },
  ];
  assert.deepEqual(rankSheltersByFlood(shelters, []).map((s) => s.id), ["bpbd-near", "mosque", "bpbd-far", "school-floods"]);
});

test("each post maps to the active areas it activates; rain-only areas map to no post", () => {
  const angke = post("P.A. Cengkareng Drain", "Siaga 3");
  const points = activeFloodPoints(POINTS, [angke], 0);
  const byPost = areasByPost(points);
  assert.deepEqual(byPost.get("P.A. Cengkareng Drain").map((p) => p.kelurahan), ["KAPUK"]);
  assert.equal(areasByPost(activeFloodPoints(POINTS, [], 30)).size, 0);
});

test("live post names find their river entry", () => {
  const table = {
    cengkarengdrain: { rivers: ["Kali Cengkareng Drain", "Kali Angke"] },
    hek: { rivers: ["Kali Baru Timur"] },
    kaliduri: { rivers: ["Kali Duri Ledeng"] },
    katulampa: { rivers: ["Kali Ciliwung"] },
  };
  assert.equal(postKey("P.A. Marina Ancol 1 (Laut)"), "marinaancol");
  assert.equal(postKey("P.S. Krukut Hulu 2"), "krukuthulu");
  assert.equal(postKey("PS. Bendung Katulampa"), "katulampa");
  assert.equal(postKey("Pompa Kali Duri (Kalijodo)"), "kaliduri");
  assert.deepEqual(riverForPost("P.A. Cengkareng Drain", table).rivers, ["Kali Cengkareng Drain", "Kali Angke"]);
  assert.deepEqual(riverForPost("P.A. Hek Kramat Jati 1", table).rivers, ["Kali Baru Timur"]);
  assert.deepEqual(riverForPost("P.A. Kaliduri 1", table).rivers, ["Kali Duri Ledeng"]);
  assert.deepEqual(riverForPost("PS. Bendung Katulampa", table).rivers, ["Kali Ciliwung"]);
  assert.equal(riverForPost("P.A. Marina Ancol 1 (Laut)", table), null);
});

test("a live post is matched to its river by place before name", () => {
  const table = {
    flusingancol: { post: "P.A. Flusing Ancol", at: [-6.12559, 106.83015], rivers: ["Kali Ancol"] },
    kampungrambutan: { post: "Kampung Rambutan (Baru)", at: [-6.3084, 106.88084], rivers: ["Kali Cipinang"] },
  };
  assert.deepEqual(riverForPost({ nama: "P.A. Ancol Flushing 1", lat: -6.1256, lon: 106.8302 }, table).rivers, ["Kali Ancol"]);
  assert.deepEqual(riverForPost({ nama: "Waduk Kampung Rambutan 1", lat: -6.3085, lon: 106.8809 }, table).rivers, ["Kali Cipinang"]);
  assert.equal(riverForPost({ nama: "Pos jauh", lat: -6.2, lon: 106.7 }, table), null);
});

test("a Siaga post only activates the flood-prone points near its drawn river stretch", () => {
  const drain = { ...post("P.A. Cengkareng Drain", "Siaga 3"), lat: -6.1537, lon: 106.748 };
  const near = { kelurahan: "KAPUK", lat: -6.131, lon: 106.746, rivers: ["ANGKE"] };
  const far = { kelurahan: "SEMANAN", lat: -6.149, lon: 106.70, rivers: ["ANGKE"] };
  const table = { cengkarengdrain: { at: [-6.1537, 106.748], rivers: ["Kali Angke"], lines: [[[-6.1537, 106.748], [-6.12, 106.746]]] } };
  assert.deepEqual(activeFloodPoints([near, far], [drain], 0, table).map((p) => p.kelurahan), ["KAPUK"]);
  // Without river lines (an upstream post off the map) the whole river still counts.
  assert.equal(activeFloodPoints([near, far], [drain], 0, {}).length, 2);
});
