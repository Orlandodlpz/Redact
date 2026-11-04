/**
 * COCO compressed RLE, decoded in the browser.
 *
 * The API sends `mask_rle` as the counts string only (gotcha 36), for a mask the size
 * of the whole working image, so the width and height come from the AnalyzeResponse
 * rather than from the string. Runs are column major, the way pycocotools writes them,
 * and alternate starting with background.
 *
 * The counts string is pycocotools' own variable length integer format: five payload
 * bits per character, bit 0x20 says another character follows, bit 0x10 on the last
 * character means the value is negative, and every character is offset by 48 so the
 * whole thing stays printable. Values after the first two are deltas against the count
 * two places back.
 */

export function decodeCounts(counts: string): number[] {
  const out: number[] = [];
  let p = 0;
  while (p < counts.length) {
    let x = 0;
    let k = 0;
    let more = true;
    while (more) {
      const c = counts.charCodeAt(p) - 48;
      x |= (c & 0x1f) << (5 * k);
      more = (c & 0x20) !== 0;
      p += 1;
      k += 1;
      if (!more && (c & 0x10) !== 0) {
        x |= -1 << (5 * k);
      }
    }
    if (out.length > 2) {
      x += out[out.length - 2];
    }
    out.push(x);
  }
  return out;
}

/**
 * Returns one byte per pixel, row major, 1 inside the mask. Row major because that is
 * what canvas ImageData wants; the runs themselves are column major.
 *
 * Use this for one mask. For a whole finding list use `orRleInto`, which writes into a
 * buffer you already have: a text dense photo can carry a hundred masks (gotcha 38),
 * and a hundred separate arrays at 2048 by 1536 is over 300 MB, which is a crashed tab
 * on a phone. One shared buffer is 3 MB.
 */
export function decodeRle(counts: string, width: number, height: number): Uint8Array {
  const mask = new Uint8Array(width * height);
  orRleInto(mask, counts, width, height);
  return mask;
}

/** Sets every pixel of this mask to 1 in `target`, leaving the rest alone. */
export function orRleInto(
  target: Uint8Array,
  counts: string,
  width: number,
  height: number,
): void {
  const runs = decodeCounts(counts);
  const total = width * height;
  let at = 0;
  let value = 0;
  for (const run of runs) {
    if (value === 1) {
      const end = Math.min(at + run, total);
      for (let i = at; i < end; i += 1) {
        // i walks down a column, so turn it back into a row major offset.
        const x = (i / height) | 0;
        const y = i % height;
        target[y * width + x] = 1;
      }
    }
    at += run;
    value = value === 1 ? 0 : 1;
    if (at >= total) break;
  }
}
