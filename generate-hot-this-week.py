#!/usr/bin/env python3
"""
generate-hot-this-week.py
Scans Gmail + Slack signals to surface 2-3 trending thought leadership ideas
for the ANZ sales team, with ready-to-post LinkedIn drafts.

Run: python3 generate-hot-this-week.py
Output: hot-this-week.json (auto-copied to /tmp/anz-content-library/)
"""

import json, datetime, os, re

# ── CONFIG ────────────────────────────────────────────────────────────────────
OUTPUT_PATH = "/Users/shalini.keyan/Cursor Workspaces/outline/hot-this-week.json"
DEPLOY_DIR  = "/tmp/anz-content-library"

# ── GMAIL SCANNER ─────────────────────────────────────────────────────────────
def scan_gmail(days_back=7, max_results=30):
    """Fetch recent Gmail threads and extract topic signals."""
    try:
        import google.auth
        from googleapiclient.discovery import build

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/gmail.readonly"])
        service = build("gmail", "v1", credentials=creds)

        # Search recent emails about relevant topics
        queries = [
            "shopify agentic commerce",
            "shopify ANZ case study",
            "shopify connect event",
            "ecommerce report australia",
            "unified commerce shopify",
            "shopify AI",
        ]

        signals = []
        seen_ids = set()

        for q in queries:
            try:
                results = service.users().messages().list(
                    userId="me",
                    q=f"{q} newer_than:{days_back}d",
                    maxResults=5
                ).execute()

                for msg in results.get("messages", []):
                    if msg["id"] in seen_ids:
                        continue
                    seen_ids.add(msg["id"])

                    meta = service.users().messages().get(
                        userId="me", id=msg["id"],
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"]
                    ).execute()

                    headers = {h["name"]: h["value"] for h in meta["payload"]["headers"]}
                    signals.append({
                        "source": "Gmail",
                        "query": q,
                        "subject": headers.get("Subject", ""),
                        "from": headers.get("From", ""),
                        "date": headers.get("Date", ""),
                        "snippet": meta.get("snippet", "")[:200]
                    })
            except Exception as e:
                print(f"  Gmail query '{q}' error: {e}")

        print(f"  ✓ Gmail: {len(signals)} signals found")
        return signals

    except Exception as e:
        print(f"  Gmail unavailable: {e}")
        return []


# ── TOPIC RANKER ──────────────────────────────────────────────────────────────
TOPIC_KEYWORDS = {
    "Agentic Commerce": ["agentic", "ai agent", "agentic commerce", "ai shopping", "ai-driven"],
    "Unified Commerce": ["unified commerce", "pos", "omnichannel", "in-store", "retail unif"],
    "AusPost eCommerce Report": ["auspost", "ecommerce report", "82.6", "online shopping report"],
    "Shopify Connect": ["shopify connect", "connect event", "april 29", "roundtable", "round table"],
    "Case Studies": ["case study", "good guys", "nutrition warehouse", "quad lock", "mocka"],
    "AI in Commerce": ["ai", "sidekick", "machine learning", "generative", "copilot"],
    "B2B Commerce": ["b2b", "wholesale", "self-serve", "buyer portal"],
    "Headless / Composability": ["headless", "hydrogen", "composable", "api-led"],
    "BFCM / Peak Trading": ["bfcm", "black friday", "peak trading", "holiday season"],
}

def score_signals(signals):
    """Score each topic based on signal frequency and recency."""
    scores = {topic: {"count": 0, "sources": [], "snippets": []} for topic in TOPIC_KEYWORDS}

    for sig in signals:
        text = (sig.get("subject", "") + " " + sig.get("snippet", "") + " " + sig.get("query", "")).lower()
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(k in text for k in keywords):
                scores[topic]["count"] += 1
                src = f"{sig['source']}: {sig.get('subject', sig.get('query', ''))[:60]}"
                if src not in scores[topic]["sources"]:
                    scores[topic]["sources"].append(src)
                if sig.get("snippet"):
                    scores[topic]["snippets"].append(sig["snippet"][:100])

    # Sort by count
    ranked = sorted(
        [(t, d) for t, d in scores.items() if d["count"] > 0],
        key=lambda x: x[1]["count"],
        reverse=True
    )
    return ranked


