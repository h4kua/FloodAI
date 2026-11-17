import { test } from "node:test";
import assert from "node:assert/strict";

import { buildStatusDesc, byPostSeverity, dailyTopKecamatan, formatChance, groupStationsByWilayah, postClass, postRiskLevel, proneAreaChances } from "./dashboardHelpers.js";

test("a post's level follows the band DSDA reports, not its ratio", () => {
  // 76% of Siaga 1 used to read "Siaga 2"; DSDA puts this post in Siaga 3.
  assert.equal(postRiskLevel({ ratio: 0.76, status_siaga: "Status : Siaga 3" }), "WASPADA");
  assert.equal(postRiskLevel({ ratio: 0.7, status_siaga: "Status : Siaga 2" }), "SIAGA_2");
  assert.equal(postRiskLevel({ ratio: 1.02, status_siaga: "Status : Siaga 1" }), "SIAGA_1");
  assert.equal(postRiskLevel({ ratio: 0.55, status_siaga: "Status : Normal" }), "NORMAL");
  assert.equal(postClass({ ratio: 0.55, status_siaga: "Status : Siaga 4" }), "ok");
});

test("without a band the ratio decides", () => {
  assert.equal(postRiskLevel({ ratio: 0.8 }), "SIAGA_2");
  assert.equal(postRiskLevel({ ratio: 0.3, status_siaga: "" }), "NORMAL");
});

test("worst post first: band before ratio", () => {
  const posts = [
    { nama: "high ratio, Siaga 3", ratio: 0.9, status_siaga: "Siaga 3" },
    { nama: "lower ratio, Siaga 2", ratio: 0.7, status_siaga: "Siaga 2" },
  ];
  assert.equal([...posts].sort(byPostSeverity)[0].nama, "lower ratio, Siaga 2");
  const [group] = groupStationsByWilayah(posts.map((p) => ({ ...p, wilayah_jakarta: "Jakarta Barat" })))
    .filter((g) => g.key === "Jakarta Barat");
  assert.equal(group.worst.nama, "lower ratio, Siaga 2");
  assert.equal(group.maxRatio, 0.9);
});

test("an Aman status explains a chronic post at Siaga 3 instead of calling it a warning", () => {
  const stations = [
    { nama: "P.A. Cengkareng Drain", ratio: 0.62, status_siaga: "Status : Siaga 3", chronic: true },
    { nama: "P.A. Manggarai 2", ratio: 0.6, status_siaga: "Status : Normal" },
  ];
  const id = buildStatusDesc({ level: "aman", stations }, true);
  assert.match(id, /Cengkareng Drain memang sering di Siaga 3, jadi tidak menaikkan status Jakarta/);
  assert.doesNotMatch(id, /Semua 2 pos pantau dalam batas normal|mulai tinggi/);
  const other = buildStatusDesc({ level: "aman", stations: [{ ...stations[0], chronic: false }, stations[1]] }, true);
  assert.match(other, /Air di 1 dari 2 pos pantau mulai tinggi/);
});

test("the daily model card lists the highest chances first", () => {
  const daily = { kecamatan: {
    a: { name: "Cakung", probability: 0.02, risk_level: "SAFE" },
    b: { name: "Kebon Jeruk", probability: 0.14, risk_level: "WARNING" },
    c: { name: "Tebet", probability: 0.004, risk_level: "SAFE" },
  } };
  const top = dailyTopKecamatan(daily, 2);
  assert.deepEqual(top.map((k) => k.name), ["Kebon Jeruk", "Cakung"]);
  assert.equal(top[0].level, "siaga");
  assert.deepEqual(dailyTopKecamatan(null), []);
  assert.equal(formatChance(0.004), "<1%");
  assert.equal(formatChance(0.137), "14%");
  assert.equal(formatChance(0), "0%");
});

test("a Waspada raised by the daily model says why", () => {
  const dailyModel = { city_level: "PRE_ALERT", kecamatan: {
    jatinegara: { name: "Jatinegara", probability: 0.17, risk_level: "PRE_ALERT" },
    tebet: { name: "Tebet", probability: 0.05, risk_level: "SAFE" },
  } };
  const text = buildStatusDesc({ level: "waspada", dailyModel }, true);
  assert.match(text, /Hujan beberapa hari terakhir/);
  assert.match(text, /17% di Kec\. Jatinegara/);
  const quiet = buildStatusDesc({ level: "waspada", dailyModel: { ...dailyModel, city_level: "SAFE" } }, true);
  assert.doesNotMatch(quiet, /Hujan beberapa hari/);
});

test("a level set by the learned decision layer leads with today's flood chance", () => {
  const decisionLayer = { decided: true, score: 0.64, push: { p: -0.2, w_max_now: 0.9 } };
  const siaga = buildStatusDesc({ level: "siaga", waterLevelRatio: 0.3, decisionLayer }, true);
  assert.match(siaga, /^Peluang banjir hari ini 64%\./);
  assert.doesNotMatch(siaga, /Air sudah 30%/);
  const dailyModel = { city_level: "PRE_ALERT", kecamatan: { a: { name: "Tebet", probability: 0.2, risk_level: "PRE_ALERT" } } };
  const waspada = buildStatusDesc({ level: "waspada", dailyModel, decisionLayer: { ...decisionLayer, score: 0.3 } }, true);
  assert.match(waspada, /Peluang banjir hari ini 30% menurut model keputusan/);
  assert.doesNotMatch(waspada, /Hujan beberapa hari/);  // the daily chance did not raise it
  const ruled = buildStatusDesc({ level: "siaga", waterLevelRatio: 0.8, decisionLayer: { ...decisionLayer, decided: false } }, true);
  assert.match(ruled, /^Air sudah 80% dari batas siaga/);
});

test("flood-prone points carry their kecamatan's chance today, one label per kecamatan", () => {
  const points = [
    { kecamatan: "JATINEGARA", kelurahan: "BIDARA CINA", lat: -6.23, lon: 106.87 },
    { kecamatan: "JATINEGARA", kelurahan: "KAMPUNG MELAYU", lat: -6.21, lon: 106.87 },
    { kecamatan: "KEBON JERUK", kelurahan: "KEDOYA", lat: -6.18, lon: 106.76 },
    { kecamatan: "SOMEWHERE ELSE", kelurahan: "X", lat: -6.1, lon: 106.8 },
  ];
  const dailyModel = { kecamatan: {
    jatinegara: { name: "Jatinegara", probability: 0.12, risk_level: "PRE_ALERT" },
    kebonjeruk: { name: "Kebon Jeruk", probability: 0.03, risk_level: "SAFE" },
  } };
  const areas = proneAreaChances(points, dailyModel);
  assert.deepEqual(areas.map((a) => [a.name, a.points.length]), [["Jatinegara", 2], ["Kebon Jeruk", 1]]);
  assert.ok(Math.abs(areas[0].lat - -6.22) < 1e-9 && areas[0].level === "PRE_ALERT");
  assert.equal(proneAreaChances(points, null), null);
});
