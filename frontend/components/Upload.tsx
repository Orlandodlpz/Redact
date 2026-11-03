"use client";

/**
 * Picking a file. The File object stays in React state and in the two POST bodies.
 * It is never written to localStorage, never put in a URL, and never sent anywhere
 * except this app's own API.
 */

import { useRef, useState } from "react";

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/heic,image/heif,image/webp,.heic,.heif";

type Props = {
  file: File | null;
  onPick: (file: File) => void;
  onProblem: (message: string) => void;
  disabled?: boolean;
};

export default function Upload({ file, onPick, onProblem, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const take = (picked: File | undefined) => {
    if (!picked) return;
    if (picked.size > MAX_UPLOAD_BYTES) {
      onProblem(`${picked.name} is larger than 20 MB.`);
      return;
    }
    if (picked.size === 0) {
      onProblem(`${picked.name} is empty.`);
      return;
    }
    onPick(picked);
  };

  return (
    <div
      className={`upload${over ? " upload-over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) take(e.dataTransfer.files[0]);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="visually-hidden"
        disabled={disabled}
        onChange={(e) => {
          take(e.target.files?.[0]);
          // Clear it so picking the same file twice still fires a change.
          e.target.value = "";
        }}
      />
      <button type="button" disabled={disabled} onClick={() => inputRef.current?.click()}>
        {file ? "Choose a different image" : "Choose an image"}
      </button>
      <p className="upload-hint">
        {file ? `${file.name}, ${readableSize(file.size)}` : "or drop one here. JPEG, PNG, HEIC or WebP, up to 20 MB."}
      </p>
    </div>
  );
}

function readableSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
