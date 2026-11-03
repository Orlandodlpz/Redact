/**
 * Rules about what this app says and how it says it, enforced rather than remembered.
 *
 * The privacy line is the one the team agreed to and must not drift into a bigger
 * claim. Nothing from a model or from text inside an image is ever rendered as markup.
 * And no em dashes anywhere, per the project's writing rules.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { PRIVACY_COPY } from "../lib/copy.ts";

const ROOT = path.resolve(import.meta.dirname, "..");
const SOURCE_DIRS = ["app", "components", "lib"];

function sources(): string[] {
  const out: string[] = [];
  for (const dir of SOURCE_DIRS) {
    const walk = (at: string) => {
      for (const entry of readdirSync(at)) {
        const full = path.join(at, entry);
        if (statSync(full).isDirectory()) walk(full);
        else if (/\.(ts|tsx|css|mjs)$/.test(entry)) out.push(full);
      }
    };
    walk(path.join(ROOT, dir));
  }
  return out;
}

test("the privacy line is exactly the one the team agreed to", () => {
  assert.equal(
    PRIVACY_COPY,
    "not used for training by Meta, may be retained by Meta for abuse monitoring, never stored by Redact",
  );
});

test("the privacy line never claims the image stays on the device", () => {
  const overreach = ["on your device", "on device", "locally", "never leaves", "offline"];
  for (const phrase of overreach) {
    assert.ok(
      !PRIVACY_COPY.toLowerCase().includes(phrase),
      `the privacy line must not say "${phrase}": local mode was cut on Oct 24`,
    );
  }
});

/** Comments explain these rules, so only real code is scanned for breaking them. */
function withoutComments(body: string): string {
  return body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

test("nothing is rendered as HTML", () => {
  for (const file of sources()) {
    const code = withoutComments(readFileSync(file, "utf8"));
    assert.ok(
      !code.includes("dangerouslySetInnerHTML"),
      `${path.relative(ROOT, file)} renders markup; text read out of an image is data, never HTML`,
    );
    assert.ok(
      !code.includes("innerHTML"),
      `${path.relative(ROOT, file)} assigns innerHTML; use text instead`,
    );
  }
});

test("no image or finding ever goes into a URL", () => {
  const api = withoutComments(readFileSync(path.join(ROOT, "lib", "api.ts"), "utf8"));
  // Both calls are POST with a FormData body. A query string would put a filename or a
  // reason into every access log between the browser and the server.
  assert.ok(!api.includes("URLSearchParams"), "api.ts builds a query string");
  assert.equal((api.match(/method: "POST"/g) ?? []).length, 2);
});

test("no em dashes in anything this app shows", () => {
  for (const file of sources()) {
    const body = readFileSync(file, "utf8");
    assert.ok(!body.includes("\u2014"), `${path.relative(ROOT, file)} has an em dash`);
    assert.ok(!body.includes("\u2013"), `${path.relative(ROOT, file)} has an en dash`);
  }
});