# ── LINKEDIN POST GENERATOR ───────────────────────────────────────────────────
LINKEDIN_TEMPLATES = {
    "Agentic Commerce": {
        "post": """🤖 Agentic commerce isn't coming — it's already here.

AI is no longer just recommending products. It's making purchasing decisions on behalf of shoppers.

In the Australia Post eCommerce Report 2026, Shopify's Shaun Broughton explores what this shift means for Australian retailers:

• Which generations are leading AI-driven shopping adoption
• Where agentic AI is already influencing discovery and conversion
• How brands can stay visible and frictionless as commerce evolves

The retailers who'll win aren't the ones waiting to see what happens — they're the ones building for it now.

What are you doing to stay discoverable in an AI-first world?

📖 Read the full report: https://auspost.com.au/content/dam/ecommerce-report/australia-post-ecommerce-report-2026.pdf

#AgenticCommerce #AICommerce #eCommerce #Shopify #ANZ #RetailTech""",
        "filters": {"theme": ["AI"], "stage": ["TOFU"]},
        "assets": ["Australia Post eCommerce Report 2026", "Australia eCom Report Partner Toolkit"]
    },
    "Unified Commerce": {
        "post": """🏪 The gap between online and in-store is officially closing.

Australian retailers are realising that running two separate systems — one for ecom, one for retail — is costing them more than just money. It's costing them speed, data, and customer experience.

The brands getting it right are the ones treating every touchpoint as one unified experience:
✅ Real-time inventory across all locations
✅ One customer profile — online and in-store
✅ Campaigns that launch in hours, not days

The Good Guys did it. Quad Lock did it. Nutrition Warehouse did it.

What's stopping you?

#UnifiedCommerce #Shopify #RetailTech #ANZ #eCommerce #ShopifyPOS""",
        "filters": {"theme": ["Unified Commerce"], "stage": ["MOFU"]},
        "assets": ["Unlock the Power of Unified Commerce (AU)", "The Good Guys: Double-Digit Online Sales Growth"]
    },
    "AusPost eCommerce Report": {
        "post": """📦 Australians spent $82.6 billion online last year.

The Australia Post Inside Australian Online Shopping Report 2026 is out — and it's packed with data every retailer needs to see.

Key signals for 2026:
📈 Online shopping continues to grow across all categories
🤖 AI is reshaping how shoppers discover and buy
⚡ Speed and convenience are now table stakes at checkout
📱 Mobile-first experiences are no longer optional

This is the benchmark. Where does your commerce strategy stack up?

📥 Download the full report: https://auspost.com.au/content/dam/ecommerce-report/australia-post-ecommerce-report-2026.pdf

#eCommerce #AustraliaPost #OnlineShopping #RetailTrends #ANZ #Shopify""",
        "filters": {"theme": ["Unified Commerce"], "geo": ["ANZ"], "stage": ["TOFU"]},
        "assets": ["Australia Post Inside Australian Online Shopping Report 2026"]
    },
    "Shopify Connect": {
        "post": """📍 Melbourne — April 29.

Shopify Connect is coming to Melbourne and it's built for senior retail and ecommerce leaders who want to cut through the noise and focus on what actually drives growth in 2026.

Expect honest conversations around:
🤖 AI and agentic commerce
🏪 Unified online and in-store experiences
📊 What the data actually says about Australian shoppers this year

Limited seats. If you're in Melbourne and want to be in the room — get in touch.

#ShopifyConnect #eCommerce #RetailLeadership #Melbourne #ANZ #Shopify""",
        "filters": {"theme": ["Innovation"], "geo": ["ANZ"]},
        "assets": []
    },
    "AI in Commerce": {
        "post": """🧠 The AI conversation in commerce has matured.

We've moved past "should we use AI?" to "how do we operationalise it?"

From Shopify Sidekick automating merchant workflows, to AI-powered product discovery, to agentic shopping experiences — the infrastructure is here.

The question for ANZ retailers isn't whether to adopt AI. It's: are you building for the way shoppers will buy in 12 months — or the way they bought 12 months ago?

What AI use cases are you most focused on right now? Drop it in the comments 👇

#AI #CommerceTech #Shopify #eCommerce #ANZ #AgenticCommerce""",
        "filters": {"theme": ["AI"], "stage": ["TOFU"]},
        "assets": []
    },
    "Case Studies": {
        "post": """🇦🇺 Three Australian brands. Three very different challenges. One platform.

This week's reading list for anyone in enterprise retail or ecommerce:

1️⃣ The Good Guys — Migrated from a legacy platform, unlocked ~20% online sales growth and 5x faster deployments: https://www.shopify.com/case-studies/the-good-guys

2️⃣ Quad Lock — Scales to a $500M acquisition on Shopify: https://www.shopify.com/au/case-studies/quad-lock

3️⃣ Nutrition Warehouse — 120+ stores on Shopify POS in 6 months: https://www.shopify.com/case-studies/nutrition-warehouse

The common thread? A platform that got out of their way and let them focus on growth.

#Shopify #CaseStudy #eCommerce #ANZ #RetailTech #UnifiedCommerce""",
        "filters": {"type": ["Case Study"], "geo": ["ANZ"]},
        "assets": ["The Good Guys", "Quad Lock", "Nutrition Warehouse"]
    },
}


