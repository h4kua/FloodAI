import { test } from "node:test";
import assert from "node:assert/strict";

import { byWilayahKey, cloudDrift, describeWeather, weatherKind } from "./wilayahWeather.js";

const ow = (over) => ({ weather_main: "Clouds", weather_desc: "awan mendung", clouds: 100, rainfall_1h: 0, temp: 34.9, weather_icon: "04d", ...over });

test("the backend's per-kota readings are keyed like the map", () => {
  const keyed = byWilayahKey({ "Jakarta Selatan": ow(), "Jakarta Utara": ow({ temp: 30 }) });
  assert.deepEqual(Object.keys(keyed).sort(), ["Selatan", "Utara"]);
  assert.equal(keyed.Utara.temp, 30);
});

test("every state comes from the OpenWeather reading", () => {
  assert.equal(weatherKind(ow({ weather_main: "Clear", clouds: 5 })), "clear");
  assert.equal(weatherKind(ow({ weather_main: "Clouds", clouds: 40 })), "partly");
  assert.equal(weatherKind(ow()), "cloudy");
  assert.equal(weatherKind(ow({ weather_main: "Haze" })), "fog");
  assert.equal(weatherKind(ow({ weather_main: "Drizzle" })), "drizzle");
  assert.equal(weatherKind(ow({ weather_main: "Rain", weather_desc: "hujan ringan", rainfall_1h: 0.1 })), "light");
  assert.equal(weatherKind(ow({ weather_main: "Rain", weather_desc: "hujan sedang", rainfall_1h: 3 })), "rain");
  assert.equal(weatherKind(ow({ weather_main: "Rain", weather_desc: "hujan", rainfall_1h: 9 })), "heavy");
  assert.equal(weatherKind(ow({ weather_main: "Thunderstorm" })), "storm");
  assert.equal(weatherKind(undefined), null);
});

test("map labels use the card's own words and units", () => {
  assert.equal(describeWeather(ow()).text, "Awan mendung");
  assert.equal(describeWeather(ow({ weather_main: "Rain", weather_desc: "hujan ringan", rainfall_1h: 0.1 })).text, "Hujan ringan · 0,1 mm/jam");
  // The backend's words are Indonesian; the English page translates them like the card does.
  assert.equal(describeWeather(ow({ weather_main: "Rain", weather_desc: "hujan ringan", rainfall_1h: 0.1 }), "en").text, "Light rain · 0.1 mm/h");
  assert.equal(describeWeather(ow(), "en").text, "Overcast");
  assert.equal(describeWeather(ow()).temp, "35°");
  assert.equal(describeWeather(ow({ weather_icon: "04n" })).isDay, false);
});

test("clouds drift where the wind blows to, slowly", () => {
  // Wind from the north-north-west (341°) blows to the south: down the screen.
  assert.deepEqual(cloudDrift([{ wind_deg: 341, wind_speed: 3 }]), { dx: 0, dy: 1, seconds: 83 });
  assert.equal(cloudDrift([{ wind_deg: 270, wind_speed: 0 }]).dx, 1);
  assert.equal(cloudDrift([{ wind_deg: 270, wind_speed: 20 }]).seconds, 35);
  assert.deepEqual(cloudDrift([]), { dx: 1, dy: 0, seconds: 80 });
});
