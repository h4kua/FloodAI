import { test } from "node:test";
import assert from "node:assert/strict";

import { byPostSeverity, groupStationsByWilayah, postClass, postRiskLevel } from "./dashboardHelpers.js";

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
