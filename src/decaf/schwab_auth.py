"""Schwab Trader API OAuth2 authentication.

Automates the authorization code grant flow:
1. Generates a self-signed TLS cert for the local callback server
2. Opens browser to Schwab's auth page
3. Captures the callback with the authorization code
4. Exchanges code for access + refresh tokens
5. Persists tokens to disk for reuse

Callback URL: https://127.0.0.1:8182
Register this EXACT URL in your Schwab developer app settings.

Access tokens expire after 30 min (auto-refreshed).
Refresh tokens expire after 7 days (requires re-login).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import ssl
import subprocess
import time
from pathlib import Path
from typing import TypedDict
from urllib.parse import unquote

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
_CALLBACK_PORT = 8182
_CALLBACK_URL = f"https://127.0.0.1:{_CALLBACK_PORT}"

# Refresh proactively 60s before expiry
_EXPIRY_BUFFER_S = 60


class _OAuthTokens(TypedDict, total=False):
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: float
    token_type: str
    scope: str


class SchwabAuth:
    """Manages Schwab OAuth2 tokens with automatic refresh."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        cache_dir: Path | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._cache_dir = cache_dir or Path.home() / ".cache" / "decaf"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._tokens_path = self._cache_dir / "schwab_tokens.json"
        self._cert_path = self._cache_dir / "schwab_localhost.pem"
        self._key_path = self._cache_dir / "schwab_localhost.key"
        self._tokens: _OAuthTokens | None = None

    @property
    def callback_url(self) -> str:
        return _CALLBACK_URL

    async def get_access_token(self, session: aiohttp.ClientSession) -> str:
        """Return a valid access token, refreshing or re-authing as needed."""
        tokens = self._load_tokens()

        if tokens:
            # Token still valid?
            if tokens.get("expires_at", 0) > time.time() + _EXPIRY_BUFFER_S:
                return tokens["access_token"]

            # Try refresh (refresh token valid for 7 days)
            refresh = tokens.get("refresh_token")
            if refresh:
                try:
                    new_tokens = await self._refresh(session, refresh)
                    self._save_tokens(new_tokens)
                    logger.info("Schwab access token refreshed")
                    return new_tokens["access_token"]
                except Exception as e:
                    logger.warning("Token refresh failed (%s) — need re-login", e)

        # Full OAuth flow
        tokens = await self._authorize(session)
        self._save_tokens(tokens)
        return tokens["access_token"]

    async def _authorize(self, session: aiohttp.ClientSession) -> _OAuthTokens:
        """Run the full OAuth2 authorization code grant flow."""
        self._ensure_cert()

        code_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

        async def handle_callback(request: web.Request) -> web.Response:
            code = request.query.get("code", "")
            if code:
                # Auth codes are URL-encoded (%40 → @)
                code_future.set_result(unquote(code))
                return web.Response(
                    text=(
                        "<html><body>"
                        "<h2>Schwab authorization successful!</h2>"
                        "<p>Return to the terminal. You can close this tab.</p>"
                        "</body></html>"
                    ),
                    content_type="text/html",
                )
            error = request.query.get("error", "unknown")
            error_desc = request.query.get("error_description", "")
            detail = f"{error}: {error_desc}" if error_desc else error
            logger.error("OAuth callback error: %s (query: %s)", detail, dict(request.query))
            code_future.set_exception(RuntimeError(f"Schwab OAuth error: {detail}"))
            return web.Response(text=f"Authorization failed: {detail}", status=400)

        # Local HTTPS server to capture the callback
        app = web.Application()
        app.router.add_get("/", handle_callback)

        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(str(self._cert_path), str(self._key_path))

        runner = web.AppRunner(app, handle_signals=False)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", _CALLBACK_PORT, ssl_context=ssl_ctx)
        await site.start()

        auth_url = (
            f"{_AUTH_URL}"
            f"?client_id={self._client_id}"
            f"&redirect_uri={_CALLBACK_URL}"
        )

        print("\nOpen this URL in your browser to authorize:\n")
        print(f"  {auth_url}\n")
        print("Waiting for callback on https://127.0.0.1:8182 ...")

        try:
            code = await asyncio.wait_for(code_future, timeout=300)
        except TimeoutError as exc:
            raise RuntimeError(
                "Timed out waiting for Schwab authorization (5 min). "
                "Make sure you completed the login in the browser."
            ) from exc
        finally:
            await runner.cleanup()

        return await self._exchange_code(session, code)

    async def _exchange_code(
        self, session: aiohttp.ClientSession, code: str,
    ) -> _OAuthTokens:
        """Exchange authorization code for access + refresh tokens."""
        async with session.post(
            _TOKEN_URL,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _CALLBACK_URL,
            },
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Schwab token exchange failed ({resp.status}): {body}"
                )
            tokens = await resp.json()

        tokens["expires_at"] = time.time() + tokens.get("expires_in", 1800)
        return tokens

    async def _refresh(
        self, session: aiohttp.ClientSession, refresh_token: str,
    ) -> _OAuthTokens:
        """Refresh the access token using the refresh token."""
        async with session.post(
            _TOKEN_URL,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Schwab token refresh failed ({resp.status}): {body}"
                )
            tokens = await resp.json()

        tokens["expires_at"] = time.time() + tokens.get("expires_in", 1800)
        return tokens

    def _basic_auth_header(self) -> str:
        """Build HTTP Basic auth header from client credentials."""
        creds = f"{self._client_id}:{self._client_secret}"
        encoded = base64.b64encode(creds.encode()).decode()
        return f"Basic {encoded}"

    def _load_tokens(self) -> _OAuthTokens | None:
        """Load cached tokens from disk."""
        if self._tokens is not None:
            return self._tokens
        if not self._tokens_path.exists():
            return None
        try:
            self._tokens = json.loads(self._tokens_path.read_text())
            return self._tokens
        except (json.JSONDecodeError, KeyError):
            return None

    def _save_tokens(self, tokens: _OAuthTokens) -> None:
        """Persist tokens to disk with restricted permissions."""
        self._tokens = tokens
        self._tokens_path.write_text(json.dumps(tokens, indent=2))
        self._tokens_path.chmod(0o600)
        logger.debug("Schwab tokens saved to %s", self._tokens_path)

    def _ensure_cert(self) -> None:
        """Generate self-signed cert for localhost callback if needed."""
        if self._cert_path.exists() and self._key_path.exists():
            return

        logger.info("Generating self-signed certificate for Schwab callback...")
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(self._key_path),
                "-out", str(self._cert_path),
                "-days", "3650", "-nodes",
                "-subj", "/CN=127.0.0.1",
                "-addext", "subjectAltName=IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
        self._key_path.chmod(0o600)
        logger.info("Certificate generated: %s", self._cert_path)