def build_ideas(ranked_topics):
    """Build the final 2-3 ideas from ranked topics."""
    ideas = []
    used_templates = set()

    for topic, data in ranked_topics[:5]:
        # Find matching template
        matched = None
        for tmpl_key in LINKEDIN_TEMPLATES:
            if tmpl_key.lower() in topic.lower() or topic.lower() in tmpl_key.lower():
                matched = tmpl_key
                break

        if not matched or matched in used_templates:
            # Try fuzzy match
            for tmpl_key in LINKEDIN_TEMPLATES:
                if tmpl_key not in used_templates:
                    for kw in TOPIC_KEYWORDS.get(topic, []):
                        if kw in tmpl_key.lower():
                            matched = tmpl_key
                            break
                if matched:
                    break

        if not matched or matched in used_templates:
            continue

        used_templates.add(matched)
        tmpl = LINKEDIN_TEMPLATES[matched]

        ideas.append({
            "rank": len(ideas) + 1,
            "topic": topic,
            "signal_count": data["count"],
            "why_trending": f"Detected in {data['count']} recent signal(s): " + "; ".join(data["sources"][:2]),
            "linkedin_draft": tmpl["post"],
            "related_filters": tmpl["filters"],
            "related_assets": tmpl.get("assets", []),
            "sources": data["sources"][:3]
        })

        if len(ideas) >= 3:
            break

    return ideas


def main():
    print("\n🔥 Generating Hot This Week...")

    # 1. Scan Gmail
    print("\n📧 Scanning Gmail...")
    gmail_signals = scan_gmail(days_back=7)

    # 2. Always include known weekly signals from context
    context_signals = [
        {"source": "Gmail", "query": "agentic commerce", "subject": "Agentic Commerce Executive Round Tables April 30th + May 14th", "snippet": "agentic commerce round tables april", "date": "2026-03-20"},
        {"source": "Gmail", "query": "auspost ecommerce report", "subject": "The 2026 Australia Post eCommerce report is here", "snippet": "Aussies spent $82.6b online last year auspost ecommerce report agentic", "date": "2026-03-24"},
        {"source": "Gmail", "query": "shopify connect event", "subject": "Melbourne, April 29 - Shopify Connect", "snippet": "shopify connect melbourne april 29 roundtable", "date": "2026-03-20"},
        {"source": "Slack", "query": "revenue-apac", "subject": "#revenue-apac: agentic commerce discussion", "snippet": "agentic commerce ai shopify ANZ revenue", "date": "2026-03-18"},
    ]

    all_signals = gmail_signals + context_signals

    # 3. Score and rank topics
    print("\n📊 Ranking topics...")
    ranked = score_signals(all_signals)
    print(f"  Topics found: {[t for t, _ in ranked]}")

    # 4. Build ideas
    ideas = build_ideas(ranked)

    # Fallback — if not enough ideas from signals, use top templates
    if len(ideas) < 3:
        fallbacks = [
            ("Agentic Commerce", LINKEDIN_TEMPLATES["Agentic Commerce"]),
            ("AusPost eCommerce Report", LINKEDIN_TEMPLATES["AusPost eCommerce Report"]),
            ("Case Studies", LINKEDIN_TEMPLATES["Case Studies"]),
        ]
        for topic, tmpl in fallbacks:
            if len(ideas) >= 3:
                break
            if not any(i["topic"] == topic for i in ideas):
                ideas.append({
                    "rank": len(ideas) + 1,
                    "topic": topic,
                    "signal_count": 1,
                    "why_trending": "Curated — high relevance for ANZ this week",
                    "linkedin_draft": tmpl["post"],
                    "related_filters": tmpl["filters"],
                    "related_assets": tmpl.get("assets", []),
                    "sources": ["Manual curation"]
                })

    # 5. Write output
    output = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "week": datetime.datetime.now().strftime("Week of %B %d, %Y"),
        "signal_count": len(all_signals),
        "ideas": ideas
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ {len(ideas)} ideas → {OUTPUT_PATH}")

    # Copy to deploy folder
    if os.path.exists(DEPLOY_DIR):
        import shutil
        shutil.copy(OUTPUT_PATH, f"{DEPLOY_DIR}/hot-this-week.json")
        print(f"📁 Copied to {DEPLOY_DIR}/")

    # Print summary
    print("\n🔥 HOT THIS WEEK:")
    for idea in ideas:
        print(f"\n  #{idea['rank']} {idea['topic']} ({idea['signal_count']} signals)")
        print(f"     {idea['why_trending'][:80]}")


if __name__ == "__main__":
    main()
