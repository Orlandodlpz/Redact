/**
 * Mirrors the contracts in docs/BRIEFING.md §2 and backend/app/schemas.py.
 * If one side changes, both change: these are a shared contract, not UI types.
 */

export const DESTINATIONS = ["public", "team", "ai_assistant"] as const;
export type Destination = (typeof DESTINATIONS)[number];

export const DESTINATION_LABELS: Record<Destination, string> = {
  public: "Public post",
  team: "Team chat",
  ai_assistant: "AI assistant",
};

export const DESTINATION_BLURBS: Record<Destination, string> = {
  public: "Anyone can see it, so faces, plates and anything that locates you get masked.",
  team: "People you know, so faces and plates stay. Credentials and documents do not.",
  ai_assistant: "A model reads it, so internal data and credentials get masked.",
};

export type Category =
  | "credential"
  | "payment"
  | "government_id"
  | "personal_account"
  | "contact_info"
  | "home_location"
  | "face"
  | "license_plate"
  | "internal_data"
  | "other_sensitive"
  | "benign";

export const CATEGORY_LABELS: Record<Category, string> = {
  credential: "Credential",
  payment: "Payment",
  government_id: "Government ID",
  personal_account: "Personal account",
  contact_info: "Contact info",
  home_location: "Home location",
  face: "Face",
  license_plate: "License plate",
  internal_data: "Internal data",
  other_sensitive: "Sensitive",
  benign: "Not sensitive",
};

export type FindingSource =
  | "floor"
  | "judge"
  | "combined"
  | "extra"
  | "metadata"
  | "manual";

export const SOURCE_LABELS: Record<FindingSource, string> = {
  floor: "Always masked",
  judge: "Model",
  combined: "Two clues together",
  extra: "Model found this",
  metadata: "File metadata",
  manual: "You drew this",
};

/** Box is [x1, y1, x2, y2] in working image pixels, x2 and y2 exclusive. */
export type Box = [number, number, number, number];

export type Finding = {
  id: string;
  marks: number[];
  category: Category;
  reason: string;
  source: FindingSource;
  masked: boolean;
  locked: boolean;
  box: Box | null;
  mask_rle: string | null;
};

export type AnalyzeResponse = {
  image_id: string;
  width: number;
  height: number;
  destination: Destination;
  findings: Finding[];
  judge_status: "ok" | "failed_closed";
  prompt_version: string;
  model_ids: Record<string, string>;
  timings_ms: Record<string, number>;
  est_cost_usd: number;
};

export function isDestination(value: string): value is Destination {
  return (DESTINATIONS as readonly string[]).includes(value);
}

/**
 * Parse an AnalyzeResponse that arrived as untyped JSON, from the API or from the
 * offline fixture. Both go through here, so a contract drift between the backend and
 * these types shows up as a clear error instead of an undefined deep in a render.
 *
 * This checks shape, not trust: the text inside a reason is still untrusted input and
 * is still only ever rendered as text.
 */
export function parseAnalyzeResponse(raw: unknown): AnalyzeResponse {
  const r = asObject(raw, "response");
  const width = asInt(r.width, "width");
  const height = asInt(r.height, "height");
  const destination = String(r.destination);
  if (!isDestination(destination)) {
    throw new Error(`response has an unknown destination`);
  }
  if (!Array.isArray(r.findings)) {
    throw new Error("response has no findings list");
  }
  return {
    image_id: String(r.image_id ?? ""),
    width,
    height,
    destination,
    findings: r.findings.map(parseFinding),
    judge_status: r.judge_status === "failed_closed" ? "failed_closed" : "ok",
    prompt_version: String(r.prompt_version ?? "unset"),
    model_ids: asStringMap(r.model_ids),
    timings_ms: asNumberMap(r.timings_ms),
    est_cost_usd: Number(r.est_cost_usd ?? 0),
  };
}

function parseFinding(raw: unknown, index: number): Finding {
  const f = asObject(raw, `finding ${index}`);
  const category = String(f.category);
  const source = String(f.source);
  if (!(category in CATEGORY_LABELS)) {
    throw new Error(`finding ${index} has an unknown category`);
  }
  if (!(source in SOURCE_LABELS)) {
    throw new Error(`finding ${index} has an unknown source`);
  }
  return {
    id: String(f.id),
    marks: Array.isArray(f.marks) ? f.marks.map((m) => asInt(m, "mark")) : [],
    category: category as Category,
    reason: String(f.reason ?? ""),
    source: source as FindingSource,
    masked: Boolean(f.masked),
    locked: Boolean(f.locked),
    box: asBox(f.box, index),
    mask_rle: typeof f.mask_rle === "string" ? f.mask_rle : null,
  };
}

function asBox(raw: unknown, index: number): Box | null {
  if (raw === null || raw === undefined) return null;
  if (!Array.isArray(raw) || raw.length !== 4) {
    throw new Error(`finding ${index} has a box that is not four numbers`);
  }
  const [x1, y1, x2, y2] = raw.map((v) => asInt(v, "box value"));
  return [x1, y1, x2, y2];
}

function asObject(raw: unknown, what: string): Record<string, unknown> {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error(`${what} is not an object`);
  }
  return raw as Record<string, unknown>;
}

function asInt(raw: unknown, what: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    throw new Error(`${what} is not a number`);
  }
  return Math.round(n);
}

function asStringMap(raw: unknown): Record<string, string> {
  if (typeof raw !== "object" || raw === null) return {};
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
  );
}

function asNumberMap(raw: unknown): Record<string, number> {
  if (typeof raw !== "object" || raw === null) return {};
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>).map(([k, v]) => [k, Number(v)]),
  );
}
