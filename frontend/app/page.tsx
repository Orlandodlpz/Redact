"use client";

/**
 * The whole flow: pick an image, pick who sees it, review what Redact found, export.
 *
 * All state lives in this component for the life of the tab. There is no router state,
 * no localStorage and no query string, because an image and a finding list are the two
 * things that must never end up in a URL or a log line.
 *
 * The server keeps nothing between /analyze and /export, so the same File is sent twice.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DestinationPicker from "../components/DestinationPicker.tsx";
import FindingsList from "../components/FindingsList.tsx";
import MaskCanvas from "../components/MaskCanvas.tsx";
import PrivacyNote from "../components/PrivacyNote.tsx";
import Upload from "../components/Upload.tsx";
import { ApiError, analyze, exportImage } from "../lib/api.ts";
import type { AnalyzeResponse, Box, Destination, Finding } from "../lib/types.ts";
import { DESTINATION_LABELS, parseAnalyzeResponse } from "../lib/types.ts";
import fixture from "../fixtures/analyze.sample.json" with { type: "json" };

type Stage = "pick" | "working" | "review";

export default function Page() {
  const [stage, setStage] = useState<Stage>("pick");
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [destination, setDestination] = useState<Destination>("public");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const manualCount = useRef(0);

  // An object URL is a live handle on the file. Revoke it so a dropped image is not
  // reachable from the page any longer than it is being looked at.
  useEffect(() => {
    if (!file) {
      setImageUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const maskedCount = useMemo(() => findings.filter((f) => f.masked).length, [findings]);

  const reset = useCallback(() => {
    setStage("pick");
    setResult(null);
    setFindings([]);
    setSelectedId(null);
    setDrawing(false);
    setError(null);
    manualCount.current = 0;
  }, []);

  const onPick = (picked: File) => {
    reset();
    setFile(picked);
  };

  const run = async () => {
    if (!file) return;
    setStage("working");
    setError(null);
    try {
      const response = await analyze(file, destination);
      setResult(response);
      setFindings(response.findings);
      setStage("review");
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Couldn't reach the service. Check that the API is running.",
      );
      setStage("pick");
    }
  };

  const loadFixture = () => {
    reset();
    setFile(null);
    const sample = parseAnalyzeResponse(fixture);
    setImageUrl("/fixture.png");
    setResult(sample);
    setFindings(sample.findings);
    setDestination(sample.destination);
    setStage("review");
  };

  const onToggle = (id: string, masked: boolean) =>
    setFindings((all) => all.map((f) => (f.id === id ? { ...f, masked } : f)));

  const onRemove = (id: string) =>
    setFindings((all) => all.filter((f) => f.id !== id));

  const onDraw = (box: Box) => {
    manualCount.current += 1;
    setFindings((all) => [
      ...all,
      {
        id: `m_${manualCount.current.toString().padStart(2, "0")}`,
        marks: [],
        category: "other_sensitive",
        reason: "You drew this mask.",
        source: "manual",
        masked: true,
        locked: false,
        box,
        mask_rle: null,
      },
    ]);
  };

  const download = async () => {
    if (!file) {
      setError("The sample is for looking at. Upload an image to export one.");
      return;
    }
    setExporting(true);
    setError(null);
    try {
      const blob = await exportImage(file, findings);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "redacted.png";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The export failed. Try again.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <main>
      <header className="masthead">
        <h1>Redact</h1>
        <p className="tagline">
          Pattern tools find text that looks like personal data. Redact decides what is
          sensitive in this photo, for whoever will see it, and explains every mask.
        </p>
      </header>

      {stage !== "review" ? (
        <section className="panel">
          <Upload
            file={file}
            onPick={onPick}
            onProblem={setError}
            disabled={stage === "working"}
          />
          <DestinationPicker
            value={destination}
            onChange={setDestination}
            disabled={stage === "working"}
          />
          <div className="row">
            <button
              type="button"
              className="primary"
              disabled={!file || stage === "working"}
              onClick={run}
            >
              {stage === "working" ? "Looking at it..." : "Check this image"}
            </button>
            <button type="button" onClick={loadFixture}>
              See a sample result
            </button>
          </div>
          <PrivacyNote />
        </section>
      ) : null}

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {stage === "review" && result && imageUrl ? (
        <section className="review">
          <div className="review-image">
            <MaskCanvas
              imageUrl={imageUrl}
              width={result.width}
              height={result.height}
              findings={findings}
              selectedId={selectedId}
              drawing={drawing}
              onDraw={onDraw}
            />
            <div className="row">
              <button
                type="button"
                className={drawing ? "primary" : ""}
                onClick={() => setDrawing((on) => !on)}
              >
                {drawing ? "Done drawing" : "Draw a mask"}
              </button>
              <button
                type="button"
                className="primary"
                disabled={exporting}
                onClick={download}
              >
                {exporting ? "Building the PNG..." : "Download the masked image"}
              </button>
              <button type="button" onClick={reset}>
                Start over
              </button>
            </div>
          </div>

          <aside className="review-side">
            <h2>
              {maskedCount} of {findings.length} masked
            </h2>
            <p className="subhead">
              Going to a {DESTINATION_LABELS[result.destination].toLowerCase()}.
            </p>
            {result.judge_status === "failed_closed" ? (
              <p className="warn" role="status">
                The model was unavailable, so Redact masked everything that could matter
                instead of guessing. Expect more masks than usual.
              </p>
            ) : null}
            <FindingsList
              findings={findings}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onToggle={onToggle}
              onRemove={onRemove}
            />
            <PrivacyNote />
          </aside>
        </section>
      ) : null}
    </main>
  );
}
