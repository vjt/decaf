# IBKR Italian Tax Report Generator

## Project Goal

Build a CLI tool (Python) that reads an Interactive Brokers Flex Query XML export and produces a complete Italian tax report for the "dichiarazione dei redditi" (tax return). The tool must compute all values needed for:

- **Quadro RW** (foreign asset monitoring + IVAFE tax)
- **Quadro RT** (capital gains/losses on securities and forex)
- **Quadro RL** (investment income: interest, dividends)
- **Forex threshold analysis** (art. 67(1)(c-ter) TUIR)

The output should be a structured report (both human-readable terminal output and a JSON file) that a commercialista (Italian tax accountant) can use directly to fill in the tax return.

## Italian Tax Rules Reference

The tool must implement these rules precisely:

### Quadro RW — Foreign Asset Monitoring + IVAFE

- Every foreign financial asset held at any point during the tax year must be reported.
- For each asset, report: ISIN, description, country (use "IE" for Ireland-domiciled ETFs), initial value (Jan 1 or acquisition date), final value (Dec 31 or disposal date), days held, percentage of ownership (always 100% for individual accounts).
- **IVAFE** (Imposta sul Valore delle Attività Finanziarie Estere): 0.2% per annum on the market value of each position, pro-rated by the number of days held during the year out of 365 (or 366 in leap years).
- For positions acquired mid-year: the holding period starts on the trade settlement date (T+1 for stocks/ETFs in EU).
- For positions disposed mid-year: the holding period ends on the settlement date of the sale.
- Cash balances in foreign currency (e.g., USD) held at a foreign broker also go in RW.
- The foreign bank account (IBKR account itself) must be reported as a separate RW line (codice investimento 1 for bank accounts, 20 for securities).
- Values must be in EUR. For USD-denominated positions, convert using the ECB reference rate on Dec 31 (or the last available rate). For IBKR statements, use the FX rate provided by IBKR in the Flex Query.

### Quadro RT — Capital Gains/Losses (Redditi Diversi)

- Report realized gains/losses on securities sales and forex conversions.
- **Tax rate**: 26% on capital gains (redditi diversi).
- **Cost basis**: FIFO method (which is what IBKR uses by default). Include commissions in the cost basis (they increase cost on buys, reduce proceeds on sells).
- **ETF classification**: UCITS-harmonized ETFs (like VWCE, VWRA, IGLD — all IE-domiciled, ISIN starts with IE) generate "redditi diversi" on capital gains. Losses from harmonized ETFs can only offset other "redditi diversi" gains, NOT "redditi di capitale".
- **Forex gains/losses**: Taxable only if the average daily foreign currency balance exceeded €51,645.69 for at least 7 consecutive business days during the tax year (see forex threshold analysis below).

### Quadro RL — Investment Income (Redditi di Capitale)

- Interest earned on cash balances is "redditi di capitale", taxed at 26%.
- Report gross interest, foreign withholding tax already deducted, and net amount.
- Foreign withholding tax may generate a tax credit under the Italy-Ireland double taxation treaty. The commercialista needs both gross and withheld amounts.
- Dividends (if any) from ETFs: accumulating ETFs (like VWCE/VWRA) don't distribute dividends, so typically nothing here. But if there are dividend entries, report them.

### Forex Threshold Analysis (art. 67(1)(c-ter) TUIR)

This is the most complex calculation:

