"""Device-code sign-in to Microsoft Graph for read-only OneNote access.

Uses a public-client Azure app registration (no client secret - device-code
auth is interactive each time by design) with the Notes.Read delegated
permission. See memory/onenote-graph-integration for the registration
details. The acquired token is cached on disk so re-running a pull doesn't
require signing in again until the cached refresh token itself expires.
"""
import os

import msal

from core.config import CONFIG_DIR

CLIENT_ID = "56df8a93-9add-41d0-b68d-8f5b4b17a066"
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["https://graph.microsoft.com/Notes.Read"]

TOKEN_CACHE_FILE = os.path.join(CONFIG_DIR, "onenote_token_cache.json")


def _load_cache():
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache


def _save_cache(cache):
    if cache.has_state_changed:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())


def get_access_token(force_refresh=False):
    """Return a valid Graph access token, signing in interactively if needed.

    Tries the cached account silently first; falls back to a device-code
    flow (prints a URL + one-time code to sign in with in a browser) if no
    cached token is usable. Blocks until the user completes sign-in or the
    device code expires (~15 minutes).

    force_refresh skips the cached access token even if MSAL still considers
    it locally unexpired, and uses the refresh token to get a genuinely new
    one instead. Needed after a 401 from Graph itself: the local cache only
    knows an access token's claimed expiry, not that Graph has separately
    revoked it (e.g. as an abuse-prevention response to sustained 429s) -
    without this, acquire_token_silent keeps handing back the same bad token
    until its claimed expiry passes.
    """
    cache = _load_cache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0], force_refresh=force_refresh)

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to start device flow: {flow.get('error_description', flow)}")
        print(flow["message"], flush=True)
        result = app.acquire_token_by_device_flow(flow)

    _save_cache(cache)

    if "access_token" not in result:
        raise RuntimeError(f"Sign-in failed: {result.get('error_description', result)}")
    return result["access_token"]
