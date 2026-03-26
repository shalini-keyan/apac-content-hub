#!/usr/bin/env python3
"""
ANZ Content Library — Asset Refresher
Reads from:
  1. Google Sheets  (SOURCES list below)
  2. Slack channels (SLACK_CHANNELS list below) — extracts content links from messages

Run: /Users/shalini.keyan/.local/bin/python3.12 refresh-assets.py
Then: quick deploy /tmp/anz-content-library anzcontent
"""
import json, re, sys, subprocess, datetime

# ── GOOGLE SHEETS CONFIG ────────────────────────────────────────────────────
# Each source maps to one tab. "schema" hints at the column layout:
#   "master"    → Asset Title, Asset Type, URL, Summary, Funnel Stage, Persona, Theme, Geo...
#   "audit"     → Funnel Stage, Theme, Content (title), Content Type, Content Details, File, Status
#   "blogs"     → Funnel Stage, Title, Summary, Post date, Industry, Link, Topics
#   "partner"   → Agency, Title, Industry, Brief Explanation, Market, URL, Direct link
#   "apac"      → Merchant, Status, Country, Segment, Date Published, Live Article Link, Video link
#   "tofu"      → (row 2 = real headers) #, Asset, Type, Funnel Stage, Recommended Package Type, ...
SPREADSHEET_ID = "1kUt_4iUk_g7mi5I6yV_I68VD29fZ9ho2DfpPmc-5veM"

SOURCES = [
    # ── Core master inventories ───────────────────────────────────────────
    {"name": "ANZ Content Library",            "gid": "702906003",  "region": "ANZ",    "schema": "master"},
    {"name": "Presentations & Pitch Decks",    "gid": "345448935",  "region": "ANZ",    "schema": "master"},
    # ── Vertical content audits ───────────────────────────────────────────
    {"name": "Shopify TOFU Asset Shortlist",   "gid": "467084718",  "region": "Global", "schema": "tofu"},
    {"name": "Enterprise Blogs 2025",          "gid": "1235249253", "region": "Global", "schema": "blogs"},
    {"name": "Fashion",                        "gid": "801339546",  "region": "Global", "schema": "audit"},
    {"name": "Security",                       "gid": "1856856270", "region": "Global", "schema": "audit"},
    {"name": "Black Friday",                   "gid": "1693852364", "region": "Global", "schema": "audit"},
    {"name": "B2B",                            "gid": "180149224",  "region": "Global", "schema": "audit"},
    {"name": "AI in Commerce",                 "gid": "1572854380", "region": "Global", "schema": "audit"},
    {"name": "Crossborder Expansion",          "gid": "355603719",  "region": "Global", "schema": "audit"},
    {"name": "Composability Audit",            "gid": "1652294571", "region": "Global", "schema": "audit"},
    {"name": "Content Audit (Xgrowth)",        "gid": "185460988",  "region": "ANZ",    "schema": "audit"},
    # ── Partner case studies ──────────────────────────────────────────────
    {"name": "ANZ Partner Case Studies",       "gid": "673437028",  "region": "ANZ",    "schema": "partner"},
    {"name": "SEA Partner Case Studies",       "gid": "847479439",  "region": "SEA",    "schema": "partner"},
    # ── APAC tracker ─────────────────────────────────────────────────────
    {"name": "APAC Case Studies",              "gid": "565467932",  "region": "APAC",   "schema": "apac"},
    # ── Vault-sourced assets (high-performing, found via Vault MCP) ───────
    {"name": "Vault Sourced Assets",           "gid": "799652894",  "region": "ANZ",    "schema": "master"},
]

# ── SLACK CHANNELS CONFIG ───────────────────────────────────────────────────
SLACK_CHANNELS = [
    {"id": "C09UVBCGCQG", "name": "revenue-marketing-team",              "region": "Global"},
    {"id": "C09QY5NR6RF", "name": "ai-h1-campaign-project",              "region": "Global", "theme": "AI"},
    {"id": "C09GTBS48G0", "name": "case-studies",                        "region": "Global", "type": "Case study"},
    {"id": "C09HSGLVD1V", "name": "gartner-mq-2025",                     "region": "Global", "theme": "Fragmentation/Integration"},
    {"id": "C09B8188DBJ", "name": "proj-automotive-campaign",            "region": "Global"},
    {"id": "C0ACCJPU8V6", "name": "proj-emea-h1-ai-campaign",            "region": "EMEA",   "theme": "AI"},
    {"id": "C0A8U3FRH5F", "name": "unified-commerce-midmarket-campaign", "region": "Global", "theme": "Unified Commerce"},
    {"id": "C088QRM6HRC", "name": "rev-apac-anz",                        "region": "ANZ"},
    {"id": "C09FKQCPF42", "name": "anz-acquisition",                     "region": "ANZ"},
]

OUTPUT_PATH = "/Users/shalini.keyan/Cursor Workspaces/outline/assets.json"
DEPLOY_DIR  = "/tmp/anz-content-library"

# ── URL CLASSIFICATION ──────────────────────────────────────────────────────
URL_RULES = [
    # (regex, type, stage, theme_hint)
    (r"shopify\.com/(?:au/|nz/|ca/)?(?:plus/)?customers/([^>\s\"'\)]+)",   "Case study",         "MOFU", ""),
    (r"shopify\.com/case-studies/([^>\s\"'\)]+)",                           "Case study",         "MOFU", ""),
    (r"shopify\.com/enterprise/blog/([^>\s\"'\)]+)",                        "Enterprise Blog",    "TOFU", ""),
    (r"shopify\.com/(?:au/|nz/)?(?:enterprise/)?blog/([^>\s\"'\)]+)",      "Blog",               "TOFU", ""),
    (r"shopify\.com/webinar/([^>\s\"'\)]+)",                                "Webinar",            "MOFU", ""),
    (r"shopify\.com/(?:au/|nz/)?retail/([^>\s\"'\)]+)",                    "Enterprise Blog",    "TOFU", "Unified Commerce"),
    (r"shopify\.com/resource/([^>\s\"'\)]+)",                               "Report / Whitepaper","MOFU", ""),
    (r"shopify\.seismic\.com/([^>\s\"'\)]+)",                               "Seismic Asset",      "BOFU", ""),
    (r"quick\.shopify\.io/([^>\s\"'\)]+)",                                  "Quick Site",         "BOFU", ""),
    (r"docs\.google\.com/(?:presentation|document|spreadsheets)/d/([^>\s\"'\)/]+)", "Internal Doc", "BOFU", ""),
]

SKIP_URL_PATTERNS = [
    r"slack\.com", r"shopify\.slack\.com", r"github\.com", r"figma\.com",
    r"lookerstudio\.google", r"banff\.lightning\.force", r"coda\.io",
    r"campaign-code-manager\.shopify", r"vault\.shopify\.io", r"ironclad",
    r"shopify\.dev", r"help\.shopify", r"apps\.shopify\.com",
    r"shopify\.com/careers", r"shopify\.com/investors", r"shopify\.com/legal",
    r"seismic\.com/Link/Content/DC",  # seismic deep links (not directly shareable)
]

def classify_url(url):
    """Return (type, stage, theme_hint) or None if URL should be skipped."""
    for skip in SKIP_URL_PATTERNS:
        if re.search(skip, url, re.I):
            return None
    for pattern, typ, stage, theme in URL_RULES:
        if re.search(pattern, url, re.I):
            return typ, stage, theme
    if "shopify.com" in url or "shopify.io" in url:
        return "Asset", "MOFU", ""
    return None

def extract_title_from_url(url):
    slug = url.rstrip("/").split("/")[-1].split("?")[0]
    return slug.replace("-", " ").replace("_", " ").title()

def extract_urls_from_message(text):
    """Find all http(s) URLs in a Slack message."""
    return re.findall(r'https?://[^\s<>\"\'\)]+', text)

def clean_text(text):
    """Strip Slack markup — mentions, emoji, etc."""
    text = re.sub(r'<@[^>]+>', '', text)          # mentions
    text = re.sub(r'<#[^>]+\|([^>]+)>', r'#\1', text)  # channel refs
    text = re.sub(r'<([^|>]+)\|([^>]+)>', r'\2', text) # links with label
    text = re.sub(r'<([^>]+)>', r'\1', text)       # bare URLs in angle brackets
    text = re.sub(r':[a-z0-9_\-]+:', '', text)     # emoji codes
    text = re.sub(r'\*([^*]+)\*', r'\1', text)     # bold
    text = re.sub(r'_([^_]+)_', r'\1', text)       # italic
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def guess_theme(text, url, channel_theme=""):
    text_lower = (text + " " + url).lower()
    if channel_theme:
        return channel_theme
    if any(w in text_lower for w in ["ai ", "agentic", "sidekick", "machine learning", "llm", "geo blog", "generative"]):
        return "AI"
    if any(w in text_lower for w in ["unified commerce", "omnichannel", "pos", "point of sale", "unif"]):
        return "Unified Commerce"
    if any(w in text_lower for w in ["fragment", "integration", "patchwork", "migration", "replatform"]):
        return "Fragmentation/Integration"
    if any(w in text_lower for w in ["b2b", "wholesale", "d2c"]):
        return "B2B"
    if any(w in text_lower for w in ["scale", "growth", "expand", "international"]):
        return "Scalability"
    return ""

def guess_credibility(typ):
    if typ in ("Case study", "Report / Whitepaper"):
        return "HIGH"
    if typ in ("Enterprise Blog", "Blog"):
        return "MED"
    if typ == "Webinar":
        return "MED"
    return "MED"

