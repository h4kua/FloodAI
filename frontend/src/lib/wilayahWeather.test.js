import { test } from "node:test";
import assert from "node:assert/strict";

import { WILAYAH, describeWeather, openMeteoUrl, parseOpenMeteo } from "./wilayahWeather.js";

test("one Open-Meteo request asks for all five kota", () => {
  const url = new URL(openMeteoUrl());
  assert.equal(url.searchParams.get("latitude").split(",").length, 5);
  assert.equal(url.searchParams.get("current"), "cloud_cover,precipitation,weather_code");
});

test("the answer is read per kota, in request order", () => {
  const data = WILAYAH.map((_, i) => ({ current: { cloud_cover: i * 20, precipitation: 0, weather_code: 3, time: "t" } }));
  const parsed = parseOpenMeteo(data);
  assert.equal(parsed.Utara.cloud, 0);
  assert.equal(parsed.Timur.cloud, 80);
  assert.deepEqual(Object.keys(parseOpenMeteo([{}])), []);
});

test("weather codes become what the map draws", () => {
  assert.equal(describeWeather({ code: 0, cloud: 5 }).kind, "clear");
  assert.equal(describeWeather({ code: 3, cloud: 98 }).text, "Berawan");
  assert.equal(describeWeather({ code: 3, cloud: 98 }, "en").text, "Cloudy");
  assert.equal(describeWeather({ code: 61, cloud: 90, rainMm: 1.2 }).text, "Hujan ringan 1,2 mm");
  assert.equal(describeWeather({ code: 61, cloud: 90 }).kind, "rain");
  assert.equal(describeWeather({ code: 95, cloud: 100 }).kind, "heavy");
  assert.equal(describeWeather(undefined), null);
});
