/**
 * The only two calls this app makes.
 *
 * Both are POST with a multipart body. Nothing about an image or a finding ever goes
 * into a URL, a query string or a header, because those end up in access logs at every
 * hop even when request body logging is off.
 *
 * The server stores nothing between the two calls, which is why export re sends the
 * same file the user picked rather than naming an id.
 */

import { parseAnalyzeResponse } from "./types.ts";
import type { AnalyzeResponse, Destination, Finding } from "./types.ts";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export async function analyze(
  image: File,
  destination: Destination,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  const body = new FormData();
  body.append("image", image);
  body.append("destination", destination);
  const response = await fetch(`${API_BASE}/analyze`, { method: "POST", body, signal });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  // Parsed, not cast: a contract drift between the API and the UI should be a
  // clear error here, not an undefined somewhere in a render.
  return parseAnalyzeResponse(await response.json());
}

export async function exportImage(image: File, findings: Finding[]): Promise<Blob> {
  const body = new FormData();
  body.append("image", image);
  body.append("findings", JSON.stringify(findings));
  const response = await fetch(`${API_BASE}/export`, { method: "POST", body });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return await response.blob();
}

/**
 * Error text is shown as text, never as markup. It comes from our own API, but the
 * rule is the same everywhere in this app: nothing from a response is ever HTML.
 */
async function errorMessage(response: Response): Promise<string> {
  const fallback =
    response.status >= 500
      ? "The service had a problem. Try again in a moment."
      : "That request was refused.";
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" && body.detail ? body.detail : fallback;
  } catch {
    return fallback;
  }
}