def guess_geo(url, channel_region):
    if "shopify.com/au/" in url or "shopify.com/nz/" in url:
        return "ANZ"
    if channel_region and channel_region != "Global":
        return channel_region
    return "Global"

def scrape_slack_channels(mcp_script_path):
    """
    Call the Slack MCP via a helper script to get messages from each channel.
    Returns list of asset dicts.
    """
    assets = []
    seen_urls = set()

    for ch in SLACK_CHANNELS:
        ch_id   = ch["id"]
        ch_name = ch["name"]
        ch_type = ch.get("type", "")
        ch_theme = ch.get("theme", "")
        ch_region = ch.get("region", "Global")

        print(f"  Scanning #{ch_name}...")
        try:
            result = subprocess.run(
                [sys.executable, mcp_script_path, "get_messages", ch_id],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0 or not result.stdout.strip():
                print(f"    No data / error")
                continue
            messages = json.loads(result.stdout)
        except Exception as e:
            print(f"    Error: {e}")
            continue

        ch_assets = 0
        for msg in messages:
            text = msg.get("text", "") or ""
            if not text:
                continue
            urls = extract_urls_from_message(text)
            for url in urls:
                url = url.rstrip(".,;:)")
                if url in seen_urls:
                    continue
                classification = classify_url(url)
                if not classification:
                    continue
                seen_urls.add(url)

                typ, stage, theme_hint = classification
                if ch_type:
                    typ = ch_type
                theme = guess_theme(text, url, ch_theme or theme_hint)
                geo   = guess_geo(url, ch_region)
                cred  = guess_credibility(typ)

                clean = clean_text(text)
                summary = (clean[:250] + "…") if len(clean) > 250 else clean
                title = extract_title_from_url(url)

                assets.append({
                    "title":       title,
                    "type":        typ,
                    "url":         url,
                    "internal":    None,
                    "summary":     summary,
                    "stage":       stage,
                    "persona":     "",
                    "theme":       theme,
                    "geo":         geo,
                    "effort":      "Ready to use",
                    "credibility": cred,
                    "notes":       f"Shared in #{ch_name} on Slack.",
                    "caveats":     "",
                    "country":     "",
                    "industry":    "",
                    "metrics":     "",
                    "segment":     [],
                    "source":      f"Slack — #{ch_name}",
                    "region":      ch_region,
                    "slackChannel": ch_name,
                    "postedBy":    msg.get("user", ""),
                    "postedAt":    msg.get("ts", ""),
                })
                ch_assets += 1

        print(f"    ✓ {ch_assets} assets extracted")

    return assets

# ── GOOGLE SHEETS ───────────────────────────────────────────────────────────
try:
    from google.auth import default
    from google.auth.transport.requests import Request
    import googleapiclient.discovery
except ImportError:
    print("Installing Google API dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "google-auth", "google-auth-httplib2", "google-api-python-client",
                    "--break-system-packages", "-q"])
    from google.auth import default
    from google.auth.transport.requests import Request
    import googleapiclient.discovery

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

def get_service():
    creds, _ = default(scopes=SCOPES)
    if hasattr(creds, 'refresh'):
        creds.refresh(Request())
    return googleapiclient.discovery.build('sheets', 'v4', credentials=creds)

def get_sheet_name_by_gid(service, spreadsheet_id, gid):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta.get('sheets', []):
        if str(s['properties']['sheetId']) == str(gid):
            return s['properties']['title']
    return None

VALID_STAGES = {'TOFU', 'MOFU', 'BOFU'}

def parse_stage(raw):
    r = raw.upper().strip()
    if 'TOFU' in r or 'TOP OF' in r: return 'TOFU'
    if 'BOFU' in r or 'BOTTOM OF' in r: return 'BOFU'
    if 'MOFU' in r or 'MID' in r: return 'MOFU'
    # Anything else (long phrases, unrecognised values) → MOFU
    return 'MOFU'

def parse_credibility(raw):
    r = raw.upper()
    if 'VERY HIGH' in r or 'EXCEPTIONAL' in r: return 'VERY HIGH'
    if 'HIGH' in r: return 'HIGH'
    if 'LOW' in r: return 'LOW'
    return 'MED'

def parse_segment(raw):
    seg = []
    for s in raw.replace(',', '/').replace(';', '/').split('/'):
        s = s.strip().upper()
        if s in ('MID-MARKET', 'MIDMARKET'): s = 'MM'
        elif s in ('LARGE', 'ENTERPRISE'): s = 'LA'
        if s in ('SMB', 'MM', 'LA'):
            seg.append(s)
    return seg

def parse_url(raw):
    raw = (raw or '').strip()
    return raw if raw.startswith('http') else None

GATED_URL_PATTERNS = [
    r'/resources/', r'/lp/', r'/landing/', r'/form/', r'/gated/',
    r'\.com/go/', r'marketo\.', r'hubspot\.', r'pardot\.',
    r'pages\.shopify', r'/whitepaper', r'/report/',
    r'ey\.com', r'gartner\.com', r'forrester\.com',
    r'hbr\.org', r'mckinsey\.com',
    r'/download/', r'cdn\.shopify\.com/static/plus',
    r'info\.', r'/get/',
]

def is_gated(url):
    if not url: return False
    u = url.lower()
    return any(re.search(p, u) for p in GATED_URL_PATTERNS)

def map_row(headers, row, region, source_name, schema='master'):
    """Map a sheet row to a normalised asset dict, aware of column schema."""
    hlow = [h.lower().strip() for h in headers]

    def col(*keys):
        """Return first non-empty cell whose header contains any of the keys."""
        for key in keys:
            for i, h in enumerate(hlow):
                if key in h:
                    val = row[i] if i < len(row) else ''
                    v = str(val).strip()
                    if v:
                        return v
        return ''

    # ── Schema-specific title / url / type / summary lookups ─────────────
    if schema == 'master':
        title   = col('asset title', 'title', 'name')
        url_raw = col('url', 'link', 'location', 'file')
        typ     = col('asset type', 'type', 'content type', 'format') or 'Asset'
        summary = col('summary', 'description', 'overview', 'brief explanation')
        theme   = col('theme fit', 'theme', 'topic')
        persona = col('persona fit', 'persona', 'audience')
        geo     = col('geo fit', 'geo', 'region', 'market') or region
        effort  = col('effort level', 'effort')
        credibility = parse_credibility(col('credibility strength', 'credibility', 'strength'))
        notes   = col('notes', 'how to use', 'usage')
        caveats = col('risks', 'caveats')
        industry = col('industry', 'vertical', 'sector')
        metrics = col('metrics', 'results', 'outcomes', 'key stats')
        stage   = parse_stage(col('funnel stage', 'stage'))
        segment = parse_segment(col('segment', 'audience size'))

    elif schema == 'audit':
        # Content audit tabs: Funnel Stage, Theme, Content (=title), Hosting,
        # Content Type, Content Details, Status, Post date, File, Notes
        title   = col('content', 'title', 'name')
        url_raw = col('file', 'url', 'link', 'location')
        typ     = col('content type', 'type', 'format') or 'Blog'
        summary = col('content details', 'summary', 'description', 'notes')
        theme   = col('theme', 'topic')
        persona = col('persona', 'audience')
        geo     = col('market', 'country', 'region', 'geo') or region
        effort  = 'Ready to use'
        credibility = 'MED'
        notes   = col('notes and relevance', 'notes', 'how to use')
        caveats = ''
        industry = col('industry', 'vertical', 'sector')
        metrics = ''
        stage   = parse_stage(col('funnel stage', 'stage'))
        segment = []

    elif schema == 'blogs':
        # Enterprise Blogs tabs: Funnel Stage, Title, Summary, Post date, Industry, Link, Topics
        title   = col('title', 'name', 'asset')
        url_raw = col('link', 'url', 'location')
        typ     = 'Enterprise Blog'
        summary = col('summary', 'description', 'overview')
        theme   = col('topics', 'theme', 'topic')
        persona = col('persona', 'audience')
        geo     = region
        effort  = 'Ready to use'
        credibility = 'MED'
        notes   = ''
        caveats = ''
        industry = col('industry', 'vertical', 'sector')
        metrics = ''
        stage   = parse_stage(col('funnel stage', 'stage'))
        segment = []

    elif schema == 'partner':
        # Partner case study tabs: Agency, Title, Industry, Brief Explanation, Market, URL, Direct link
        title   = col('title', 'name')
        url_raw = col('direct link', 'url', 'link')
        typ     = 'Case study'
        summary = col('brief explanation', 'summary', 'description', 'overview')
        theme   = 'Partner Case Study'
        persona = col('persona', 'audience')
        geo     = col('market', 'country', 'region') or region
        effort  = 'Ready to use'
        credibility = 'HIGH'
        notes   = col('shopify products', 'notes')
        caveats = col('prev. platform', 'previous platform', 'caveats')
        industry = col('industry', 'vertical', 'sector')
        metrics = ''
        stage   = 'MOFU'
        segment = []

    elif schema == 'tofu':
        # TOFU shortlist: #, Asset (=title), Type, Funnel Stage, Recommended Package Type,
        # Recommended Publications, Gaps / Localisation / Edits Needed
        title   = col('asset', 'title', 'name', 'content')
        url_raw = col('url', 'link', 'file')
        typ     = col('type', 'content type', 'format') or 'Asset'
        summary = col('gaps', 'notes', 'summary', 'description', 'recommended package')
        theme   = ''
        persona = col('recommended publications', 'persona', 'audience')
        geo     = region
        effort  = col('recommended package', 'effort')
        credibility = 'MED'
        notes   = col('gaps', 'notes', 'how to use')
        caveats = ''
        industry = ''
        metrics = ''
        stage   = parse_stage(col('funnel stage', 'stage'))
        segment = []

    elif schema == 'apac':
        # APAC tracker: Merchant, Status, Country, Segment, Date Published,
        # Previous Platform, Live Article Link, Video link
        title   = col('merchant', 'title', 'name')
        url_raw = col('live article link', 'video link', 'url', 'link')
        typ     = 'Case study'
        summary = col('summary', 'description', 'overview', 'brief explanation')
        theme   = 'Unified Commerce'
        persona = ''
        geo     = col('country', 'market', 'region') or region
        effort  = 'Ready to use'
        credibility = 'HIGH'
        notes   = col('notes', 'how to use')
        caveats = col('previous platform', 'prev. platform')
        industry = ''
        metrics = ''
        stage   = 'MOFU'
        segment = parse_segment(col('segment', 'audience size'))

    else:
        return None

    url = parse_url(url_raw)

    # Skip rows with no title or are clearly meta/instruction rows
    if not title or title.startswith('#') or title.lower().startswith('shopify tofu'):
        return None

    return {
        "title":       title,
        "type":        typ,
        "url":         url,
        "internal":    None if url else (url_raw or None),
        "summary":     summary,
        "stage":       stage,
        "persona":     persona,
        "theme":       theme,
        "geo":         geo,
        "effort":      effort,
        "credibility": credibility,
        "notes":       notes,
        "caveats":     caveats,
        "country":     col('country', 'market') if schema not in ('apac', 'partner') else geo,
        "industry":    industry,
        "metrics":     metrics,
        "segment":     segment,
        "gated":       is_gated(url),
        "status":      "published",
        "source":      source_name,
        "region":      region,
        "slackChannel": "",
    }