1. Reconstruct the **daily balance** in each foreign currency (USD in this case) for every calendar day of the year.
2. Convert each daily USD balance to EUR using the ECB reference rate for that day (or IBKR's rate as a proxy).
3. Check if the EUR-equivalent balance exceeded **€51,645.69** for at least **7 consecutive business days** (exclude weekends and Italian public holidays).
4. If the threshold was breached, ALL forex gains/losses for the year become taxable. If not, forex gains/losses are tax-exempt.
5. The daily balance must account for: deposits, withdrawals, trade settlements (T+1), interest credits, withholding tax debits, and forex conversions.

Italian public holidays to exclude (2025):
- Jan 1, Jan 6, Apr 20-21 (Easter Sun/Mon), Apr 25, May 1, Jun 2, Aug 15, Nov 1, Dec 8, Dec 25, Dec 26

## Input: IBKR Flex Query XML

The tool reads an XML file exported from IBKR's Flex Query system. The expected structure is an Activity Statement Flex Query containing these sections:

### Trades (`<Trade>` elements inside `<Trades>`)
Key fields to extract:
- `symbol`, `isin`, `description`, `assetCategory` (STK, CASH for forex)
- `currency`, `fxRateToBase`
- `dateTime` (trade execution timestamp)
- `settleDateTarget` (settlement date, use this for IVAFE day counting)
- `quantity` (negative = sell)
- `tradePrice`, `tradeMoney`, `proceeds`
- `ibCommission`, `ibCommissionCurrency`
- `costBasis`, `realizedPL`
- `buySell` (BUY, SELL)
- `openCloseIndicator`

### Open Positions (`<OpenPosition>` elements inside `<OpenPositions>`)
Key fields:
- `symbol`, `isin`, `description`, `assetCategory`, `currency`
- `position` (quantity)
- `markPrice`, `costBasisMoney`, `costBasisPrice`
- `fifoPnlUnrealized`, `positionValue`
- `fxRateToBase`
- `openDateTime` (when the position was first opened — needed for IVAFE pro-rata)

### Cash Transactions (`<CashTransaction>` elements inside `<CashTransactions>`)
Key fields:
- `type` (Deposits/Withdrawals, Broker Interest Paid, Broker Interest Received, Withholding Tax, Other Fees, etc.)
- `dateTime`, `settleDate`
- `amount`, `currency`
- `description`
- `fxRateToBase`

### Cash Report (`<CashReportCurrency>` elements inside `<CashReport>`)
If available, this gives period-level cash summaries per currency. But daily reconstruction from transactions is more reliable.

### Account Information
- `accountId`, `currency` (base currency), `name`

## Output

### 1. Terminal Output
Print a clear, structured report with sections for each quadro. Use tables where appropriate. Include all intermediate calculations so the commercialista can verify.

### 2. JSON Output
Write a JSON file with the same data, structured for programmatic consumption:

```json
{
  "tax_year": 2025,
  "account": { "id": "...", "holder": "...", "broker": "Interactive Brokers Ireland Limited", "country": "IE" },
  "quadro_rw": [
    {
      "codice_investimento": 20,
      "isin": "IE00BK5BQT80",
      "description": "VANG FTSE AW USDA",
      "country": "IE",
      "initial_value_eur": 0,
      "final_value_eur": 82071.90,
      "days_held": 113,
      "ivafe_due": 50.73
    }
  ],
  "quadro_rt": {
    "capital_gains": [...],
    "capital_losses": [...],
    "forex_gains": [...],
    "forex_threshold_breached": true,
    "net_gain_loss": -196.62
  },
  "quadro_rl": {
    "gross_interest": 15.03,
    "withholding_tax_foreign": 3.01,
    "net_interest": 12.02
  },
  "forex_analysis": {
    "threshold_eur": 51645.69,
    "max_consecutive_business_days_above": 12,
    "first_breach_date": "2025-08-19",
    "daily_balances": [...]
  }
}
```

## Implementation Notes

- Use `xml.etree.ElementTree` or `lxml` for XML parsing.
- Be defensive: not all fields may be present. Handle missing fields gracefully.
- All monetary amounts should be computed with `Decimal` (not float) to avoid rounding errors.
- For the forex threshold check, if IBKR FX rates are not available for every day, fall back to a hardcoded ECB rate table or accept a CSV of ECB rates as optional input.
- The tool should work as: `python ibkr_tax.py <flexquery.xml> [--ecb-rates ecb_rates.csv] [--output report.json]`
- Include unit tests for the key calculations (IVAFE pro-rata, forex threshold, cost basis with commissions).
- Add a `--verbose` flag that prints the daily USD balance reconstruction for forex threshold verification.

## Test Data

The Flex Query XML I'll provide covers the period January 1 — December 31, 2025, for an account at Interactive Brokers Ireland Limited (IBIE). Key facts for validation:

- **3 stock positions**: IGLD (303 shares, EUR), VWCE (565 shares, EUR), VWRA (418 shares, USD)
- **1 realized trade**: sale of 1 VWRA share on 2025-09-04, realized P/L approximately -3.85 EUR
- **Forex activity**: multiple EUR/USD conversions, largest on 2025-11-19
- **Interest earned**: ~15 EUR gross, ~3 EUR withheld
- **No dividends** (all ETFs are accumulating)
- **Total NAV at Dec 31, 2025**: 167,372.55 EUR

The tool should flag any discrepancies between its calculations and the values in the Flex Query (e.g., if our computed realized P/L differs from IBKR's `realizedPL` field).
