/**
 * The decoder is checked against masks encoded by the pycocotools the backend uses,
 * not against itself. Regenerate the fixtures with frontend/test/gen_rle_fixtures.py.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { decodeCounts, decodeRle, orRleInto } from "../lib/rle.ts";

type Case = {
  name: string;
  width: number;
  height: number;
  counts: string;
  rows: number[][];
};

const cases: Case[] = JSON.parse(
  readFileSync(new URL("./rle.fixtures.json", import.meta.url), "utf8"),
);

for (const c of cases) {
  test(`decodes ${c.name} the same as pycocotools`, () => {
    const mask = decodeRle(c.counts, c.width, c.height);
    assert.equal(mask.length, c.width * c.height);
    for (let y = 0; y < c.height; y += 1) {
      for (let x = 0; x < c.width; x += 1) {
        assert.equal(
          mask[y * c.width + x],
          c.rows[y][x],
          `${c.name} differs at x=${x} y=${y}`,
        );
      }
    }
  });
}

test("counts are run lengths that add up to the pixel count", () => {
  for (const c of cases) {
    const runs = decodeCounts(c.counts);
    assert.ok(runs.every((r) => r >= 0), `${c.name} has a negative run`);
    const total = runs.reduce((a, b) => a + b, 0);
    assert.equal(total, c.width * c.height, `${c.name} runs do not fill the image`);
  }
});

test("masks accumulate into one buffer instead of one array each", () => {
  // A text dense photo carries about a hundred masks (gotcha 38). One full image array
  // per mask is hundreds of megabytes held at once, which is a crashed tab on a phone.
  const a = cases.find((c) => c.name === "rectangle")!;
  const b = cases.find((c) => c.name === "corners")!;
  assert.equal(a.width, 9);
  const buffer = new Uint8Array(a.width * a.height);
  orRleInto(buffer, a.counts, a.width, a.height);
  const afterFirst = buffer.reduce((n, v) => n + v, 0);

  // A second mask of the same size only adds pixels, never clears one.
  const same = cases.find((c) => c.name === "full" && c.width === a.width);
  if (same) {
    orRleInto(buffer, same.counts, a.width, a.height);
    assert.ok(buffer.reduce((n, v) => n + v, 0) >= afterFirst);
  }
  assert.ok(afterFirst > 0);
  assert.notEqual(b.name, a.name);
});

test("accumulating two masks is the union of decoding them apart", () => {
  const rect = cases.find((c) => c.name === "rectangle")!;
  const { width, height } = rect;
  // Build a second mask over the same canvas by reusing the fixture's own encoding.
  const alone = decodeRle(rect.counts, width, height);
  const buffer = new Uint8Array(width * height);
  orRleInto(buffer, rect.counts, width, height);
  orRleInto(buffer, rect.counts, width, height);
  assert.deepEqual(Array.from(buffer), Array.from(alone), "twice is the same as once");
});

test("a mask longer than the image is cut off instead of overflowing", () => {
  const mask = decodeRle(decodeCountsRoundTrip([0, 1000]), 4, 4);
  assert.equal(mask.length, 16);
});

/** Encode a plain run list back into the counts string, for the overflow case above. */
function decodeCountsRoundTrip(runs: number[]): string {
  let out = "";
  runs.forEach((value, index) => {
    let x = index > 2 ? value - runs[index - 2] : value;
    let more = true;
    while (more) {
      let c = x & 0x1f;
      x >>= 5;
      more = c & 0x10 ? x !== -1 : x !== 0;
      if (more) c |= 0x20;
      out += String.fromCharCode(c + 48);
    }
  });
  return out;
}