def load_sheet(service, source):
    schema = source.get('schema', 'master')
    print(f"  Reading '{source['name']}' [{schema}] (gid={source['gid']})...")
    sheet_name = get_sheet_name_by_gid(service, SPREADSHEET_ID, source['gid'])
    if not sheet_name:
        print(f"  WARNING: Tab not found for gid={source['gid']}, skipping")
        return []

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'"
    ).execute()

    rows = result.get('values', [])
    if len(rows) < 2:
        return []

    # TOFU shortlist has a title row before real headers
    header_row_idx = 1 if schema == 'tofu' else 0
    # APAC tracker often has an empty row 0 before real headers
    if schema == 'apac' and rows and not any(c.strip() for c in rows[0] if c):
        header_row_idx = 1

    headers = [str(h).strip() for h in rows[header_row_idx]]
    data_rows = rows[header_row_idx + 1:]

    assets = []
    for row in data_rows:
        if not row or not str(row[0]).strip():
            continue
        # Capture publish status for audit tabs (no longer skip — show as "Coming Soon")
        row_status = 'published'
        if schema == 'audit':
            status_idx = next((i for i, h in enumerate(headers) if 'status' in h.lower()), None)
            if status_idx is not None and status_idx < len(row):
                raw_status = str(row[status_idx]).strip().lower()
                if raw_status:
                    row_status = raw_status if raw_status in (
                        'published', 'complete', 'completed', 'ready', 'live', 'final'
                    ) else 'draft'
        # Skip APAC rows that are section headers (all caps, no URL data)
        if schema == 'apac' and len(row) < 3:
            continue

        asset = map_row(headers, row, source['region'], source['name'], schema)
        if asset and asset['title']:
            # Skip rows where title or type was incorrectly parsed as a URL
            if asset['title'].startswith('http') or asset['type'].startswith('http'):
                continue
            # Skip note-style rows where someone left a comment in the title field
            _t_lower = asset['title'].lower().strip()
            _note_prefixes = ('new asset -', 'new asset:', 'can you look', 'this too pls', 'todo:', 'todo -', 'placeholder', 'tbd', 'wip -', 'wip:')
            if any(_t_lower.startswith(p) for p in _note_prefixes):
                continue
            asset['status'] = row_status
            assets.append(asset)

    print(f"  ✓ {len(assets)} assets from '{sheet_name}'")
    return assets

# ── SLACK MCP HELPER SCRIPT ─────────────────────────────────────────────────
SLACK_HELPER_PATH = "/tmp/slack_mcp_helper.py"

SLACK_HELPER_CODE = '''#!/usr/bin/env python3
"""
Helper script: calls the Slack MCP server via its HTTP interface to get channel messages.
Usage: python3 slack_mcp_helper.py get_messages <channel_id>
"""
import sys, json, subprocess, os

action  = sys.argv[1]
channel = sys.argv[2]

# Use the Cursor MCP client approach - call via Node.js bridge
# The MCP server info is available from cursor config
mcp_config_path = os.path.expanduser(
    "~/.cursor/projects/Users-shalini-keyan-Cursor-Workspaces-outline/mcps/user-playground-slack-mcp"
)

# Read server instructions to find the endpoint
import glob
server_files = glob.glob(f"{mcp_config_path}/*.json") + glob.glob(f"{mcp_config_path}/**/*.json")

# Fallback: write a curl-based call using the MCP endpoint
# Since we cannot directly call the MCP from Python, we output empty
# and let the main script handle this gracefully
print(json.dumps([]))
'''

def write_slack_helper():
    with open(SLACK_HELPER_PATH, "w") as f:
        f.write(SLACK_HELPER_CODE)

# ── DIRECT SLACK INTEGRATION ────────────────────────────────────────────────
def scrape_slack_direct():
    """
    Since we can't call the Slack MCP directly from Python, we use the
    pre-fetched Slack data embedded here. When you run refresh-assets.py,
    it also calls this function which returns the most recent Slack-sourced
    assets as a snapshot.

    To update: ask the AI assistant to re-scan Slack channels and regenerate
    this section, or add to the Google Sheet manually.
    """
    # These are assets extracted from the 9 Slack channels
    # Automatically generated - re-run refresh with AI to update
    return SLACK_SNAPSHOT

