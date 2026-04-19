# IBKR Flex Query Setup Guide

Step-by-step guide for creating the Activity Flex Query that decaf uses to generate your Italian tax report.

## Prerequisites

- An Interactive Brokers account (IBKR Ireland or similar)
- Access to the [Client Portal](https://portal.interactivebrokers.com/)

## Step 1: Create a new Activity Flex Query

Log in to Client Portal. Go to **Performance & Reports** > **Flex Queries**. Click the **Create** button (or **+**) next to **Activity Flex Query**.

![Create Activity Flex Query](img/01-flex-queries-create.png)

## Step 2: Set the Query Name

Enter a name for your query. We use `Italian Tax Report` but you can call it whatever you want.

![Query Name](img/02-query-name.png)

## Step 3: Configure Sections

You'll see a list of collapsible sections. Click each one to expand it and select the required fields. Configure them exactly as shown below.

### Account Information

Select all fields. This provides account metadata for the report.

![Account Information](img/03-account-information.png)

### Cash Report

**Options**: Select **Currency Breakout** (this gives per-currency starting/ending balances instead of just the base currency summary).

**Fields**: Account ID, Currency, Starting Cash, Ending Cash.

![Cash Report](img/04-cash-report.png)

### Cash Transactions

**Options**: Check ALL transaction types in both columns (Dividends, Withholding Tax, Broker Interest Received, Deposits & Withdrawals, etc.). Make sure **Detail** is selected, NOT Summary.

**Fields**: Account ID, Currency, FXRateToBase, Type, Date/Time, Settle Date, Amount, Description.

![Cash Transactions](img/05-cash-transactions.png)

### Open Dividend Accruals

No options to set. Select all fields shown: Account ID, Currency, FXRateToBase, Symbol, ISIN, Ex Date, Pay Date, Gross Amount, Net Amount, Tax.

![Open Dividend Accruals](img/06-open-dividend-accruals.png)

### Open Positions

> **IMPORTANT**: Select **Lot** mode, NOT Summary. This is critical. Lot mode provides per-lot acquisition dates (`openDateTime`) which are required for IVAFE pro-rata day counting. Summary mode returns empty dates and the report will be incorrect.

**Options**: Select **Lot** (you should see the checkmark on Lot, not Summary).

**Fields**: Account ID, Currency, FXRateToBase, Asset Class, Symbol, ISIN, Description, Quantity, Mark Price, Position Value, Cost Basis Money, Open Date Time.

![Open Positions - Lot mode](img/07-open-positions.png)

### Trades

**Options**: Select **Execution** *and* **Closed Lots**. Do not check Symbol Summary, Asset Class (option), Order, or Wash Sales.

> **Why Closed Lots matters**: per art. 9 c. 2 TUIR decaf converts the cost basis at the ECB rate on the lot's acquisition date and the proceeds at the ECB rate on the sell settlement date. Without Closed Lots enabled, every SELL reports the sell date as the acquisition date and the plusvalenza is converted at a single rate — an approximation, not what the Agenzia expects. Schwab already exposes per-lot acquisition dates in its Year-End Summary; enabling Closed Lots on IBKR brings the two brokers into alignment.

**Fields**: Account ID, Currency, FXRateToBase, Asset Class, Symbol, ISIN, Description, Date/Time, Settle Date Target, Buy/Sell, Quantity, TradePrice, Proceeds, IB Commission, IB Commission Currency, Cost Basis, Realized P/L, Listing Exchange.

![Trades - Execution + Closed Lots](img/08-trades.png)

IB applies this field list to both the Execution rows and the Closed Lot children — each `<Lot>` under a SELL `<Trade>` emits its own `openDateTime`, `cost`, `proceeds`, `quantity`, `fifoPnlRealized`. decaf's parser flattens these into one Trade row per lot so every RT line gets per-lot ECB conversion.

## Step 4: Delivery and General Configuration

Scroll down to the Delivery and General Configuration sections. Set them as follows:

| Setting | Value |
|---------|-------|
| **Format** | **XML** |
| **Period** | **Last 365 Calendar Days** |
| Profit and Loss | Default |
| Include Canceled Trades? | No |
| **Include Currency Rates?** | **Yes** |
| **Include Audit Trail Fields?** | **Yes** |
| Display Account Alias in Place of Account ID? | No |
| Breakout by Day? | No |
| **Date Format** | **yyyyMMdd** |
| **Time Format** | **HHmmss** |
| **Date/Time Separator** | **; (semi-colon)** |

![Delivery and General Configuration](img/09-delivery-general-config.png)

## Step 5: Review and Save

Review the Delivery and General Configuration to make sure the format, period, date/time format, and currency rates flag match the table in Step 4. The full field review summary is not reproduced here — it's a long list that's hard to cross-check at a glance; trust the per-section screenshots above.

![Delivery Configuration Review](img/11-review-delivery-config.png)

Click **Save Changes**. You should see the confirmation screen:

![Complete](img/12-complete.png)

## Step 6: Get Your Token and Query ID

1. Go back to **Performance & Reports** > **Flex Queries**
2. Your new query appears in the list with a **Query ID** (a number like `1423221`)
3. Go to **Flex Web Service Configuration** (at the bottom of the Flex Queries page)
4. Activate the service and generate a **Token**
5. Set both in your `.env` file:

```bash
IBKR_TOKEN=your_token_here
IBKR_QUERY_ID=your_query_id_here
```

Or pass them via CLI flags, or enter them interactively when decaf prompts you.

## Field Name Mapping Reference

IB uses different names in the selection screen, the review screen, and the XML output. This table maps all three for fields where names differ:

| Selection Screen | Review Summary | XML Attribute |
|---|---|---|
| Account ID | ClientAccountID | `accountId` |
| Currency | CurrencyPrimary | `currency` |
| Asset Class | AssetClass | `assetCategory` |
| Cost Basis | CostBasis | `cost` |
| Realized P/L | FifoPnlRealized | `fifoPnlRealized` |
| Date/Time | DateTime | `dateTime` |
| Settle Date Target | SettleDateTarget | `settleDateTarget` |
| Buy/Sell | Buy/Sell | `buySell` |
| FXRateToBase | FXRateToBase | `fxRateToBase` |
| Open Date Time | OpenDateTime | `openDateTime` |
| Quantity (Positions) | Quantity | `position` |
