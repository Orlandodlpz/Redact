import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Redact",
  description:
    "Check a photo before you share it: what is sensitive here, for whoever will see it.",
  // No crawling and no link preview of a page people paste images into.
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
