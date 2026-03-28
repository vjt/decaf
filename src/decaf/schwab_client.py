"""Schwab Trader API client.

Wraps the Schwab Trader API v1 endpoints needed for Italian tax reporting:
- Account numbers (to get the encrypted hash)
- Account details with positions
- Transaction history (trades, RSU deposits, dividends)

All endpoints require an OAuth2 access token managed by SchwabAuth.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import aiohttp

from decaf.schwab_auth import SchwabAuth

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.schwabapi.com/trader/v1"


class SchwabClient:
    """Async client for Schwab Trader API."""

    def __init__(self, auth: SchwabAuth) -> None:
        self._auth = auth

    async def get_account_numbers(
        self, session: aiohttp.ClientSession,
    ) -> list[dict[str, str]]:
        """Get account number to hash mapping.

        Returns list of {"accountNumber": "...", "hashValue": "..."}.
        The hash is required for all subsequent account-specific API calls.
        """
        return await self._get(session, "/accounts/accountNumbers")

    async def get_account(
        self, session: aiohttp.ClientSession, account_hash: str,
    ) -> dict[str, Any]:
        """Get account details including current positions.

        Returns the full account JSON with securitiesAccount.positions[].
        """
        return await self._get(
            session,
            f"/accounts/{account_hash}",
            params={"fields": "positions"},
        )

    async def get_transactions(
        self,
        session: aiohttp.ClientSession,
        account_hash: str,
        start_date: date,
        end_date: date,
        types: str = "TRADE,RECEIVE_AND_DELIVER,DIVIDEND_OR_INTEREST",
    ) -> list[dict[str, Any]]:
        """Get transaction history for an account.

        Default types cover what we need for Italian tax:
        - TRADE: buy/sell executions (Quadro RT)
        - RECEIVE_AND_DELIVER: RSU vest deposits (lot acquisition dates)
        - DIVIDEND_OR_INTEREST: dividends, interest (Quadro RL)
        """
        return await self._get(
            session,
            f"/accounts/{account_hash}/transactions",
            params={
                "startDate": _fmt_datetime(start_date),
                "endDate": _fmt_datetime(end_date),
                "types": types,
            },
        )

    async def _get(
        self,
        session: aiohttp.ClientSession,
        path: str,
        params: dict[str, str] | None = None,
    ) -> Any:
        """Make an authenticated GET request to the Schwab API."""
        token = await self._auth.get_access_token(session)
        url = f"{_BASE_URL}{path}"

        logger.debug("GET %s", url)
        async with session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Schwab API error {resp.status} for {path}: {body}"
                )
            return await resp.json()


def _fmt_datetime(d: date) -> str:
    """Format date as Schwab expects: ISO-8601 with time component."""
    return f"{d.isoformat()}T00:00:00.000Z"