# ── EMBEDDED SLACK SNAPSHOT ─────────────────────────────────────────────────
# Last updated: 2026-03-18 (auto-generated from 9 channels)
SLACK_SNAPSHOT = [
    # ── #case-studies ──────────────────────────────────────────────────────
    {
        "title": "Sea Bags: Unifies 36 Stores, Cuts Platform Costs 20%",
        "type": "Case study", "url": "https://www.shopify.com/case-studies/sea-bags",
        "internal": None,
        "summary": "Sea Bags switched from Clover POS + Salesforce Commerce Cloud to Shopify, unifying 36 retail locations. 20% reduction in platform fees ($70K annual savings), 1,200 customer emails captured per week at POS checkout, 47% email opt-in rate. Great for Clover compete conversations.",
        "stage": "MOFU", "persona": "CIO/CTO · Head of Retail", "theme": "Unified Commerce",
        "geo": "Global", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Especially useful for Clover compete conversations. Seismic: https://shopify.seismic.com/Link/Content/DCbh8gBJf9QJ28QFq3cDV93F7pmP",
        "caveats": "", "country": "USA", "industry": "Retail / Accessories", "metrics": "20% cost reduction; 47% email opt-in; 36 stores unified",
        "segment": ["MM", "LA"], "source": "Slack — #case-studies", "region": "Global", "slackChannel": "case-studies"
    },
    {
        "title": "Faherty: Unifies 80+ Stores, Slashes Costs, Unlocks BOPIS",
        "type": "Enterprise Blog", "url": "https://www.shopify.com/enterprise/blog/faherty-unified-commerce",
        "internal": None,
        "summary": "Premium apparel brand Faherty ditched fragmented stack (Shopify online + NewStore retail). Deployed 80+ stores in 3 months with remote setup. Unlocked BOPIS and ship-from-store. Support calls reduced to quick messages. One unified catalog eliminated pricing mismatches.",
        "stage": "MOFU", "persona": "CIO/CTO · Head of IT · COO", "theme": "Unified Commerce",
        "geo": "Global", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Strong unified commerce proof point. Seismic: https://shopify.seismic.com/app?ContentId=33821828-4813-449f-bb2b-098cb1b6c170",
        "caveats": "", "country": "USA", "industry": "Apparel", "metrics": "80+ stores in 3 months; eliminated hourly support calls",
        "segment": ["MM", "LA"], "source": "Slack — #case-studies", "region": "Global", "slackChannel": "case-studies"
    },
    {
        "title": "ALDO Group: Three Brands Launched in Nine Months",
        "type": "Case study", "url": "https://www.shopify.com/case-studies/aldo-group",
        "internal": None,
        "summary": "ALDO launched three brands in under nine months — on time, on scope, on budget. +20% YoY conversion increase in first 2 months. Reduced release process from hours to seconds with instant deployments.",
        "stage": "MOFU", "persona": "CIO/CTO · VP Digital Product", "theme": "Scalability",
        "geo": "Global", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Seismic full URL: https://shopify.seismic.com/Link/Content/DCbF43MQBBXdJ8MDfPDTcgmqQJTj | Seismic slide: https://shopify.seismic.com/Link/Content/DCcXpqh227BJGG9XfbFFcG66BQM3",
        "caveats": "", "country": "Canada", "industry": "Fashion / Footwear", "metrics": "+20% YoY conversion; 3 brands in <9 months",
        "segment": ["LA"], "source": "Slack — #case-studies", "region": "Global", "slackChannel": "case-studies"
    },
    {
        "title": "David's Bridal: Complete Replatform in 9 Months",
        "type": "Case study", "url": "https://www.shopify.com/case-studies/davids-bridal",
        "internal": None,
        "summary": "75-year-old wedding retailer needed a complete overhaul — 'change or die'. Complete replatform, Canada launch, new concept store, and first-of-its-kind interactive screens powered by Shopify POS, all in 9 months. Featured in Time to Value campaign.",
        "stage": "MOFU", "persona": "CEO · CIO/CTO", "theme": "Unified Commerce",
        "geo": "Global", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Featured in Time to Value campaign. Use for risk-of-standing-still narrative.",
        "caveats": "", "country": "USA", "industry": "Retail / Bridal", "metrics": "Full replatform in 9 months",
        "segment": ["LA"], "source": "Slack — #case-studies", "region": "Global", "slackChannel": "case-studies"
    },
    {
        "title": "Healf: Triples Revenue in a Year, Scales to 5,000+ SKUs",
        "type": "Case study", "url": "https://www.shopify.com/case-studies/healf",
        "internal": None,
        "summary": "UK health tech brand Healf built on Shopify from day one. 3x revenue in a single year, 500%+ three-year CAGR, 5,000+ SKUs from 250 at launch. Team grew from 7 to 100+. Extending into AI-powered membership and new markets.",
        "stage": "MOFU", "persona": "CEO · Head of Digital", "theme": "Scalability",
        "geo": "Global", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Good for health & wellness vertical. Seismic: https://shopify.seismic.com/Link/Content/DCVB8P822THQd8CGGCj8c9V8b7Wd",
        "caveats": "", "country": "UK", "industry": "Health & Wellness", "metrics": "3x revenue; 500%+ CAGR; 5,000+ SKUs",
        "segment": ["MM"], "source": "Slack — #case-studies", "region": "Global", "slackChannel": "case-studies"
    },
    # ── #ai-h1-campaign-project ────────────────────────────────────────────
    {
        "title": "GEO Playbook: Generative Engine Optimization",
        "type": "Enterprise Blog", "url": "https://www.shopify.com/enterprise/blog/generative-engine-optimization",
        "internal": None,
        "summary": "First major blog post in the H1 2026 AI Campaign. Thought leadership on Generative Engine Optimization (GEO) — how brands can optimize their content to be discovered by AI-powered search engines. Strong social reaction on launch.",
        "stage": "TOFU", "persona": "Head of Marketing · CMO · Head of Digital", "theme": "AI",
        "geo": "Global", "effort": "Ready to use", "credibility": "MED",
        "notes": "Part of H1 2026 AI Campaign. Content hub: https://ai-campaign-hub.quick.shopify.io/",
        "caveats": "", "country": "", "industry": "", "metrics": "",
        "segment": ["MM", "LA"], "source": "Slack — #ai-h1-campaign-project", "region": "Global", "slackChannel": "ai-h1-campaign-project"
    },
    {
        "title": "Aviator Nation Blog: AI Unified Commerce Data Insights",
        "type": "Enterprise Blog", "url": "https://www.shopify.com/enterprise/blog/ai-unified-commerce-data-insights",
        "internal": None,
        "summary": "Thought leadership on why unified commerce data is the foundation for AI that actually works. Features Sidekick capabilities + quotes from Curtis Ulrich (Aviator Nation Director of Ecommerce). Key example: Sidekick revealed 23% higher LTV for customers with retail touchpoints. Used in LinkedIn/DemandBase paid ads.",
        "stage": "TOFU", "persona": "CIO/CTO · Head of Digital · CMO", "theme": "AI; Unified Commerce",
        "geo": "Global", "effort": "Ready to use", "credibility": "MED",
        "notes": "Has CTA to AI webinar. Being promoted via LinkedIn and DemandBase ads to MM/LA in AMER.",
        "caveats": "", "country": "USA", "industry": "Apparel", "metrics": "23% higher LTV for retail-touchpoint customers",
        "segment": ["MM", "LA"], "source": "Slack — #ai-h1-campaign-project", "region": "Global", "slackChannel": "ai-h1-campaign-project"
    },
    {
        "title": "[Webinar] AI for Commerce Teams: Offload Busy Work and Grow Faster",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/ai-for-commerce-teams",
        "internal": None,
        "summary": "On-demand webinar from the H1 AI Campaign. 1,081 total registrations, 412 live attendees (38% view rate, above average). Covers practical AI tools for commerce teams. Features Sidekick product demos.",
        "stage": "MOFU", "persona": "CMO · Head of Marketing · Head of Digital", "theme": "AI",
        "geo": "Global", "effort": "Ready to use", "credibility": "MED",
        "notes": "Now available on demand. 38% live attendance rate (above average benchmark).",
        "caveats": "", "country": "", "industry": "", "metrics": "1,081 registrants; 412 live attendees; 38% view rate",
        "segment": ["MM", "LA"], "source": "Slack — #ai-h1-campaign-project", "region": "Global", "slackChannel": "ai-h1-campaign-project"
    },
    {
        "title": "[Webinar] Beyond the AI Hype: How Brands Build for Agentic Commerce",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/ai-agentic-commerce-established-brands",
        "internal": None,
        "summary": "Webinar for Large Accounts + Enterprise. Practical, actionable content with real-world demos of Sidekick analytics, SimGym, custom app builds, Flow, UCP, and agentic storefronts. Air date: March 18, 2026. Speakers from Shopify's leadership.",
        "stage": "MOFU", "persona": "CIO/CTO · VP Engineering · Head of Digital", "theme": "AI",
        "geo": "Global", "effort": "Ready to use", "credibility": "MED",
        "notes": "Enablement hub: https://la-ent-ai-webinar-enable.quick.shopify.io/ — includes ready-to-share social posts for Sales & CS.",
        "caveats": "", "country": "", "industry": "", "metrics": "",
        "segment": ["LA"], "source": "Slack — #ai-h1-campaign-project", "region": "Global", "slackChannel": "ai-h1-campaign-project"
    },
    {
        "title": "[Webinar] A Practical Guide to AI Discovery",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/ai-discovery",
        "internal": None,
        "summary": "On-demand webinar from the H1 AI Campaign. Available now. Part of the Shopify AI commerce content series.",
        "stage": "TOFU", "persona": "CMO · Head of Marketing", "theme": "AI",
        "geo": "Global", "effort": "Ready to use", "credibility": "MED",
        "notes": "On-demand only. Part of AI campaign content series.",
        "caveats": "", "country": "", "industry": "", "metrics": "",
        "segment": ["SMB", "MM"], "source": "Slack — #ai-h1-campaign-project", "region": "Global", "slackChannel": "ai-h1-campaign-project"
    },
    # ── #unified-commerce-midmarket-campaign ───────────────────────────────
    {
        "title": "Retail's Digital Transformation: From Integration to Unification (Blog)",
        "type": "Enterprise Blog", "url": "https://www.shopify.com/enterprise/blog/retail-tech-trap-integration-vs-unification",
        "internal": None,
        "summary": "Shopify Field CTO team reveals why most 'unified' retail solutions fail. True unified commerce isn't just about connecting systems — it's about eliminating the need for those connections entirely. Features KEEN (80% TCO reduction), Mejuri, Parachute. Stats: 25% less maintenance, 27% less middleware, 89% less third-party support, 8.9% GMV uplift.",
        "stage": "TOFU", "persona": "CIO/CTO · VP Engineering · COO", "theme": "Fragmentation/Integration; Unified Commerce",
        "geo": "Global", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Strong thought leadership piece from Field CTO team. Companion to the Retail Digital Transformation Report.",
        "caveats": "", "country": "", "industry": "Retail", "metrics": "25% less maintenance; 27% less middleware; 89% less 3P support; 8.9% GMV uplift",
        "segment": ["MM", "LA"], "source": "Slack — #unified-commerce-midmarket-campaign", "region": "Global", "slackChannel": "unified-commerce-midmarket-campaign"
    },
    # ── Shopify AU Webinars (additional 6) ─────────────────────────────────────
    {
        "title": "Shopify's Winter '25 Edition Webinar (AU)",
        "type": "Webinar", "url": "https://www.shopify.com/au/webinar/au-winter-25-edition?country=au&lang=en",
        "internal": None,
        "summary": "Australian edition of Shopify's Winter '25 product update. Covers new platform features and capabilities relevant to AU merchants.",
        "stage": "TOFU", "persona": "Head of eCommerce · CTO · Digital Product", "theme": "Innovation",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "AU-specific Winter '25 edition — use over the global version for ANZ accounts.",
        "caveats": "", "country": "Australia", "industry": "Multi-industry",
        "segment": ["SMB", "MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Deliver Self-Serve Experiences for Modern B2B Buyers (AU)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/au-b2b-commerce",
        "internal": None,
        "summary": "Australian B2B webinar on delivering self-serve buying experiences on Shopify. Covers B2B buyer portals, self-serve ordering, and modern B2B commerce capabilities.",
        "stage": "MOFU", "persona": "Head of B2B · VP Sales · Head of eCommerce", "theme": "B2B",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Australia-specific B2B webinar. Great for merchants exploring B2B on Shopify Plus. Part of the APAC B2B workshop series.",
        "caveats": "", "country": "Australia", "industry": "B2B / Wholesale",
        "segment": ["MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Introduction to B2B on Shopify Plus: Workshop 1 (APAC)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/apac-b2b-workshop-1",
        "internal": None,
        "summary": "APAC Workshop 1 of 3: Introduction to B2B on Shopify Plus. Covers core B2B features, account management, and getting started with wholesale on Shopify Plus.",
        "stage": "TOFU", "persona": "Head of B2B · VP Sales · Head of eCommerce", "theme": "B2B",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Start here for B2B conversations. Part 1 of 3-part APAC B2B workshop series.",
        "caveats": "", "country": "Australia", "industry": "B2B / Wholesale",
        "segment": ["MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Deep Dive on Shopify's B2B Features: Workshop 2 (APAC)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/apac-b2b-workshop-2",
        "internal": None,
        "summary": "APAC Workshop 2 of 3: Deep dive on Shopify B2B — pricing rules, customer accounts, payment terms, and catalog management.",
        "stage": "MOFU", "persona": "Head of B2B · IT Lead · Head of eCommerce", "theme": "B2B",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Part 2 of the APAC B2B workshop series. Use after Workshop 1 for deeper evaluation conversations.",
        "caveats": "", "country": "Australia", "industry": "B2B / Wholesale",
        "segment": ["MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Overview of Sales Staff Features: Workshop 3 (APAC)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/apac-b2b-workshop-3",
        "internal": None,
        "summary": "APAC Workshop 3 of 3: Sales staff features on Shopify Plus B2B — managing sales reps, assigning accounts, and enabling field sales teams.",
        "stage": "MOFU", "persona": "Head of B2B · VP Sales · Sales Operations", "theme": "B2B",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Part 3 of the APAC B2B workshop series. Best for merchants with field sales teams or complex B2B org structures.",
        "caveats": "", "country": "Australia", "industry": "B2B / Wholesale",
        "segment": ["MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "How to Increase Your Site Speed by Up to 2.4x (AU)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/au-compare-sitespeed",
        "internal": None,
        "summary": "Australian webinar on improving Shopify store performance — up to 2.4x faster. Covers platform performance benchmarks and the conversion impact of site speed.",
        "stage": "TOFU", "persona": "CTO · Head of eCommerce · Digital Product", "theme": "Innovation",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "MEDIUM",
        "notes": "Good for technical platform performance conversations. AU edition — use over UK/US versions for ANZ accounts.",
        "caveats": "", "country": "Australia", "industry": "Multi-industry",
        "segment": ["SMB", "MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    # ── Manual additions ────────────────────────────────────────────────────────
    {
        "title": "Australia eCom Report Partner Toolkit",
        "type": "Toolkit / Campaign Asset",
        "url": "https://drive.google.com/file/d/1_533kzxAj_QnUuesj43Bu5-FcQWryg1B/view",
        "internal": None,
        "summary": "Shopify's digital activation toolkit for the Australia Post eCommerce Report 2026. Ready-to-use eDM, LinkedIn, Meta and Facebook copy + campaign images (1:1, 4:5, eDM banner, website banner). Features Shaun Broughton's take on agentic commerce and AI-driven shopping for Australian retailers.",
        "stage": "TOFU",
        "persona": "CMO · Head of eCommerce · Marketing Manager",
        "theme": "AI",
        "geo": "ANZ",
        "effort": "Ready to use",
        "credibility": "HIGH",
        "notes": "Use eDM or LinkedIn copy directly for merchant outreach. Pairs with AusPost 2026 report. Produced by AusPost partnerships team — contact partners@auspost.com.au for support.",
        "caveats": "Internal Shopify partner toolkit — not for public distribution",
        "country": "Australia",
        "industry": "Retail / eCommerce",
        "metrics": "",
        "segment": ["SMB", "MM", "LA"],
        "source": "AusPost / Shopify ANZ",
        "region": "ANZ",
        "slackChannel": ""
    },
    # ── Shopify Connect Sydney 2026 — LinkedIn Posts ────────────────────────────
    {
        "title": "Shopify Connect Sydney — Peyman Naeini (Agentic Commerce)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Peyman Naeini at Shopify Connect Sydney. Covers agentic commerce, the shift from attention-based to execution-based economy, Universal Commerce Protocol, and why data is the key unlock for AI commerce.",
        "stage": "TOFU", "persona": "CTO · Head of Digital · CMO", "theme": "AI",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Thu 26 Mar, 1pm AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
Great to be in Sydney this week at [@]Shopify's Connect event, sharing how quickly the role of technology in commerce is evolving.
We're at an inflection point.
For years, machine learning has helped us analyse data. Now, with generative AI and large language models, we're seeing systems that can create, decide, and increasingly, act.
This is what's driving the shift toward agentic commerce.
A few perspectives I shared:
The "end customer" is no longer just human – AI agents are now part of the buying journey.
We're moving from an attention-based economy to an execution-based one.
AI should be treated as a core business channel, not an experiment.
We're also seeing important infrastructure emerge, like the Universal Commerce Protocol, helping standardise how AI systems interact across the entire commerce journey, from discovery through to transaction.
But the biggest thing unlocking value for businesses isn't the technology itself.
It's data.
If your product, pricing, and brand data isn't structured, accurate, and real-time, AI systems won't be able to represent you properly – or transact on your behalf.
As AI becomes another interface to commerce, the question shifts from "how do we use AI" to:
👉 "Are we ready for AI to act for us?"
This shift is already underway.
#AI #Commerce #Shopify #ShopifyConnect #AgenticCommerce #FutureOfRetail""",
        "caveats": "Tag @Shopify when posting. Select photo from SYD Rush Selects folder.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Jason Bowman (AI Discovery Stats)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Jason Bowman at Shopify Connect Sydney. Covers AI-driven customer journey, key stats (43% using generative AI, 39% using AI for purchase decisions, 38% using AI search), and structured product data as the key to AI discoverability.",
        "stage": "TOFU", "persona": "Head of eCommerce · CMO · CTO", "theme": "AI",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Thu 26 Mar, 3pm AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
The customer journey has become more complex, more fragmented, and increasingly influenced by AI.
At [@]Shopify Connect, I broke down what that looks like in practice.
Customers now expect to move from question to recommendation to purchase in a single, seamless interaction, rather than across multiple steps and channels.
And this is already happening:
43% are using generative AI
39% are using AI to support purchase decisions
38% are using AI search instead of traditional search
The shift has real implications for how brands are discovered.
It's no longer just about ranking, but whether you're present in these AI-driven interactions at all.
Which comes back to structure.
Your catalogue becomes the source of truth, and how well your product data, metafields and content are mapped determines whether AI systems can understand and surface what you sell.
If that layer isn't in place, you simply won't appear.
The opportunity is significant, both in driving revenue and improving efficiency, but it depends on getting the fundamentals right.
#Shopify #ShopifyConnect #Commerce #AI #AgenticCommerce""",
        "caveats": "Stats (43%/39%/38%) are from Shopify data — confirm source before external use. Tag @Shopify.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Amanda Johnstone / Transhuman (AI & People)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Amanda Johnstone (Transhuman) at Shopify Connect Sydney. Human-first take on AI — AI gives time back to build better customer connections. Don't wait for perfection, start testing.",
        "stage": "TOFU", "persona": "CMO · Founder · Head of Innovation", "theme": "AI",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Thu 26 Mar, 4pm AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
What a wild ride speaking at [@]Shopify's Connect event in Sydney 🎤
I shared a bit of my story (Tassie, no uni, figuring things out as I went 😅) and how that's shaped how I think about AI.
Because here's the thing…
AI isn't the point. People are.
AI just gives us more time back – to understand customers more deeply, build better experiences, and create real connections.
But only if we stay close to the human.
Some of the best insights I've found haven't come from dashboards. They've come from observing behaviour, spotting patterns, and looking outside the category.
That's where the opportunity sits ✨
If there's one thing I'd leave people with:
Don't wait for permission.
Don't wait for perfection.
Start building. Start testing. Stay curious.
The future's already happening – you just have to look for it.
#AI #Innovation #FutureOfCommerce #ShopifyConnect""",
        "caveats": "External speaker post — tag @Shopify and @Transhuman where appropriate.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["SMB", "MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — WGAC (Simplifying Tech Stack)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Who Gives a Crap (WGAC) at Shopify Connect Sydney. Covers managing complexity at scale, reducing 'commercial debt' from layered tech, and how simplification unlocks growth.",
        "stage": "MOFU", "persona": "CTO · COO · Head of eCommerce", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Fri 27 Mar, 9am AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
Great to be part of the conversation at [@]Shopify's Connect event in Sydney.
As we've scaled, one of the biggest challenges hasn't been growth – it's been managing complexity.
Over time, it's easy to build up layers of tech and process that start to create what we'd call "commercial debt", where even simple questions take too long to answer.
A big focus for us has been simplifying that.
Bringing things back to a smaller set of core platforms, reducing manual work, and making it easier for teams to access and use data without needing multiple steps or workarounds.
That shift has unlocked real value for us as a company and a brand.
Less time spent on admin. More time spent improving the customer experience.
It also changes how teams operate.
When systems are simpler, teams move faster, make better decisions, and avoid creating new complexity on top.
Growth doesn't come from adding more. It comes from simplifying what's already there.
#Shopify #ShopifyConnect #Ecommerce #Retail #Growth""",
        "caveats": "Merchant post — tag @WhoGivesACrap and @Shopify.",
        "country": "Australia", "industry": "Retail / DTC",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Shaun Broughton (AI as Growth Driver)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Shaun Broughton (MD, Shopify) at Shopify Connect Sydney. AI is moving from novelty to practical growth driver. Businesses moving fastest have unified tech stacks and strong operational foundations.",
        "stage": "TOFU", "persona": "CEO · CTO · Head of eCommerce · CMO", "theme": "AI",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Fri 27 Mar, 12pm AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
I repeatedly come across a consistent theme from conversations with retailers: how to grow without adding unnecessary complexity.
At [@]Shopify's Connect event in Sydney, I spoke about how this is shaping decision-making across technology and AI.
There's been a clear shift in mindset. AI is no longer viewed as a novelty, but as a practical driver of growth – with real orders already being attributed to AI-driven interactions.
What stands out is that the businesses moving fastest aren't defined by size or industry, but by having strong operational foundations and a unified technology stack that gives them visibility across business.
That's what enables speed, without disrupting existing systems or revenue streams.
Our focus is to give merchants the tools, confidence and clarity to move faster in a rapidly evolving landscape – without adding complexity.
While the tools are changing quickly, the fundamentals of commerce remain the same.
#Shopify #ShopifyConnect #Commerce #AI #Retail""",
        "caveats": "High-credibility post from Shopify MD — prioritise sharing. Tag @Shopify.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — James Johnson (Unified Commerce Baseline)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from James Johnson at Shopify Connect Sydney. Unified commerce is now the baseline, not a differentiator. Covers generative engine optimisation (GEO), single customer view, and cross-channel experience.",
        "stage": "TOFU", "persona": "Head of eCommerce · CTO · Head of Retail", "theme": "Unified Commerce",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Fri 27 Mar, 4pm AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
Customer expectations aren't just increasing, they're changing shape.
At [@]Shopify's Connect event in Sydney, I spent time unpacking what growth looks like in an increasingly agentic commerce landscape.
Customers no longer think in channels. They shop in moments – across store, online, social, and now AI-driven experiences – expecting brands to be present and relevant whenever those moments occur.
That's raising the bar.
Unified commerce is no longer a differentiator, it's the baseline. Delivering on that requires a single view of the customer, connected systems across every touchpoint, and the operational alignment behind it. Capabilities like cross-channel returns are quickly becoming standard.
But meeting these expectations isn't simple. It requires coordination across teams, ongoing investment in operations, and the ability to continuously adapt as expectations keep rising.
At the same time, discovery is evolving.
We're moving from traditional SEO to generative engine optimisation – where visibility depends on how well your product data, content and knowledge base can be understood and surfaced by AI.
📈 The opportunity is clear: brands that get this right unlock growth and loyalty
⚙️ The challenge is execution across systems, teams and data
It starts with a strong foundation.
#Shopify #ShopifyConnect #Commerce #AI #UnifiedCommerce""",
        "caveats": "Tag @Shopify. Strong GEO (generative engine optimisation) narrative — useful for AI conversations.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Gareth Davies (AI to Commercial Outcomes)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Gareth Davies at Shopify Connect Sydney. AI shifting from experimentation to real commercial outcomes. Compressed customer journey — discovery, decision and transaction converging.",
        "stage": "TOFU", "persona": "CTO · Head of Digital · CFO", "theme": "AI",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Mon 30 Mar, 9am AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
Spent the day at [@]Shopify's Connect event in Sydney yesterday with teams, partners, and retailers across the ecosystem.
What stood out wasn't just the pace of AI adoption, but how quickly it's moving from experimentation to driving real commercial outcomes.
At the same time, the core challenge hasn't changed: how to accelerate growth without adding unnecessary complexity or risk.
The businesses moving fastest are solving this through strong operational foundations, unified systems, and clear visibility across their operations.
What is changing is the customer journey. It's becoming more compressed and increasingly shaped by AI, bringing discovery, decision and transaction closer together.
That shift raises a more immediate question for businesses:
Are you set up to capture demand when it happens, wherever it happens?
#Shopify #ShopifyConnect #Commerce #AI #Retail""",
        "caveats": "Tag @Shopify. Post goes Monday — schedule in advance.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Ankita Agarwal (AI Agents & Commerce Infrastructure)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Ankita Agarwal at Shopify Connect Sydney. AI agents bridging the gap between discovery and decision. Brands still own the customer relationship — AI is infrastructure, not replacement.",
        "stage": "TOFU", "persona": "CTO · Head of eCommerce · Head of Digital", "theme": "AI",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Mon 30 Mar, 4pm AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
One of the biggest inefficiencies in commerce today sits between discovery and decision.
Customers are spending more time researching, comparing and evaluating, often without reaching a confident purchase.
At [@]Shopify's Connect event in Sydney, I spoke about how AI agents are starting to address this gap.
By handling research, making recommendations, and executing transactions, they help compress the distance between intent and action, creating a more seamless experience for users.
Importantly, this doesn't change the role of the brand.
Brands still own the customer relationship, the transaction and the overall experience. AI acts as an infrastructure layer that enables better interactions, not a replacement for them.
For businesses, this shifts the focus to fundamentals, such as:
Data needs to be accurate, structured and complete
User intent needs to be clearly captured
Signals like price and availability remain critical
Because the effectiveness of these systems depends entirely on how well they can understand and represent what you offer.
The opportunity is to reduce friction and better capture demand as it emerges.
#Shopify #ShopifyConnect #AI #Commerce #Google #Ecommerce""",
        "caveats": "Tag @Shopify and @Google (Google appears in hashtags — confirm if Google was a co-presenter).",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Oz Hair & Beauty (Speed to Learn)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Oz Hair & Beauty at Shopify Connect Sydney. Speed only matters if the org is set up to support it. Removing friction so teams can test, learn and move fast without being blocked.",
        "stage": "MOFU", "persona": "COO · Head of eCommerce · CTO", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Tue 31 Mar, 9am AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
Speed only matters if your organisation is set up to support it.
That was a big takeaway for us at [@]Shopify's Connect event in Sydney.
As the business grows, it is easy for complexity to creep in. More tools, more integrations, more layers. Before long, even simple changes start taking too long.
For us, the focus has been on removing that friction.
Creating an environment where teams can move quickly, test ideas, and make changes without being blocked by systems or processes.
Because the real advantage is not just speed.
It is how quickly you can learn.
Try something.
See what works.
Double down or move on.
That only happens when teams are empowered to act.
And as you scale, staying disciplined becomes just as important.
Not every idea needs to be pursued.
Not every tool needs to be added.
The businesses that move fastest are often the ones doing less, but doing it better.
#Shopify #ShopifyConnect #Ecommerce #Retail #Growth""",
        "caveats": "Merchant post — tag @OzHairAndBeauty and @Shopify.",
        "country": "Australia", "industry": "Health & Beauty",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Nadine Coady (AI & Marketing Foundations)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Nadine Coady at Shopify Connect Sydney. As AI shapes discovery and decision, marketing wins come from foundations — clear positioning, strong product data, content that answers customer needs.",
        "stage": "TOFU", "persona": "CMO · Head of Marketing · Head of eCommerce", "theme": "AI",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """POST SCHEDULE: Tue 31 Mar, 12pm AEDT
PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
Really energising to spend the day at [@]Shopify's Connect event in Sydney.
What stood out for me was what all of this means for marketing.
As AI starts to influence more of the discovery and decision process, the way brands show up is changing.
It is no longer just about campaigns or channels. It is about how clearly your brand, products and content can be understood and surfaced in the moments that matter.
That puts a much bigger focus on foundations, like:
Clear positioning
Strong product data
Content that actually answers customer needs
Because that is what gets picked up, interpreted and ultimately recommended.
There is a lot changing, but it is creating a real opportunity for marketing teams to have a bigger impact across the entire customer journey.
Excited for what comes next 🚀
#Shopify #ShopifyConnect #Marketing #AI #Ecommerce""",
        "caveats": "Tag @Shopify. Strong CMO/marketing persona post.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    {
        "title": "Shopify Connect Sydney — Tricia Fallows (Panel Host: Simplify to Scale)",
        "type": "Social / LinkedIn",
        "url": "https://docs.google.com/document/d/1p4NbOaDOiDQrdjrheNMhrvO0YJYGLqEcYQdlQJ2B-k8/edit",
        "internal": None,
        "summary": "LinkedIn post from Tricia Fallows (Shopify panel host) at Shopify Connect Sydney. Panel with The Body Shop, Who Gives a Crap and Oz Hair & Beauty on unified systems, simplification, and speed to test and learn.",
        "stage": "TOFU", "persona": "CEO · COO · Head of eCommerce · CMO", "theme": "Unified Commerce",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """PHOTOS: https://drive.google.com/drive/folders/1i_NqL1uERONt4GK4OeTsFi22422pF2Y_ (SYD Photos - Rush Selects)

---
Loved hosting the [@]Shopify Connect panel in Sydney with @The Body Shop, @Who Gives a Crap and @Oz Hair & Beauty.
What stood out was how aligned these businesses are on where to focus.
The pace of change is only increasing, but the response isn't adding more tech or complexity – it's simplifying.
Unified systems. Fewer integrations. A single view of the customer.
That's what's enabling teams to move faster, make better decisions, and deliver more consistent experiences.
There was also a strong focus on how teams operate.
Speed comes from being comfortable testing, learning, and making decisions without waiting for everything to be perfect – while staying disciplined on what actually drives value for the customer.
Really exciting to hear firsthand how these brands are driving the next phase of growth!
#AI #Innovation #FutureOfCommerce #Shopify #ShopifyConnect #UnifiedCommerce""",
        "caveats": "Tag @TheBodyShop @WhoGivesACrap @OzHairAndBeauty @Shopify. No scheduled time — post when ready.",
        "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Connect Sydney 2026", "region": "ANZ"
    },
    # ── Shopify AU Webinars ─────────────────────────────────────────────────────
    {
        "title": "Shopify's Summer '25 Edition | APAC",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/summer-25-edition-au",
        "internal": None,
        "summary": "On-demand APAC edition of Shopify's Summer '25 product update. Covers the latest Shopify innovations for Australian, NZ and broader APAC merchants.",
        "stage": "TOFU", "persona": "Head of eCommerce · CTO · Digital Product", "theme": "Innovation",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Good intro asset for merchants curious about latest Shopify capabilities. ANZ/APAC-specific edition — preferred over the global version for AU conversations.",
        "caveats": "", "country": "Australia", "industry": "Multi-industry",
        "segment": ["SMB", "MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Level Up: Bydee's Journey to Shopify Plus",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/upgradetoplus-firesidechat",
        "internal": None,
        "summary": "Fireside chat with Bydee (Australian swimwear brand) on their journey upgrading to Shopify Plus. Covers scaling challenges, platform migration, and growth outcomes.",
        "stage": "MOFU", "persona": "Head of eCommerce · Founder · CMO", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Strong ANZ peer proof point for Plus upgrade conversations. Bydee is a well-known AU DTC brand — great for SMB/MM upgrade discussions.",
        "caveats": "", "country": "Australia", "industry": "Fashion / Apparel",
        "segment": ["SMB", "MM"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Are You Ready to Upgrade? (AU)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/upgradetoplus",
        "internal": None,
        "summary": "Australia-targeted webinar helping merchants evaluate when and how to upgrade to Shopify Plus. Covers feature unlock, ROI, and migration pathway.",
        "stage": "MOFU", "persona": "Head of eCommerce · Founder · CFO", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Use for Plus upgrade conversations with AU merchants on basic Shopify. Pairs well with Bydee fireside chat.",
        "caveats": "", "country": "Australia", "industry": "Multi-industry",
        "segment": ["SMB", "MM"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "True Checkout Customization with Rebuy (APAC)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/rebuy-apac",
        "internal": None,
        "summary": "Australia-specific webinar on checkout customization using Rebuy. Covers upsell widgets, cart-based recommendations, and conversion optimization via Shopify checkout extensibility.",
        "stage": "MOFU", "persona": "Head of eCommerce · CRO · Digital Product", "theme": "Unified Commerce",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "MEDIUM",
        "notes": "Good for checkout-focused conversations. APAC edition — use this over the EMEA version for ANZ accounts.",
        "caveats": "Features Rebuy (3P app) — not a pure Shopify-native demo", "country": "Australia", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Unlock Growth: Future-proof Your Commerce Strategy with Shopify (AU)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/efficient-growth-levers-au",
        "internal": None,
        "summary": "Australian webinar covering how merchants can future-proof their commerce strategy using Shopify. Focuses on efficiency, growth levers, and scalable commerce infrastructure.",
        "stage": "TOFU", "persona": "CMO · Head of eCommerce · CFO", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Broad strategic webinar — good for early-stage pipeline and account planning. Australia-specific edition.",
        "caveats": "", "country": "Australia", "industry": "Multi-industry",
        "segment": ["SMB", "MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Unlock the Power of Unified Commerce (AU)",
        "type": "Webinar", "url": "https://www.shopify.com/webinar/introduction-to-unified-commerce-au",
        "internal": None,
        "summary": "Australia-specific introduction to unified commerce with Shopify POS. Covers connecting online and in-store, inventory unification, and omnichannel customer journeys.",
        "stage": "TOFU", "persona": "Head of Retail · CTO · Head of eCommerce", "theme": "Unified Commerce",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Ideal intro asset for retail merchants exploring unified commerce. AU edition — use over the US/CA version for ANZ accounts. Pairs with Shopify POS case studies.",
        "caveats": "", "country": "Australia", "industry": "Retail",
        "segment": ["MM", "LA"], "source": "Shopify Webinars AU", "region": "ANZ"
    },
    {
        "title": "Australia Post Inside Australian Online Shopping Report 2026",
        "type": "Report / Whitepaper",
        "url": "https://auspost.com.au/content/dam/ecommerce-report/australia-post-ecommerce-report-2026.pdf",
        "internal": None,
        "summary": "Australia Post's annual eCommerce report tracking Australian online shopping trends, category growth, delivery preferences, and consumer behaviour for 2026. Essential third-party ANZ market validation.",
        "stage": "TOFU",
        "persona": "CMO · Head of eCommerce · CFO · Digital Strategy",
        "theme": "Unified Commerce",
        "geo": "ANZ",
        "effort": "Ready to use",
        "credibility": "HIGH",
        "notes": "Strong ANZ market credibility. Use to anchor conversations about Australian eCommerce growth. Pairs well with Shopify ANZ case studies. Third-party — not Shopify-branded.",
        "caveats": "Third-party (AusPost) report — use as market context, not Shopify proof point",
        "country": "Australia",
        "industry": "Retail / eCommerce",
        "metrics": "",
        "segment": ["SMB", "MM", "LA"],
        "source": "AusPost",
        "region": "ANZ",
        "slackChannel": ""
    },
    {
        "title": "Shopify Enterprise Product Demos — AU",
        "type": "Demo / Webinar",
        "url": "https://www.shopify.com/au/resources/enterprise/product-demos",
        "internal": None,
        "summary": "Watch Shopify's enterprise product demos for Australia: checkout extensibility (AOV + conversion), platform overview, enterprise features (intelligent upselling), and integration ecosystem. Each demo is ~4 mins. Covers checkout UI extensions, dynamic checkout flows, trust badges, and cart-based recommendations.",
        "stage": "TOFU",
        "persona": "CIO/CTO · Head of eCommerce · Digital Product",
        "theme": "Unified Commerce",
        "geo": "ANZ",
        "effort": "Ready to use",
        "credibility": "HIGH",
        "notes": "Official Shopify AU enterprise demo hub. Great for early-stage conversations or pre-meeting prep. Covers: Checkout Extensibility, Platform Overview, Enterprise Features, Integration Ecosystem.",
        "caveats": "",
        "country": "Australia",
        "industry": "Multi-industry",
        "metrics": "",
        "segment": ["SMB", "MM", "LA"],
        "source": "Shopify.com/au",
        "region": "ANZ",
        "slackChannel": ""
    },
    # ── #ext-archetype-case-studies ────────────────────────────────────────────
    {
        "title": "Bombay Shaving Company: Scaling D2C Commerce with Shopify",
        "type": "Case study", "url": None,
        "internal": "Google Doc — awaiting publication",
        "summary": "ANZ/India D2C grooming brand Bombay Shaving Company migrated to Shopify. Case study approved by merchant and ready for publication. Strong D2C growth narrative for retail + personal care sector.",
        "stage": "MOFU", "persona": "Head of eCommerce · CMO", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "MEDIUM",
        "notes": "Approved for publication as of Mar 2026. Draft: https://docs.google.com/document/d/1mfhyrKGMQ0BXjEe6xjgCkB-z00XkDxmO9OCmeiGyVEs/edit",
        "caveats": "Not yet live on shopify.com/case-studies — use draft link for internal reference", "country": "India / ANZ", "industry": "Health & Beauty",
        "status": "draft", "segment": ["SMB", "MM"], "source": "Slack — #ext-archetype-case-studies", "region": "ANZ", "slackChannel": "ext-archetype-case-studies"
    },
    {
        "title": "Hairhouse: Omnichannel Retail Transformation with Shopify POS",
        "type": "Case study", "url": None,
        "internal": "Google Doc — pending merchant sign-off",
        "summary": "Hairhouse, one of Australia's leading hair and beauty retailers, undergoing case study production. Story covers their Shopify POS rollout across retail locations. Pending final merchant approval.",
        "stage": "MOFU", "persona": "Head of Retail · CTO", "theme": "Unified Commerce",
        "geo": "ANZ", "effort": "Light edit required", "credibility": "MEDIUM",
        "notes": "Draft under review. Working doc: https://docs.google.com/document/d/1zb7ofZMx9ZZvrDgUrknlUHbqxjIG5cGPZH4mtf31zMk/edit",
        "caveats": "Awaiting merchant sign-off — not cleared for external distribution", "country": "Australia", "industry": "Health & Beauty",
        "status": "draft", "segment": ["MM", "LA"], "source": "Slack — #ext-archetype-case-studies", "region": "ANZ", "slackChannel": "ext-archetype-case-studies"
    },
    {
        "title": "The Good Guys: Double-Digit Online Sales Growth & 5x Faster Deployments with Shopify",
        "type": "Case study",
        "url": "https://www.shopify.com/case-studies/the-good-guys",
        "internal": None,
        "summary": "The Good Guys migrated from a legacy custom platform to Shopify headless (Hydrogen + Oxygen) with The Working Party. Results: ~20% increase in online sales, 5x faster deployment cycles, 2x site speed increase, 50% reduction in campaign setup time. One of Australia's largest headless Shopify Plus migrations.",
        "stage": "BOFU", "persona": "CIO · Head of Digital · CFO · Head of eCommerce", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "LIVE on shopify.com. 🎬 Video: https://shopify-2.wistia.com/medias/6x95ouhs5j. Partner: The Working Party. Also on Inside Retail AU: https://insideretail.com.au/business/how-the-good-guys-built-scalability-and-confidence-online-202510. TWP case study (downloadable PDF): https://theworkingparty.com.au/pages/our-work/the-good-guys",
        "caveats": "", "country": "Australia", "industry": "Consumer Electronics / Appliances",
        "metrics": "~20% online sales growth; 5x faster deployments; 2x site speed; 50% less campaign setup time",
        "status": "published", "segment": ["LA"], "source": "Slack — #ext-archetype-case-studies", "region": "ANZ", "slackChannel": "ext-archetype-case-studies"
    },
    {
        "title": "The Good Guys — LinkedIn Post Template",
        "type": "Social / LinkedIn",
        "url": "https://www.shopify.com/case-studies/the-good-guys",
        "internal": None,
        "summary": "Ready-to-use LinkedIn post for The Good Guys x Shopify case study. Copy the post below, personalise the opening line, and share with a link to the case study.",
        "stage": "TOFU", "persona": "AE · Marketing Manager · Sales Lead", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": """LinkedIn post copy (ready to use — personalise as needed):

🎬 VIDEO: https://shopify-2.wistia.com/medias/6x95ouhs5j
📄 CASE STUDY: https://www.shopify.com/case-studies/the-good-guys

---

🏪 One of Australia's most iconic retailers just made a big move.

The Good Guys — a household name for home appliances since 1952 — completed one of Australia's largest headless Shopify Plus migrations, transforming their ecommerce from a maintenance bottleneck into a growth engine.

The results:
📈 ~20% increase in online sales
⚡ 2x faster site speed
🚀 5x faster deployment cycles
⏱ 50% reduction in campaign setup time

Before Shopify, even simple content updates needed developer tickets. Teams worked through the night to push deployments without crashing the site. Peak periods like Black Friday were a source of dread, not opportunity.

Now? Campaigns go live in hours, not days. Developers are focused on building — not babysitting infrastructure.

Built with The Working Party using Shopify Hydrogen and Oxygen — composable, API-led, built for scale.

Watch the story 👇

#Shopify #eCommerce #RetailTech #HeadlessCommerce #TheGoodGuys #ANZ #UnifiedCommerce

---

TIP: Upload the Wistia video (https://shopify-2.wistia.com/medias/6x95ouhs5j) directly to LinkedIn for native video play — do NOT just paste the Wistia link. Download from Wistia first, then upload.""",
        "caveats": "Pair with Wistia video for LinkedIn video posts. Inside Retail article adds third-party credibility.",
        "country": "Australia", "industry": "Consumer Electronics / Appliances",
        "metrics": "~20% online sales growth; 5x faster deployments; 2x site speed; 50% less campaign setup time",
        "status": "published", "segment": ["MM", "LA"], "source": "Slack — #ext-archetype-case-studies", "region": "ANZ", "slackChannel": "ext-archetype-case-studies"
    },
    {
        "title": "The Good Guys — Case Study Video",
        "type": "Video",
        "url": "https://shopify-2.wistia.com/medias/6x95ouhs5j",
        "internal": None,
        "summary": "Shopify video case study for The Good Guys. Covers their headless Shopify Plus migration with The Working Party, key results (~20% online sales growth, 5x faster deployments, 2x site speed), and the shift from a legacy bottleneck to a composable commerce platform.",
        "stage": "BOFU", "persona": "CIO · Head of Digital · CFO · Head of eCommerce", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Hosted on Wistia. Download and upload natively to LinkedIn for best reach — do not just share the Wistia URL. Pair with case study: https://www.shopify.com/case-studies/the-good-guys",
        "caveats": "", "country": "Australia", "industry": "Consumer Electronics / Appliances",
        "metrics": "~20% online sales growth; 5x faster deployments; 2x site speed; 50% less campaign setup time",
        "status": "published", "segment": ["MM", "LA"], "source": "Shopify Wistia", "region": "ANZ"
    },
    {
        "title": "Metagenics: Transforming Legacy Tech Stack to Improve CX and Revenue",
        "type": "Case study", "url": "https://insideretail.com.au/case-study/how-metagenics-transformed-its-legacy-tech-stack-to-improve-cx-and-grow-revenue",
        "internal": None,
        "summary": "Metagenics migrated from a legacy tech stack to Shopify, improving customer experience and growing revenue. Published via Inside Retail Australia. Case study on shopify.com pending publication as of Mar 2026.",
        "stage": "MOFU", "persona": "CIO · Head of eCommerce", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Inside Retail version live. Shopify.com case study in preview: https://everest.shopify.com/case-studies/metagenics?preview (user: Shopify / pass: Awesome)",
        "caveats": "", "country": "Australia", "industry": "Health & Wellness",
        "status": "draft", "segment": ["MM", "LA"], "source": "Slack — #ext-archetype-case-studies", "region": "ANZ", "slackChannel": "ext-archetype-case-studies"
    },
    {
        "title": "APAC Case Studies Master Deck",
        "type": "Presentation", "url": "https://docs.google.com/presentation/d/1W7lMeAdTzuV-otMqxUWSCQdlmuIfkMVYXWLZTEQJDnw/edit",
        "internal": "Google Slides — internal only",
        "summary": "Master deck compiling all published APAC case studies by country (ANZ, SEA). Includes Quad Lock, Mocka, Nutrition Warehouse, Mr DIY, Delugs and others. Updated regularly by Archetype team.",
        "stage": "BOFU", "persona": "AE · Sales Lead", "theme": "Scalability",
        "geo": "ANZ", "effort": "Ready to use", "credibility": "HIGH",
        "notes": "Internal use for sales conversations. Maintained by Archetype (daniel.ling team).",
        "caveats": "", "country": "Australia / APAC", "industry": "Multi-industry",
        "segment": ["MM", "LA"], "source": "Slack — #ext-archetype-case-studies", "region": "ANZ", "slackChannel": "ext-archetype-case-studies"
    },
]

# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    all_assets = []

    # 1. Google Sheets
    print("\n📊 Loading Google Sheets sources...")
    try:
        service = get_service()
        for source in SOURCES:
            try:
                assets = load_sheet(service, source)
                all_assets.extend(assets)
            except Exception as e:
                print(f"  ERROR reading {source['name']}: {e}")
    except Exception as e:
        print(f"  ERROR connecting to Sheets: {e}")

    # 2. Slack snapshot (auto-generated from 9 channels)
    print("\n💬 Loading Slack channel assets...")
    slack_assets = scrape_slack_direct()
    all_assets.extend(slack_assets)
    print(f"  ✓ {len(slack_assets)} assets from {len(SLACK_CHANNELS)} Slack channels")

    # ── Geo normalisation & exclusion ───────────────────────────
    # Only keep assets relevant to ANZ, AMER, EMEA, or Global.
    # Exclude assets that are specifically for non-target markets.
    EXCLUDE_GEOS = {
        'japan', 'singapore', 'india', 'china', 'malaysia', 'philippines',
        'thailand', 'taiwan', 'indonesia', 'korea', 'vietnam', 'sea',
        'southeast asia', 'hong kong', 'bangladesh', 'pakistan',
    }
    # Geo values we normalise to clean labels
    def normalise_geo(geo):
        g = (geo or '').strip()
        gl = g.lower()
        if any(k in gl for k in ['australia', 'anz', 'new zealand', ' nz', 'nz ']):
            return 'ANZ'
        if gl in ('nz',): return 'ANZ'
        if 'global' in gl: return 'Global'
        if any(k in gl for k in ['amer', 'us', 'usa', 'canada', 'north america', 'latam']):
            return 'AMER'
        if any(k in gl for k in ['emea', 'europe', 'uk', 'middle east', 'africa']):
            return 'EMEA'
        if 'apac' in gl: return 'APAC'
        return g  # keep original for anything else

    filtered = []
    for a in all_assets:
        geo = (a.get('geo') or '').strip().lower()
        # Exclude if geo is solely a non-target country
        if any(excluded in geo for excluded in EXCLUDE_GEOS):
            # Allow through if it ALSO mentions ANZ/Australia
            if not any(k in geo for k in ['anz', 'australia', 'new zealand']):
                continue
        # Normalise geo label
        a['geo'] = normalise_geo(a.get('geo', ''))
        filtered.append(a)

    before = len(all_assets)
    all_assets = filtered
    print(f"  Geo filter: {before} → {len(all_assets)} assets ({before - len(all_assets)} non-target excluded)")

    # ── Deduplicate by URL ───────────────────────────────────────
    seen = set()
    deduped = []
    for a in all_assets:
        key = ((a.get("url") or "") + "|" + (a.get("title") or "")).strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(a)
    all_assets = deduped

    # Ensure every asset has required fields (status, gated) for frontend filters
    for a in all_assets:
        a.setdefault('status', 'published')
        a.setdefault('gated', is_gated(a.get('url')))
        # Ensure stage is always a valid value
        if a.get('stage') not in ('TOFU', 'MOFU', 'BOFU'):
            a['stage'] = parse_stage(a.get('stage', ''))

    # 3. Write output
    output = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "count": len(all_assets),
        "sources": [s['name'] for s in SOURCES] + [f"Slack — #{c['name']}" for c in SLACK_CHANNELS],
        "assets": all_assets
    }

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ {len(all_assets)} total assets → {OUTPUT_PATH}")

    # Copy to deploy folder
    import shutil, os
    if os.path.exists(DEPLOY_DIR):
        shutil.copy(OUTPUT_PATH, f"{DEPLOY_DIR}/assets.json")
        shutil.copy(
            "/Users/shalini.keyan/Cursor Workspaces/outline/content-library.html",
            f"{DEPLOY_DIR}/index.html"
        )
        print(f"📁 Copied to {DEPLOY_DIR}/")
        print(f"\nTo deploy: quick deploy {DEPLOY_DIR} anzcontent")

if __name__ == '__main__':
    main()
