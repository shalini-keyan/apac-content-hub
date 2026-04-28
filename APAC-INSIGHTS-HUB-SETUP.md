# APAC Sales Insights Hub — Setup Guide

> For anyone on the team who wants to run their own version of the hub for their region.

---

## What this is

A self-contained HTML tool that turns weekly intent signals (from 6sense or similar) into a prioritised, AE-filtered view for your sales team. No backend, no dependencies — just one HTML file deployed to `quick.shopify.io`.

Live example: [https://apacinsights.quick.shopify.io](https://apacinsights.quick.shopify.io)

---

## What you need

- Access to Shopify's `quick` hosting (run `quick` in your terminal to check)
- A weekly export of intent signals (6sense, Bombora, or similar) in CSV or JSON
- Cursor (or any editor) to update the data each week

---

## File structure

Everything lives in a single HTML file: `apac-sales-insights-hub.html`

No external dependencies. CSS, JS, and data are all inline.

---

## How to set up your own version

### Step 1 — Copy the source file

Get `apac-sales-insights-hub.html` from Shalini (or the workspace). Rename it to match your region, e.g. `sea-insights-hub.html` or keep it as-is.

### Step 2 — Update the title and region defaults

Open the file and search for these two things:

```
<title>APAC Sales Insights Hub — Shopify</title>
```
Change to your region, e.g. `SEA Sales Insights Hub — Shopify`

```
const WEEK = "March 23, 2026";
```
Update this each week to match the week you're publishing for.

### Step 3 — Replace the signals data

The signals live in a `const signals = [...]` array starting around line 733.

Each signal looks like this:

```json
{
  "type": "mqa",
  "account": "Company Name",
  "website": "company.com",
  "ae": "First Last",
  "industry": "Retail",
  "region": "ANZ",
  "grade": "",
  "engagement": [
    "Engagement score: 450 pts this week · 1,200 page visits in last 30 days",
    "Viewed: Pricing page",
    "Searching for: unified commerce",
    "Last active: 2026-03-21",
    "Pipeline predict score: 72%"
  ],
  "note": "Hit MQA with zero sales touches.",
  "days": 0,
  "id": 1
}
```

**Signal types:**
| type | What it means |
|------|--------------|
| `mqa` | Hit MQA threshold — no sales touches yet |
| `lost` | Closed lost deal that's re-engaging |
| `new` | Net new account engaging for the first time |
| `eng` | Existing MQA account doing specific page research |

**AE names** must match exactly across signals — the hub groups by `ae` value.

**IDs** must be unique integers — just increment from 1.

### Step 4 — Update the proof points (optional but worth it)

Around line 2472 there's a `proof` object with ANZ-specific merchant examples used in the outreach hooks:

```js
const proof = {
  ch1: "JB Hi-Fi handled nearly twice their BFCM traffic...",
  ch2: "The Good Guys ran a 3-month proof-of-concept...",
  ...
};
```

If you're running this for a different region, swap these out for relevant local proof points from your market.

### Step 5 — Create a deploy folder and script

Create a folder for your version:

```
mkdir sea-insights-hub
cp sea-insights-hub.html sea-insights-hub/index.html
```

Then deploy:

```bash
quick deploy sea-insights-hub sea-insights-hub
```

This makes it live at `https://sea-insights-hub.quick.shopify.io`

---

## Weekly update workflow

1. Download the 3 weekly CSV exports from Drive into `~/Downloads`
   - `ApacBobNewlyEngagedPeopleThisWeek`
   - `ApacBobAccountsWithHighIntentAndNoSalesTouches`
   - `ApacBobWebsiteVisitsIntentSignalsLast7Days`

2. Run the signal generator:
   ```bash
   cd anz-sales-insights
   python3 generate-signals-from-csvs.py --week "April 7, 2026"
   ```
   This automatically:
   - Excludes any account with **Open Pipeline > 0** (active open opportunity)
   - Keeps closed-lost accounts that are re-engaging
   - Writes the clean signals array into `apac-sales-insights-hub.html`
   - Copies it to `apac-insights-hub/index.html`

3. Run the signal extractor (populates `data/signals.json` for the Slack automation):
   ```bash
   python3 extract-signals.py
   ```

4. Deploy:
   ```bash
   quick deploy apac-insights-hub apacinsights --force
   ```

5. Send Slack DMs and channel summaries (the `launchd` job does this automatically on Monday at 11am AEDT, or run manually):
   ```bash
   python3 send-weekly-dms.py
   python3 send-weekly-summaries.py
   ```

### Open opportunity filtering rule

Accounts with an active, non-closed opportunity in Salesforce (`Open Pipeline > 0`) are excluded at step 2 and never appear in the hub or Slack DMs. The AE is already working that account — they don't need a signal for it.

Closed-lost accounts that are re-engaging are **kept** — that's a warm re-entry signal worth acting on.

---

## Regions and AEs currently in the ANZ version

**Regions:** ANZ, Japan, GCR, India, SEA/ROA, APAC

**AEs:**
- ANZ: Shane Kilgour, Kole Mahan, Chachi Apolinario, Lauren Critten, Bronte Hogarth, Morris Bray, Karim Lalji
- Japan: Eiji Hasegawa, Jio Sotoyama, Tanabe Rika, Yuki Kataoka, Yuki Tokunaga
- GCR/SEA: Anwei Sun, Rae Chang, Sally Xin, Weijie Neo
- India: Nikhil Sareen
- SEA/ROA: Amaly Khairallah

Update the `ae` values in your signals to match your team's names exactly.

---

## Questions?

Ping Shalini — she built and maintains the ANZ version.
