"use client";

/**
 * The review list: one row per finding, with its one line reason.
 *
 * Reasons and any text the pipeline read out of the image are rendered as text. React
 * escapes them, and nothing here uses dangerouslySetInnerHTML, because text inside an
 * image is untrusted input (gotcha 12): a sticky note saying `<img onerror=...>` is a
 * string to print, never markup to run.
 *
 * A locked finding is a floor rule hit. The model cannot clear it, so the lock asks for
 * a second, explicit click before it comes off.
 */

import { useState } from "react";
import {
  CATEGORY_LABELS,
  SOURCE_LABELS,
  type Finding,
} from "../lib/types.ts";

type Props = {
  findings: Finding[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onToggle: (id: string, masked: boolean) => void;
  onRemove: (id: string) => void;
};

export default function FindingsList({
  findings,
  selectedId,
  onSelect,
  onToggle,
  onRemove,
}: Props) {
  const [confirming, setConfirming] = useState<string | null>(null);

  if (findings.length === 0) {
    return <p className="empty">Nothing to mask for this destination.</p>;
  }

  return (
    <ul className="findings">
      {findings.map((f) => {
        const needsConfirm = confirming === f.id;
        return (
          <li
            key={f.id}
            className={`finding${f.id === selectedId ? " finding-selected" : ""}${
              f.masked ? "" : " finding-kept"
            }`}
            onMouseEnter={() => onSelect(f.id)}
            onMouseLeave={() => onSelect(null)}
          >
            <div className="finding-head">
              <span className="finding-category">
                {f.locked ? <span aria-hidden="true">&#128274; </span> : null}
                {CATEGORY_LABELS[f.category]}
              </span>
              <span className="finding-source">{SOURCE_LABELS[f.source]}</span>
            </div>
            <p className="finding-reason">{f.reason}</p>
            <div className="finding-actions">
              {f.source === "metadata" ? (
                <span className="note">Removed from the file. Nothing to unmask.</span>
              ) : needsConfirm ? (
                <>
                  <span className="note">
                    This one is always masked. Unmask it anyway?
                  </span>
                  <button
                    type="button"
                    className="danger"
                    onClick={() => {
                      onToggle(f.id, false);
                      setConfirming(null);
                    }}
                  >
                    Unmask it
                  </button>
                  <button type="button" onClick={() => setConfirming(null)}>
                    Keep it masked
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (f.masked && f.locked) {
                        setConfirming(f.id);
                        return;
                      }
                      onToggle(f.id, !f.masked);
                    }}
                  >
                    {f.masked ? "Unmask" : "Mask"}
                  </button>
                  {f.source === "manual" ? (
                    <button type="button" onClick={() => onRemove(f.id)}>
                      Remove
                    </button>
                  ) : null}
                </>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
