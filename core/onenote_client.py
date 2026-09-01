"""Thin wrapper over the Microsoft Graph OneNote endpoints this project uses.

Only the calls the label-history pull needs: listing pages in a section and
fetching one page's HTML content. Everything goes through /me/onenote/... -
the /onenote/... form (without /me/) 404s, per prior testing.

OneNote's Graph endpoints throttle noticeably harder than most Graph APIs -
a full pull (one content call per page, ~250+ pages) trips a 429 well before
that many requests if they're fired back to back, and the cooldown after
hitting one runs well past a handful of seconds. MIN_INTERVAL paces requests
proactively so a full run doesn't rely on hitting the limit and backing off;
_get_with_retry is still there as a safety net for whatever that doesn't
prevent.
"""
import time

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RETRIES = 3
MIN_INTERVAL = 2.0  # seconds between requests, paced proactively - see module docstring

_last_request_at = 0.0


class PullAborted(Exception):
    """Base for errors that should stop the whole pull rather than skip one
    page - see the subclasses below for what each specifically means.
    """


class RateLimited(PullAborted):
    """Raised when a request is still getting 429s after MAX_RETRIES.

    Deliberately not retried further here: OneNote's throttling cooldown
    runs well past what's reasonable to sit in a per-request retry loop for
    (observed several minutes of sustained 429s in practice), and repeatedly
    hammering it while already throttled risks a harsher/longer penalty (a
    run that did exactly that also got a 401 partway through - plausibly the
    token being pulled as an abuse response). Callers should stop the whole
    run on this, not just skip the one request, and only retry after a real
    cooldown.
    """


class TokenRevoked(PullAborted):
    """Raised on a 401 from Graph.

    MSAL's local token cache only tracks a token's claimed expiry, not that
    Graph has separately revoked it server-side - acquire_token_silent keeps
    handing back the same bad token otherwise (observed once, right after
    sustained 429s - plausibly an abuse-prevention response). Callers should
    get a fresh token with force_refresh=True (see
    onenote_auth.get_access_token) before retrying, not just retry with the
    same one.
    """


def _headers(access_token):
    return {"Authorization": f"Bearer {access_token}"}


def _throttle():
    global _last_request_at
    wait = MIN_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _get_with_retry(url, headers, params=None):
    """GET with proactive pacing (_throttle) plus a short retry/backoff on
    429 for a brief, one-off throttle. Honors the Retry-After header when
    present, otherwise backs off 2**attempt seconds. Raises RateLimited
    (rather than retrying further) if still 429 after MAX_RETRIES, or
    TokenRevoked immediately on a 401 - see their docstrings for why neither
    is "just retry more".
    """
    for attempt in range(MAX_RETRIES):
        _throttle()
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 401:
            raise TokenRevoked(f"401 Unauthorized: {url}")
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        wait = int(resp.headers.get("Retry-After", 2 ** attempt))
        print(f"  rate limited (429), waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})", flush=True)
        time.sleep(wait)
    raise RateLimited(f"still getting 429s after {MAX_RETRIES} attempts: {url}")


def list_section_pages(access_token, section_id, page_size=100):
    """Yield every page {id, title, createdDateTime} in a section, paginated.

    $top maxes out at 100 on this endpoint (confirmed by testing), so larger
    sections are paged via the @odata.nextLink Graph returns.
    """
    url = f"{GRAPH_BASE}/me/onenote/sections/{section_id}/pages"
    params = {"$top": page_size, "$select": "id,title,createdDateTime"}

    while url:
        resp = _get_with_retry(url, _headers(access_token), params)
        data = resp.json()
        for page in data.get("value", []):
            yield page
        url = data.get("@odata.nextLink")
        params = None  # nextLink already includes the query string


def get_page_content(access_token, page_id):
    """Return the raw HTML content of one OneNote page."""
    url = f"{GRAPH_BASE}/me/onenote/pages/{page_id}/content"
    resp = _get_with_retry(url, _headers(access_token))
    return resp.text
