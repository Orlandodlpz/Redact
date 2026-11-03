/**
 * The privacy line, and nothing stronger.
 *
 * Redact sends the image to the Meta Model API on the Standard tier. That tier does not
 * train on inputs, but zero data retention is not on by default: Meta may keep inputs
 * for abuse monitoring (gotcha 7). Local mode was cut on Oct 24, so there is no version
 * where the image stays on the device, and this copy must never suggest there is.
 *
 * It lives in its own module so a test can assert on it without rendering anything.
 */

export const PRIVACY_COPY =
  "not used for training by Meta, may be retained by Meta for abuse monitoring, never stored by Redact";
