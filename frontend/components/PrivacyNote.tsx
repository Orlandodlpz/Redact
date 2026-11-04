import { PRIVACY_COPY } from "../lib/copy.ts";

/** The one sentence this app says about where the image goes. See lib/copy.ts. */
export default function PrivacyNote() {
  return (
    <p className="privacy">
      Your image goes to Meta's models to be read: {PRIVACY_COPY}.
    </p>
  );
}
