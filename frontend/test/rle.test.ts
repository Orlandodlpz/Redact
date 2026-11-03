/**
 * The decoder is checked against masks encoded by the pycocotools the backend uses,
 * not against itself. Regenerate the fixtures with frontend/test/gen_rle_fixtures.py.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { decodeCounts, decodeRle } from "../lib/rle.ts";

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
