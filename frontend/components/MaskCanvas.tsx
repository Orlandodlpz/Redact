"use client";

/**
 * The image with its masks, at the working image size the API returned.
 *
 * Every box and mask in a finding is in the ingested image's coordinates, so the
 * canvas is that size and the browser scales it down with CSS. Drawing it at the
 * original photo's size instead would put every mask in the wrong place.
 *
 * What is painted here is a preview. The file the user downloads is composed on the
 * server by the same compose.py the eval uses, so the preview can never disagree with
 * the export about what was masked.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { orRleInto } from "../lib/rle.ts";
import type { Box, Finding } from "../lib/types.ts";

type Props = {
  imageUrl: string;
  width: number;
  height: number;
  findings: Finding[];
  selectedId: string | null;
  drawing: boolean;
  onDraw: (box: Box) => void;
};

const MIN_DRAWN_PX = 6;

export default function MaskCanvas({
  imageUrl,
  width,
  height,
  findings,
  selectedId,
  drawing,
  onDraw,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [ready, setReady] = useState(false);
  const [preview, setPreview] = useState<Box | null>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      imageRef.current = img;
      setReady(true);
    };
    img.src = imageUrl;
    return () => {
      imageRef.current = null;
      setReady(false);
    };
  }, [imageUrl]);

  // One buffer for every pixel mask, not one per finding. A text dense photo can carry
  // a hundred masks (gotcha 38) and a hundred full image arrays at 2048 by 1536 is over
  // 300 MB, which is a crashed tab on a phone. This is 3 MB and is rebuilt only when
  // the masked set changes, so hovering a finding costs a repaint, not a decode.
  const maskedKey = findings
    .filter((f) => f.masked && f.mask_rle)
    .map((f) => f.id)
    .join(",");
  const pixels = useMemo(() => {
    const masked = findings.filter((f) => f.masked && f.mask_rle);
    if (masked.length === 0) return null;
    const buffer = new Uint8Array(width * height);
    for (const f of masked) {
      try {
        orRleInto(buffer, f.mask_rle!, width, height);
      } catch {
        // A mask that will not decode falls back to its box below.
      }
    }
    return buffer;
    // findings is intentionally not a dependency: only which masks are on matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maskedKey, width, height]);

  /** A box is filled directly when its finding has no pixel mask to decode. */
  const boxOnly = useMemo(
    () => findings.filter((f) => f.masked && f.box && !f.mask_rle),
    [findings],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img || !ready) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0, width, height);

    if (pixels) {
      const frame = ctx.getImageData(0, 0, width, height);
      const data = frame.data;
      for (let i = 0; i < pixels.length; i += 1) {
        if (pixels[i] === 1) {
          const p = i * 4;
          data[p] = 0;
          data[p + 1] = 0;
          data[p + 2] = 0;
        }
      }
      ctx.putImageData(frame, 0, 0);
    }
    for (const f of boxOnly) {
      const [x1, y1, x2, y2] = f.box!;
      ctx.fillStyle = "#000";
      ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
    }

    // Outlines last, so a region is findable whether or not it is filled.
    const stroke = Math.max(2, Math.round(width / 500));
    for (const f of findings) {
      if (!f.box) continue;
      const [x1, y1, x2, y2] = f.box;
      const selected = f.id === selectedId;
      ctx.lineWidth = selected ? stroke * 2 : stroke;
      ctx.setLineDash(f.masked ? [] : [stroke * 3, stroke * 2]);
      ctx.strokeStyle = selected ? "#ffd166" : f.masked ? "#4cc9f0" : "#9aa5b1";
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    }
    ctx.setLineDash([]);

    if (preview) {
      const [x1, y1, x2, y2] = preview;
      ctx.lineWidth = stroke;
      ctx.setLineDash([stroke * 3, stroke * 2]);
      ctx.strokeStyle = "#ffd166";
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.setLineDash([]);
    }
  }, [ready, findings, pixels, boxOnly, width, height, selectedId, preview]);

  const toImage = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>): { x: number; y: number } => {
      const rect = event.currentTarget.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * width;
      const y = ((event.clientY - rect.top) / rect.height) * height;
      return {
        x: Math.min(Math.max(Math.round(x), 0), width),
        y: Math.min(Math.max(Math.round(y), 0), height),
      };
    },
    [width, height],
  );

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    startRef.current = toImage(event);
    setPreview(null);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing || !startRef.current) return;
    setPreview(rect(startRef.current, toImage(event)));
  };

  const onPointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing || !startRef.current) return;
    const box = rect(startRef.current, toImage(event));
    startRef.current = null;
    setPreview(null);
    if (box[2] - box[0] >= MIN_DRAWN_PX && box[3] - box[1] >= MIN_DRAWN_PX) {
      onDraw(box);
    }
  };

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className={`canvas${drawing ? " canvas-drawing" : ""}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      aria-label="The image with its masks"
    />
  );
}

function rect(a: { x: number; y: number }, b: { x: number; y: number }): Box {
  return [
    Math.min(a.x, b.x),
    Math.min(a.y, b.y),
    Math.max(a.x, b.x),
    Math.max(a.y, b.y),
  ];
}
