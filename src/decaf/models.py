"""Domain models for decaf.

All monetary amounts use Decimal. Dates use datetime.date.
Frozen dataclasses throughout — immutable after creation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


# ---------------------------------------------------------------------------
# Input models (parsed from FlexQuery XML)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountInfo:
    """Account metadata from broker statement."""

    account_id: str
    base_currency: str
    holder_name: str
    date_opened: date
    country: str
    broker_name: str = ""


@dataclass(frozen=True, slots=True)
class Trade:
    """A single executed trade (stock/ETF or forex conversion)."""

    account_id: str
    asset_category: str          # "STK" or "CASH" (forex)
    symbol: str
    isin: str                    # empty string for forex trades
    description: str
    currency: str
    fx_rate_to_base: Decimal
    trade_datetime: date         # parsed from dateTime (date part only)
    settle_date: date            # from settleDateTarget
    buy_sell: str                # "BUY" or "SELL"
    quantity: Decimal            # positive for buys, negative for sells
    trade_price: Decimal
    proceeds: Decimal            # positive for sells, negative for buys
    cost: Decimal                # broker's FIFO cost basis (negative for sells)
    commission: Decimal          # always negative (cost to trader)
    commission_currency: str
    broker_pnl_realized: Decimal # broker's computed FIFO P/L
    listing_exchange: str        # IBKR listing exchange (LSEETF, IBIS2, NYSE...)
    acquisition_date: date       # lot acquisition date (sell: which lot; buy: = trade date)

    @property
    def is_forex(self) -> bool:
        return self.asset_category == "CASH"

    @property
    def is_sell(self) -> bool:
        return self.buy_sell == "SELL"

    @property
    def is_buy(self) -> bool:
        return self.buy_sell == "BUY"


@dataclass(frozen=True, slots=True)
class OpenPositionLot:
    """A single lot in an open position at statement end date.

    With the Flex Query in "Lot" mode, each purchase lot is reported
    separately with its own openDateTime and cost basis.
    """

    account_id: str
    asset_category: str
    symbol: str
    isin: str
    description: str
    currency: str
    fx_rate_to_base: Decimal
    quantity: Decimal
    mark_price: Decimal
    position_value: Decimal      # quantity * mark_price in local currency
    cost_basis_money: Decimal    # total cost basis in local currency
    open_datetime: date          # when this lot was acquired (trade date)
    listing_exchange: str        # IBKR exchange code (LSEETF, IBIS2, NASDAQ...)


@dataclass(frozen=True, slots=True)
class CashTransaction:
    """A cash movement: interest, withholding tax, deposit, fee, etc."""

    account_id: str
    tx_type: str                 # "Broker Interest Received", "Withholding Tax", etc.
    currency: str
    fx_rate_to_base: Decimal
    date_time: date
    settle_date: date
    amount: Decimal
    description: str


@dataclass(frozen=True, slots=True)
class ConversionRate:
    """Broker's daily FX rate for a currency pair on a given date."""

    report_date: date
    from_currency: str
    to_currency: str
    rate: Decimal


@dataclass(frozen=True, slots=True)
class CashReportEntry:
    """Period-level cash summary for one currency."""

    currency: str
    starting_cash: Decimal
    ending_cash: Decimal


# ---------------------------------------------------------------------------
# Output models (computed tax report)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RWLine:
    """One line of Quadro RW (foreign asset monitoring)."""

    codice_investimento: int      # 1 = bank account, 20 = security
    isin: str
    symbol: str
    description: str
    country: str                  # derived from ISIN prefix (IE, US, etc.)
    acquisition_date: date | None # when acquired (None for cash)
    disposed_date: date | None    # when sold (None = held at year-end)
    initial_value_eur: Decimal
    final_value_eur: Decimal
    days_held: int
    ownership_pct: Decimal        # always 100 for individual accounts
    ivafe_due: Decimal


@dataclass(slots=True)
class RTLine:
    """One realized gain/loss for Quadro RT."""

    symbol: str
    isin: str
    acquisition_date: date       # when the lot was acquired
    sell_date: date
    quantity: Decimal
    proceeds_eur: Decimal
    cost_basis_eur: Decimal
    gain_loss_eur: Decimal
    ecb_rate: Decimal            # ECB rate used for EUR conversion
    is_forex: bool
    broker_pnl: Decimal          # broker's original value for cross-check
    broker_pnl_eur: Decimal      # broker's value converted to EUR


@dataclass(slots=True)
class RLLine:
    """Interest income or withholding tax entry for Quadro RL."""

    description: str
    currency: str
    gross_amount: Decimal
    gross_amount_eur: Decimal
    wht_amount: Decimal
    wht_amount_eur: Decimal
    net_amount_eur: Decimal


@dataclass(frozen=True, slots=True)
class ForexGainEntry:
    """A single forex FIFO gain/loss from converting USD to EUR."""

    disposal_date: date
    usd_amount: Decimal           # USD disposed in this entry
    acquisition_date: date        # from the FIFO lot consumed
    ecb_rate_acquisition: Decimal # EUR/USD at acquisition
    ecb_rate_disposal: Decimal    # EUR/USD at disposal
    gain_eur: Decimal             # positive = gain, negative = loss


@dataclass(frozen=True, slots=True)
class UsdEvent:
    """A single USD cash flow event for the forex timeline."""

    date: date
    amount: Decimal         # positive = inflow, negative = outflow
    balance: Decimal        # running balance after this event
    description: str


@dataclass(slots=True)
class ForexDayRecord:
    """Daily forex balance for threshold analysis."""

    date: date
    usd_balance: Decimal
    eur_equivalent: Decimal
    fx_rate: Decimal
    is_business_day: bool
    above_threshold: bool


@dataclass(slots=True)
class TaxReport:
    """Complete tax report for one year."""

    tax_year: int
    account: AccountInfo
    rw_lines: list[RWLine] = field(default_factory=list)
    rt_lines: list[RTLine] = field(default_factory=list)
    rl_lines: list[RLLine] = field(default_factory=list)
    forex_threshold_breached: bool = False
    forex_max_consecutive_days: int = 0
    forex_first_breach_date: date | None = None
    forex_daily_records: list[ForexDayRecord] = field(default_factory=list)
    forex_usd_events: list[UsdEvent] = field(default_factory=list)

    @property
    def total_ivafe(self) -> Decimal:
        return sum((line.ivafe_due for line in self.rw_lines), Decimal(0))

    @property
    def net_capital_gain_loss(self) -> Decimal:
        return sum((line.gain_loss_eur for line in self.rt_lines), Decimal(0))

    @property
    def total_gross_interest_eur(self) -> Decimal:
        return sum((line.gross_amount_eur for line in self.rl_lines), Decimal(0))

    @property
    def total_wht_eur(self) -> Decimal:
        return sum((line.wht_amount_eur for line in self.rl_lines), Decimal(0))
