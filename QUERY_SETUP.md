# Flex Query Setup Guide

Step-by-step instructions for creating the Activity Flex Query in Interactive Brokers that ibtax needs.

## Prerequisites

- An Interactive Brokers account (IBKR Ireland or similar)
- Access to Client Portal or Account Management

## Create the Flex Query

1. Log in to **Client Portal**
2. Go to **Performance & Reports** > **Flex Queries**
3. Click **+** (Create) next to **Activity Flex Queries**
4. Set the **Query Name** to `Italian Tax Report` (or any name you like)

## Configure Sections

For each section below, click the section name to expand it, then check the listed fields.

### Account Information

No options to set. Select these fields:

- Account ID
- Currency
- Name
- Account Type
- Customer Type
- Date Opened
- Street (Mailing Address)
- Street2 (Mailing Address)
- City (Mailing Address)
- State (Mailing Address)
- Country (Mailing Address)
- Postal Code (Mailing Address)
- Street (Residential Address)
- Street2 (Residential Address)
- City (Residential Address)
- State (Residential Address)
- Country (Residential Address)
- Postal Code (Residential Address)
- Primary Email

### Cash Report

No options to set. Select these fields:

- Account ID
- Currency
- Starting Cash
- Ending Cash

### Cash Transactions

**Options** (check ALL of the following):
- [x] Dividends
- [x] Payment in Lieu of Dividends
- [x] Withholding Tax
- [x] 871(m) Withholding
- [x] Advisor Fees
- [x] Other Fees
- [x] Other Income
- [x] Deposits & Withdrawals
- [x] Carbon Credits
- [x] Bill Pay
- [x] Broker Interest Paid
- [x] Broker Interest Received
- [x] Broker Fees
- [x] Bond Interest Paid
- [x] Bond Interest Received
- [x] Price Adjustments
- [x] Commission Adjustments
- [x] Detail

**Do NOT check**: Summary

Select these fields:
- Account ID
- Currency
- FXRateToBase
- Type
- Date/Time
- Settle Date
- Amount
- Description

### Open Dividend Accruals

No options. Select these fields:

- Account ID
- Currency
- FXRateToBase
- Symbol
- ISIN
- Ex Date
- Pay Date
- Gross Amount
- Net Amount
- Tax

### Open Positions

**Options**: Select **Lot** (NOT Summary)

> **Important**: You MUST select "Lot" mode, not "Summary". Lot mode
> provides per-lot open dates which are required for IVAFE pro-rata
> day counting. Summary mode returns empty `openDateTime` fields.

Select these fields:
- Account ID
- Currency
- FXRateToBase
- Asset Class
- Symbol
- ISIN
- Description
- Quantity
- Mark Price
- Position Value
- Cost Basis Money
- Open Date/Time

### Trades

**Options**: Select **Execution** only

Do NOT check: Symbol Summary, Asset Class, Order, Closed Lots, Wash Sales

Select these fields:
- Account ID
- Currency
- FXRateToBase
- Asset Class
- Symbol
- ISIN
- Description
- Date/Time
- Settle Date Target
- Buy/Sell
- Quantity
- TradePrice
- Proceeds
- IB Commission
- IB Commission Currency
- Cost Basis
- Realized P/L

## Delivery Configuration

| Setting | Value |
|---------|-------|
| Format | **XML** |
| Period | **Last 365 Calendar Days** |

## General Configuration

| Setting | Value |
|---------|-------|
| Profit and Loss | Default |
| Include Canceled Trades? | No |
| **Include Currency Rates?** | **Yes** |
| Include Audit Trail Fields? | Yes |
| Display Account Alias in Place of Account ID? | No |
| Breakout by Day? | No |
| **Date Format** | **yyyyMMdd** |
| **Time Format** | **HHmmss** |
| **Date/Time Separator** | **; (semi-colon)** |

## Field Name Mapping

The IB UI uses different names in the selection screen vs. the review
screen vs. the XML output. Here's the mapping for fields where the
names differ:

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
| Open Date/Time | OpenDateTime | `openDateTime` |
| Quantity (Positions) | Quantity | `position` |

## Get Your Token and Query ID

1. Go to **Performance & Reports** > **Flex Queries** > **Flex Web Service Configuration**
2. Activate the service and generate a **Token**
3. Note your **Query ID** (shown next to the query name)
4. Set them as environment variables or in a `.env` file:

```bash
IBKR_TOKEN=your_token_here
IBKR_QUERY_ID=your_query_id_here
```
