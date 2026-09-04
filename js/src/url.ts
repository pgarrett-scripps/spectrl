/** URL / data-URI bindings for spectrl tokens. */

const MAGIC_PREFIX = "spectrl.v1.";
const DATA_URI_PREFIX = "data:application/vnd.spectrl;v=1,";

/** Wrap a token as a URL fragment: `base#token` (never sent to the server). */
export function toFragment(token: string, base: string): string {
  return `${base.split("#", 1)[0]}#${token}`
}

/** Wrap a token as a query parameter, preserving existing query params.
 * Token characters (base64url + '.') are unreserved, so they survive unescaped. */
export function toQuery(token: string, base: string, param = "d"): string {
  const url = new URL(base);
  url.searchParams.set(param, token);
  return url.toString();
}

/** Wrap a token in a `data:application/vnd.spectrl;v=1,` URI. */
export function toDataUri(token: string): string {
  return `${DATA_URI_PREFIX}${token}`;
}

/** Extract a spectrl.v1 token from a fragment, query string, or data: URI. */
export function extractToken(urlOrUri: string): string {
  if (urlOrUri.startsWith(DATA_URI_PREFIX)) return urlOrUri.slice(DATA_URI_PREFIX.length);

  let parsed: URL | null = null;
  try {
    parsed = new URL(urlOrUri);
  } catch {
    parsed = null;
  }

  if (parsed) {
    const frag = parsed.hash.replace(/^#/, "");
    if (frag.startsWith(MAGIC_PREFIX)) return frag;
    for (const v of parsed.searchParams.values()) {
      if (v.startsWith(MAGIC_PREFIX)) return v;
    }
  } else {
    const hashIdx = urlOrUri.indexOf("#");
    if (hashIdx >= 0) {
      const frag = urlOrUri.slice(hashIdx + 1);
      if (frag.startsWith(MAGIC_PREFIX)) return frag;
    }
  }
  throw new Error(`No spectrl.v1 token found in: ${JSON.stringify(urlOrUri)}`);
}
