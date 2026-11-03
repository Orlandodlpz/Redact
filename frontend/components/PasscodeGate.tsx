"use client";

/**
 * The hosted demo's passcode field.
 *
 * Shown only when `NEXT_PUBLIC_REQUIRE_PASSCODE` is on, so local development and the
 * offline fixture need nothing. The value is held in memory for the life of the tab by
 * lib/api.ts and sent as a header. It is never written to localStorage and never put in
 * the URL, so a shared machine does not keep the key to someone else's demo and the
 * code does not end up in an access log.
 */

import { useState } from "react";
import { setPasscode } from "../lib/api.ts";

export const REQUIRED =
  (process.env.NEXT_PUBLIC_REQUIRE_PASSCODE ?? "").toLowerCase() === "on";

export default function PasscodeGate({ onReady }: { onReady: () => void }) {
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);

  if (!REQUIRED) return null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    setPasscode(value.trim());
    setSaved(true);
    onReady();
  };

  return (
    <form className="passcode" onSubmit={submit}>
      <label htmlFor="passcode">Demo passcode</label>
      <div className="row">
        <input
          id="passcode"
          type="password"
          autoComplete="off"
          value={value}
          placeholder="from the submission page"
          onChange={(e) => {
            setValue(e.target.value);
            setSaved(false);
          }}
        />
        <button type="submit" disabled={!value.trim()}>
          {saved ? "Saved" : "Use it"}
        </button>
      </div>
      <p className="note">
        Kept in this tab only, sent as a header, never written to storage or a link.
      </p>
    </form>
  );
}
