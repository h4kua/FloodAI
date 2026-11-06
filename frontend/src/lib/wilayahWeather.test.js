import { test } from "node:test";
import assert from "node:assert/strict";

import { WILAYAH, cloudDrift, describeWeather, openMeteoUrl, parseOpenMeteo, weatherKind } from "./wilayahWeather.js";

test("one Open-Meteo request asks for all five kota", () => {
  const url = new URL(openMeteoUrl());
  assert.equal(url.searchParams.get("latitude").split(",").length, 5);
  assert.match(url.searchParams.get("current"), /weather_code/);
  assert.match(url.searchParams.get("current"), /wind_direction_10m/);
});

test("the answer is read per kota, in request order", () => {
  const data = WILAYAH.map((_, i) => ({ current: { cloud_cover: i * 20, precipitation: 0, weather_code: 3, temperature_2m: 30 + i, is_day: 0 } }));
  const parsed = parseOpenMeteo(data);
  assert.equal(parsed.Utara.cloud, 0);
  assert.equal(parsed.Timur.cloud, 80);
  assert.equal(parsed.Timur.tempC, 34);
  assert.equal(parsed.Utara.isDay, false);
  assert.deepEqual(Object.keys(parseOpenMeteo([{}])), []);
});

test("all eight weather states come from the WMO code and cloud cover", () => {
  assert.equal(weatherKind({ code: 0, cloud: 5 }), "clear");
  assert.equal(weatherKind({ code: 1, cloud: 40 }), "partly");
  assert.equal(weatherKind({ code: 3, cloud: 98 }), "cloudy");
  assert.equal(weatherKind({ code: 45, cloud: 100 }), "fog");
  assert.equal(weatherKind({ code: 53, cloud: 90 }), "drizzle");
  assert.equal(weatherKind({ code: 63, cloud: 90 }), "rain");
  assert.equal(weatherKind({ code: 65, cloud: 100 }), "heavy");
  assert.equal(weatherKind({ code: 95, cloud: 100 }), "storm");
});

test("labels say the state, the rain and the temperature", () => {
  assert.equal(describeWeather({ code: 3, cloud: 98 }).text, "Berawan");
  assert.equal(describeWeather({ code: 3, cloud: 98 }, "en").text, "Cloudy");
  assert.equal(describeWeather({ code: 61, cloud: 90, rainMm: 1.2 }).text, "Hujan 1,2 mm");
  assert.equal(describeWeather({ code: 0, cloud: 0, rainMm: 0.3 }).text, "Cerah");  // no rain shown when it is not raining
  assert.equal(describeWeather({ code: 0, cloud: 0, tempC: 31.6 }).temp, "32°");
  assert.equal(describeWeather(undefined), null);
});

test("clouds drift where the wind blows to, slowly", () => {
  // Wind from the north-north-west (341°) blows to the south: down the screen.
  assert.deepEqual(cloudDrift([{ windFrom: 341, windKmh: 11 }]), { dx: 0, dy: 1, seconds: 83 });
  // From the west → to the east.
  assert.equal(cloudDrift([{ windFrom: 270, windKmh: 0 }]).dx, 1);
  assert.equal(cloudDrift([{ windFrom: 270, windKmh: 60 }]).seconds, 35);
  assert.deepEqual(cloudDrift([]), { dx: 1, dy: 0, seconds: 80 });
});
