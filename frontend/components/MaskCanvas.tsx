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
import { decodeRle } from "../lib/rle.ts";
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

  // Decoding a full image RLE is the expensive part, so each one is decoded once and
  // kept until its finding changes. Toggling a mask then costs a repaint, not a decode.
  const decoded = useMemo(() => {
    const out = new Map<string, Uint8Array>();
    for (const f of findings) {
      if (f.mask_rle) {
        try {
          out.set(f.id, decodeRle(f.mask_rle, width, height));
        } catch {
          // A mask that will not decode falls back to its box below.
        }
      }
    }
    return out;
  }, [findings, width, height]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img || !ready) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0, width, height);

    const masked = findings.filter((f) => f.masked && f.box);
    const pixelMasks = masked.filter((f) => decoded.has(f.id));
    if (pixelMasks.length > 0) {
      const frame = ctx.getImageData(0, 0, width, height);
      for (const f of pixelMasks) {
        const mask = decoded.get(f.id)!;
        for (let i = 0; i < mask.length; i += 1) {
          if (mask[i] === 1) {
            const p = i * 4;
            frame.data[p] = 0;
            frame.data[p + 1] = 0;
            frame.data[p + 2] = 0;
          }
        }
      }
      ctx.putImageData(frame, 0, 0);
    }
    for (const f of masked) {
      if (!decoded.has(f.id)) {
        const [x1, y1, x2, y2] = f.box!;
        ctx.fillStyle = "#000";
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
      }
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
  }, [ready, findings, decoded, width, height, selectedId, preview]);

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
