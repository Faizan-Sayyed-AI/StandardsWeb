/**
 * Decode a JWT's payload claims.
 *
 * JWTs use base64url encoding (`-`/`_`, no padding), not plain base64
 * (`+`/`/`, padded with `=`). Passing a base64url string straight to
 * `atob()` throws `InvalidCharacterError` whenever the payload segment
 * contains a `-` or `_` byte — which is common, not an edge case. This also
 * handles UTF-8 correctly: `atob()` alone yields a binary string, and
 * feeding that directly to `JSON.parse` mangles any non-ASCII characters
 * (e.g. accented names) instead of throwing.
 */
export function decodeJwtPayload<T = Record<string, unknown>>(token: string): T {
  const base64Url = token.split(".")[1];
  if (!base64Url) {
    throw new Error("Malformed JWT: missing payload segment");
  }

  const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);

  const binary = atob(padded);
  const percentEncoded = Array.from(binary)
    .map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0"))
    .join("");

  return JSON.parse(decodeURIComponent(percentEncoded));
}
