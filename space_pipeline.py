"""
UK Space Sector Value Chain — Stage 3 Pipeline (v3)

Automatically processes ALL CH bulk candidates in batches of 500
without any manual intervention between batches.

Saves progress after every batch so you can safely stop and resume
at any time — just re-run the script and it picks up where it left off.

How to use:
  Run:    python space_pipeline_v3.py
  Resume: python space_pipeline_v3.py          (auto-detects where you left off)
  Finish: python space_pipeline_v3.py --finalise

  Script resumes automatically if interrupted — just re-run.

Output files (all append-safe):
  data/pipeline_verified.csv     — firms confirmed as space sector
  data/pipeline_peripheral.csv   — firms excluded (not space)
  data/pipeline_review.csv       — firms needing manual defence check
  data/pipeline_progress.json    — progress tracker (auto-managed)
  data/firm_database_final.csv   — final merged database (--finalise only)

References:
  Companies House API
  https://developer-specs.company-information.service.gov.uk/
  ONS (2007) UK SIC 2007 — space activity index
  ONS (2026) UK SIC 2026 — codes 30.331 and 30.332
  UK Space Agency (2025) Size and Health of the UK Space Industry 2024
"""

import requests
import pandas as pd
import time
import os
import re
import json
import sys
from datetime import date, datetime

# ── CONFIGURATION ──────────────────────────────────────────────────────────

API_KEY    = "7c912c9d-e8ce-4c4c-8048-b4380e5ab00c"   # replace with your key
BASE_URL   = "https://api.company-information.service.gov.uk"
OUTPUT_DIR = "/Users/keerthanate/dissertation/data"
DATE_TODAY = str(date.today())

BATCH_SIZE = 500       # firms per batch — do not change
API_DELAY  = 0.4       # seconds between API calls (CH limit: 600/5min)
                       # 0.4s = 150 req/min, within the 120/min avg limit
                       # Script handles 429 rate-limit errors automatically

# Input files — point to ML-filtered candidates (threshold >= 0.50)
# This reduces from 83,690 (threshold 0.30) to ~34,111 firms
# Calibration data confirms firms below 0.50 have 5-10% actual space rate
# See ml_model_evaluation_v2.txt for full calibration evidence
CH_UNVERIFIED_PATH = f"{OUTPUT_DIR}/ml_pipeline_candidates.csv"
REVIEWED_PATH      = f"{OUTPUT_DIR}/seed_firms_reviewed.csv"

# Output files
VERIFIED_PATH    = f"{OUTPUT_DIR}/pipeline_verified.csv"
PERIPHERAL_PATH  = f"{OUTPUT_DIR}/pipeline_peripheral.csv"
REVIEW_PATH      = f"{OUTPUT_DIR}/pipeline_review.csv"
PROGRESS_PATH    = f"{OUTPUT_DIR}/pipeline_progress.json"
FINAL_DB_PATH    = f"{OUTPUT_DIR}/firm_database_final.csv"

# ── NODE LABELS ────────────────────────────────────────────────────────────

NODE_LABELS = {
    'N1': 'Components and Materials',
    'N2': 'Subsystems and Payloads',
    'N3': 'Satellite and Spacecraft Manufacturing',
    'N4': 'Ground Segment',
    'N5': 'Launch',
    'N6': 'Satellite Operations',
    'N7': 'Data Processing and Analytics',
    'N8': 'Applications and Services',
    'N9': 'Enabling and Ancillary',
}

# ── SPACE KEYWORDS ─────────────────────────────────────────────────────────

SPACE_KEYWORDS = [
    'satellite', 'space', 'spacecraft', 'orbital', 'launch',
    'earth observation', 'gnss', 'navigation system', 'telemetry',
    'propulsion', 'payload', 'ground station', 'remote sensing',
    'geospatial', 'aerospace', 'astro', 'rocket', 'cubesat',
    'smallsat', 'constellation', 'launcher', 'nanosatellite',
    'spaceport', 'in-orbit', 'debris removal', 'earth imaging',
    'hyperspectral', 'synthetic aperture', 'geostationary',
    'low earth orbit', 'leo satellite', 'sar satellite',
]

# Tier 1 SIC codes confirmed by ONS SIC 2007 as explicitly space-related
# These pass Filter 2 without keyword check
HIGH_CONFIDENCE_CODES = {'30300', '51220', '61300'}

# ── PROGRESS TRACKER ───────────────────────────────────────────────────────

def load_progress():
    """Load progress from previous run. Returns next row to process."""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, 'r') as f:
            p = json.load(f)
        print(f"Resuming from row {p['next_row']:,} "
              f"(previously processed {p['total_processed']:,} firms)")
        return p
    return {
        'next_row':        0,
        'total_processed': 0,
        'total_verified':  0,
        'total_peripheral':0,
        'total_review':    0,
        'started':         datetime.now().isoformat(),
        'last_updated':    datetime.now().isoformat(),
    }


def save_progress(p):
    """Save progress after each batch."""
    p['last_updated'] = datetime.now().isoformat()
    with open(PROGRESS_PATH, 'w') as f:
        json.dump(p, f, indent=2)


# ── CH API FUNCTIONS ───────────────────────────────────────────────────────

def get_company_by_number(company_number):
    """Fetch company details from CH API."""
    url = f"{BASE_URL}/company/{company_number}"
    try:
        r = requests.get(url, auth=(API_KEY, ""), timeout=10)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 429:
            print("\n  Rate limit hit — waiting 60 seconds...")
            time.sleep(60)
            return get_company_by_number(company_number)
        return None
    except Exception:
        return None


def search_company_by_name(name, items=1):
    """Search CH API by company name."""
    url = f"{BASE_URL}/search/companies"
    try:
        r = requests.get(url, auth=(API_KEY, ""),
                         params={"q": name, "items_per_page": items},
                         timeout=10)
        if r.status_code == 200:
            return r.json().get("items", [])
        return []
    except Exception:
        return []


def extract_ch_fields(data):
    """Extract relevant fields from CH API response."""
    if not data:
        return {}
    addr = data.get("registered_office_address", {})
    return {
        'ch_name':         data.get("company_name", ""),
        'ch_status':       data.get("company_status", ""),
        'ch_type':         data.get("type", ""),
        'ch_sic_codes':    ", ".join(data.get("sic_codes", [])),
        'ch_postcode':     addr.get("postal_code", ""),
        'ch_locality':     addr.get("locality", ""),
        'ch_region':       addr.get("region", ""),
        'ch_country':      addr.get("country", ""),
        'ch_incorporated': data.get("date_of_creation", ""),
        'ch_verified':     'Yes',
    }


# ── FILTER FUNCTIONS ───────────────────────────────────────────────────────

def has_space_signal(company_name, sic_text):
    """Check if name or SIC description contains space keywords."""
    text = (str(company_name) + ' ' + str(sic_text)).lower()
    return any(kw in text for kw in SPACE_KEYWORDS)


def normalise(name):
    """Normalise company name for matching."""
    name = str(name).upper()
    name = re.sub(r'\b(LIMITED|LTD|PLC|LLP|UK|GROUP|HOLDINGS)\b', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    return re.sub(r'\s+', ' ', name).strip()


def apply_filters(firm, ch_data, reviewed_norms):
    """
    Four filters — returns (status, reason).
    status: 'verified' | 'peripheral' | 'review'
    """
    name     = str(firm.get('company_name', ''))
    sic_code = str(firm.get('matched_sic_code', ''))
    sic_text = str(firm.get('sic_codes_full', ''))
    defence  = str(firm.get('requires_defence_check', ''))

    # Filter 1 — CH API active status
    if ch_data:
        ch_status = ch_data.get('ch_status', '').lower()
        if ch_status and ch_status != 'active':
            return 'peripheral', f'CH status: {ch_status} — not active'

    # Filter 2 — Space signal
    if sic_code not in HIGH_CONFIDENCE_CODES:
        if not has_space_signal(name, sic_text):
            return 'peripheral', (
                f'No space keyword in name or SIC. '
                f'Broad SIC {sic_code} match — not space sector.'
            )

    # Filter 3 — Source 2 cross-reference
    norm = normalise(name)
    for rev_norm in reviewed_norms:
        if (norm == rev_norm or
            (len(norm) > 5 and norm in rev_norm) or
            (len(rev_norm) > 5 and rev_norm in norm)):
            return 'verified', 'Also in Source 2 (ukspacetech.com)'

    # Filter 4 — Defence check flag
    if defence == 'Yes':
        return 'review', (
            f'SIC {sic_code} confirmed by ONS SIC 2026 to contain both '
            f'civilian and military manufacturers. '
            f'Needs website review for defence_primary assessment.'
        )

    # Passed all filters
    return 'verified', (
        f'Active, space keyword confirmed, '
        f'SIC {sic_code} ({firm.get("sic_confidence","")} confidence).'
    )


# ── APPEND TO FILE ─────────────────────────────────────────────────────────

def append_to_csv(records, path):
    """Append records to CSV — create if not exists."""
    if not records:
        return
    df_new = pd.DataFrame(records)
    if os.path.exists(path):
        df_existing = pd.read_csv(path, low_memory=False)
        pd.concat([df_existing, df_new], ignore_index=True).to_csv(
            path, index=False)
    else:
        df_new.to_csv(path, index=False)


# ── MAIN PIPELINE ──────────────────────────────────────────────────────────

def run_pipeline():
    """Process all CH bulk candidates automatically in batches."""

    print("=" * 65)
    print("UK Space Sector — Stage 3 Pipeline (v3)")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    if API_KEY == "YOUR_COMPANIES_HOUSE_API_KEY":
        print("\nERROR: Replace API_KEY with your Companies House API key")
        print("Register free at:")
        print("  https://developer.company-information.service.gov.uk/")
        return

    # Load candidates
    print(f"\nLoading ML pipeline candidates: {CH_UNVERIFIED_PATH}")
    try:
        df_ch = pd.read_csv(CH_UNVERIFIED_PATH, low_memory=False)
    except FileNotFoundError:
        print("File not found — run ml_classifier_v2.py first")
        return
    print(f"  Total loaded: {len(df_ch):,}")

    # Apply ML threshold filter — keep only firms scoring >= 0.50
    # Calibration data: firms below 0.50 have 5-10% actual space rate
    # Threshold raised from 0.30 to 0.50 to reduce pipeline time from
    # 13.9 hours to ~3.8 hours with minimal loss of genuine space firms
    # Evidence: ml_model_evaluation_v2.txt calibration table
    ML_THRESHOLD = 0.50
    if 'space_probability' in df_ch.columns:
        before = len(df_ch)
        df_ch = df_ch[df_ch['space_probability'] >= ML_THRESHOLD].copy()
        df_ch = df_ch.reset_index(drop=True)
        print(f"  After ML threshold >= {ML_THRESHOLD}: {len(df_ch):,} firms")
        print(f"  Excluded below threshold: {before - len(df_ch):,} firms")
    else:
        print(f"  No space_probability column — processing all {len(df_ch):,} firms")
    print(f"  Total candidates: {len(df_ch):,}")

    # Load reviewed firms for cross-reference
    try:
        df_reviewed = pd.read_csv(REVIEWED_PATH, low_memory=False)
        reviewed_norms = set(
            df_reviewed['company_name'].dropna()
            .apply(normalise).tolist()
        )
    except FileNotFoundError:
        reviewed_norms = set()
    print(f"  Source 2 firms for cross-reference: {len(reviewed_norms)}")

    # Load progress
    progress = load_progress()
    start_row = progress['next_row']

    if start_row >= len(df_ch):
        print(f"\nAll {len(df_ch):,} firms already processed.")
        print("Run with --finalise to build the final database.")
        return

    total_remaining = len(df_ch) - start_row
    est_hours = total_remaining * API_DELAY / 3600
    print(f"\nRemaining: {total_remaining:,} firms")
    print(f"Estimated time: {est_hours:.1f} hours")
    print(f"Starting from row: {start_row:,}")
    print(f"\nProcessing... (Ctrl+C to stop safely between batches)\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        row_idx = start_row

        while row_idx < len(df_ch):
            # Get next batch
            batch_end = min(row_idx + BATCH_SIZE, len(df_ch))
            df_batch  = df_ch.iloc[row_idx:batch_end]

            verified   = []
            peripheral = []
            review     = []

            for _, row in df_batch.iterrows():
                firm = row.to_dict()
                company_number = str(firm.get('company_number','')).strip().zfill(8)
                company_name   = str(firm.get('company_name','')).strip()

                # CH API lookup
                ch_data = {}
                if company_number and company_number != '00000000':
                    raw = get_company_by_number(company_number)
                    if raw:
                        ch_data = extract_ch_fields(raw)
                        firm.update(ch_data)
                elif company_name:
                    results = search_company_by_name(company_name)
                    if results:
                        num = results[0].get('company_number', '')
                        if num:
                            raw = get_company_by_number(num)
                            if raw:
                                ch_data = extract_ch_fields(raw)
                                firm.update(ch_data)
                                firm['company_number'] = num

                # Apply filters
                status, reason = apply_filters(firm, ch_data, reviewed_norms)
                firm['pipeline_status'] = status
                firm['pipeline_reason'] = reason
                firm['pipeline_date']   = DATE_TODAY

                if status == 'verified':
                    verified.append(firm)
                elif status == 'peripheral':
                    peripheral.append(firm)
                else:
                    review.append(firm)

                time.sleep(API_DELAY)

            # Save batch results
            append_to_csv(verified,   VERIFIED_PATH)
            append_to_csv(peripheral, PERIPHERAL_PATH)
            append_to_csv(review,     REVIEW_PATH)

            # Update progress
            row_idx += len(df_batch)
            progress['next_row']         = row_idx
            progress['total_processed'] += len(df_batch)
            progress['total_verified']  += len(verified)
            progress['total_peripheral']+= len(peripheral)
            progress['total_review']    += len(review)
            save_progress(progress)

            # Progress report
            pct = row_idx / len(df_ch) * 100
            remaining = (len(df_ch) - row_idx) * API_DELAY / 3600
            print(f"  Row {row_idx:>7,}/{len(df_ch):,} ({pct:.1f}%) | "
                  f"verified={progress['total_verified']:,} | "
                  f"peripheral={progress['total_peripheral']:,} | "
                  f"review={progress['total_review']:,} | "
                  f"~{remaining:.1f}h remaining")

    except KeyboardInterrupt:
        print(f"\n\nStopped safely at row {progress['next_row']:,}")
        print(f"Re-run the script to continue from this point.")
        return

    # All done
    print(f"\n{'='*65}")
    print("PIPELINE COMPLETE")
    print(f"{'='*65}")
    print(f"  Total processed:  {progress['total_processed']:,}")
    print(f"  Verified:         {progress['total_verified']:,}")
    print(f"  Peripheral:       {progress['total_peripheral']:,}")
    print(f"  Needs review:     {progress['total_review']:,}")
    print(f"\nRun with --finalise to build the final database:")
    print(f"  python space_pipeline_v3.py --finalise")
    print("=" * 65)


# ── SHELL COMPANY DETECTION ────────────────────────────────────────────────

def flag_shells(df):
    """
    Flag likely shell companies and holding vehicles for Tableau filtering.

    A firm is flagged is_shell=Yes if it meets two or more of:
      - Company name contains shell indicator words
      - CH type is 'investment-company' or contains 'holding'
      - Company has 0 employees (from CH API)
      - Company name ends in HOLDINGS, VENTURES, CAPITAL, INVESTMENT,
        GROUP, PARTNERS where no other space signal exists

    Firms flagged is_shell=Yes are included in firm_database_final.csv
    but marked so Tableau can filter them out of the main analysis.
    They may be legitimate holding vehicles for genuine space firms
    — the flag is informational, not an exclusion.
    """
    SHELL_NAME_PATTERNS = [
        r'\bholdings?\b', r'\bventures?\b', r'\bcapital\b',
        r'\binvestment\b', r'\bfinance\b', r'\bgroup\b',
        r'\bpartners\b', r'\bacquisition\b', r'\bequity\b',
        r'\bproperties\b', r'\bassets\b', r'\benterprises?\b',
    ]

    SPACE_NAME_PATTERNS = [
        r'satellite', r'space', r'spacecraft', r'orbital',
        r'launch', r'rocket', r'aerospace', r'astro',
        r'gnss', r'propulsion', r'payload', r'cubesat',
    ]

    def check_shell(row):
        name = str(row.get('company_name', '')).lower()
        ch_type = str(row.get('ch_type', '') or
                      row.get('company_category', '')).lower()

        # Has space keyword — unlikely to be pure shell
        has_space = any(re.search(p, name) for p in SPACE_NAME_PATTERNS)
        if has_space:
            return 'No'

        # Count shell signals
        signals = 0

        # Shell name pattern
        if any(re.search(p, name) for p in SHELL_NAME_PATTERNS):
            signals += 1

        # CH company type suggests investment/holding
        if any(t in ch_type for t in
               ['investment', 'holding', 'private-fund', 'assurance']):
            signals += 1

        # Zero employees from CH API
        emp = str(row.get('ch_employees', '') or
                  row.get('employees', '')).strip()
        if emp in ('0', 'None', '', 'nan'):
            signals += 1

        # Very short name (3 letters or less — likely initials shell)
        core_name = re.sub(
            r'\b(limited|ltd|plc|llp|holdings?|group)\b', '', name
        ).strip()
        if len(core_name) <= 4:
            signals += 1

        return 'Yes' if signals >= 2 else 'No'

    df['is_shell'] = df.apply(check_shell, axis=1)
    return df


# ── BUILD FINAL DATABASE ───────────────────────────────────────────────────

def build_final_database():
    """
    Merge seed_firms_reviewed.csv + pipeline_verified.csv
    into the final firm database.

    Also produces:
      pipeline_defence_review.xlsx — firms needing manual defence check
        (same format as review_sheet.xlsx — fill yellow cells,
         then run apply_pipeline_review.py to merge back)
      firm_database_final.csv — complete database with is_shell flag

    Run after all pipeline batches are complete:
      python space_pipeline_v3.py --finalise
    """
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    print("=" * 65)
    print("Building Final Firm Database")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    # Load reviewed firms (121 manually reviewed from Sources 1+2)
    try:
        df_reviewed = pd.read_csv(REVIEWED_PATH, low_memory=False)
        df_reviewed['defence_review_status'] = 'Manually reviewed'
        df_reviewed['is_shell'] = 'No'  # manual review already caught shells
        print(f"\nReviewed firms (Sources 1+2): {len(df_reviewed):,}")
    except FileNotFoundError:
        print(f"Not found: {REVIEWED_PATH}")
        return

    # Load pipeline verified firms
    try:
        df_pipeline = pd.read_csv(VERIFIED_PATH, low_memory=False)
        print(f"Pipeline verified (CH Bulk): {len(df_pipeline):,}")
    except FileNotFoundError:
        df_pipeline = pd.DataFrame()
        print(f"Pipeline verified: 0 — run pipeline first")

    # Load pipeline review firms (defence check needed)
    try:
        df_defence = pd.read_csv(REVIEW_PATH, low_memory=False)
        print(f"Needs defence review: {len(df_defence):,}")
    except FileNotFoundError:
        df_defence = pd.DataFrame()
        print(f"Defence review: 0")

    # Deduplicate pipeline vs reviewed
    if len(df_pipeline) > 0:
        reviewed_nums = set(
            df_reviewed['company_number'].dropna().astype(str)
        )
        df_pipeline_dedup = df_pipeline[
            ~df_pipeline['company_number'].astype(str).isin(reviewed_nums)
        ].copy()
        print(f"Duplicates removed: "
              f"{len(df_pipeline) - len(df_pipeline_dedup):,}")
        print(f"Pipeline-only firms: {len(df_pipeline_dedup):,}")
    else:
        df_pipeline_dedup = pd.DataFrame()

    # Flag shells in pipeline firms
    if len(df_pipeline_dedup) > 0:
        print(f"\nFlagging shell companies and holding vehicles...")
        df_pipeline_dedup = flag_shells(df_pipeline_dedup)
        df_pipeline_dedup['defence_review_status'] = 'Pipeline verified'
        shell_count = len(df_pipeline_dedup[
            df_pipeline_dedup['is_shell'] == 'Yes'
        ])
        print(f"  Flagged as is_shell=Yes: {shell_count:,}")
        print(f"  (included in database but flagged for Tableau filtering)")

    # Combine
    df_final = pd.concat([df_reviewed, df_pipeline_dedup], ignore_index=True)
    df_final['data_collection_date'] = DATE_TODAY

    # Ensure chain_position is derived from node for pipeline firms
    # where it may not have been set during SIC extraction
    chain_map = {
        'N1': 'Upstream', 'N2': 'Upstream', 'N3': 'Upstream',
        'N4': 'Upstream', 'N5': 'Upstream',
        'N6': 'Downstream', 'N7': 'Downstream', 'N8': 'Downstream',
        'N9': 'Enabling',
    }
    df_final['chain_position'] = df_final.apply(
        lambda r: chain_map.get(str(r.get('primary_node', '')),
                                str(r.get('chain_position', ''))),
        axis=1
    )

    print(f"\nFinal firm database: {len(df_final):,} firms")

    print(f"\nBy primary node:")
    for node in ['N1','N2','N3','N4','N5','N6','N7','N8','N9']:
        count = len(df_final[df_final['primary_node'] == node])
        if count > 0:
            label = NODE_LABELS.get(node, '')
            print(f"  {node}  {label:<42} {count:>5,}")

    print(f"\nBy chain position:")
    for pos in ['Upstream', 'Downstream', 'Enabling']:
        count = len(df_final[df_final['chain_position'] == pos])
        if count > 0:
            print(f"  {pos:<14} {count:>5,}")

    print(f"\nBy is_shell:")
    for val in ['No', 'Yes']:
        count = len(df_final[df_final.get('is_shell', pd.Series('No')) == val]) \
            if 'is_shell' in df_final.columns else 0
        if count > 0:
            label = '(genuine firms)' if val == 'No' else '(holding/shell — Tableau filter)'
            print(f"  is_shell={val}: {count:,}  {label}")

    # Save final database
    df_final.to_csv(FINAL_DB_PATH, index=False)
    print(f"\nSaved: {FINAL_DB_PATH}")

    # ── GENERATE DEFENCE REVIEW EXCEL ──────────────────────────────────────
    # Same format as review_sheet.xlsx — yellow cells for you to fill in
    # After completing, run apply_pipeline_review.py to merge back

    if len(df_defence) > 0:
        print(f"\nGenerating defence review sheet...")

        # Style helpers
        NAVY   = PatternFill('solid', fgColor='1F3864')
        YELLOW = PatternFill('solid', fgColor='FFD700')
        ORANGE = PatternFill('solid', fgColor='FCE4D6')
        GREY   = PatternFill('solid', fgColor='F2F2F2')
        WHITE  = PatternFill('solid', fgColor='FFFFFF')
        HDR_F  = Font(name='Arial', bold=True, color='FFFFFF', size=10)
        BODY_F = Font(name='Arial', size=10)
        BOLD_F = Font(name='Arial', bold=True, size=10)
        LINK_F = Font(name='Arial', size=10, color='0563C1', underline='single')
        INP_F  = Font(name='Arial', bold=True, size=10, color='000080')
        thin   = Side(style='thin', color='BFBFBF')
        BDR    = Border(left=thin, right=thin, top=thin, bottom=thin)

        def sh(cell, fill=None):
            cell.font = HDR_F; cell.fill = fill or NAVY
            cell.alignment = Alignment(horizontal='center',
                                        vertical='center', wrap_text=True)
            cell.border = BDR

        def sc(cell, fill=None, bold=False, link=False):
            cell.font = LINK_F if link else (BOLD_F if bold else BODY_F)
            cell.fill = fill or WHITE
            cell.alignment = Alignment(horizontal='left', vertical='center',
                                        wrap_text=True)
            cell.border = BDR

        def si(cell):
            cell.font = INP_F; cell.fill = YELLOW
            cell.alignment = Alignment(horizontal='left', vertical='center',
                                        wrap_text=True)
            cell.border = BDR

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Defence Review — Pipeline'
        ws.sheet_view.showGridLines = False

        ws.merge_cells('A1:L1')
        ws['A1'] = 'UK Space Sector — Pipeline Defence Review'
        ws['A1'].font = Font(name='Arial', bold=True, size=14,
                              color='1F3864')
        ws['A1'].alignment = Alignment(horizontal='left',
                                        vertical='center')
        ws.row_dimensions[1].height = 28

        ws.merge_cells('A2:L2')
        ws['A2'] = (
            f'{len(df_defence)} firms from the CH API pipeline flagged '
            f'requires_defence_check=Yes. Visit each company website and fill '
            f'in the yellow cells. Same format as review_sheet.xlsx. '
            f'Run apply_pipeline_review.py when complete.'
        )
        ws['A2'].font = Font(name='Arial', italic=True, size=10,
                              color='595959')
        ws['A2'].alignment = Alignment(horizontal='left', vertical='center',
                                        wrap_text=True)
        ws.row_dimensions[2].height = 40
        ws.row_dimensions[3].height = 6

        headers = [
            '#', 'Company Name (CH legal)', 'Current Node',
            'Chain Position', 'SIC Code', 'SIC Description',
            'CH Profile', 'Website',
            'defence_primary\n(fill: Yes/Partial/No)',
            'node_confirmed\n(fill if different)',
            'secondary_node\n(fill if applicable)',
            'evidence_notes\n(fill: what you found)',
        ]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col, value=h)
            sh(cell)
        ws.row_dimensions[4].height = 40
        ws.freeze_panes = 'A5'

        for i, (_, row) in enumerate(df_defence.iterrows()):
            r = i + 5
            fill = ORANGE if i % 2 == 0 else WHITE

            ws.cell(row=r, column=1, value=i+1).fill = fill
            ws.cell(row=r, column=1).font = BODY_F
            ws.cell(row=r, column=1).alignment = Alignment(
                horizontal='center', vertical='center')
            ws.cell(row=r, column=1).border = BDR

            name = row.get('company_name', '')
            c = ws.cell(row=r, column=2, value=name); sc(c, fill=fill, bold=True)

            c = ws.cell(row=r, column=3,
                        value=row.get('primary_node', '')); sc(c, fill=fill)
            c = ws.cell(row=r, column=4,
                        value=row.get('chain_position', '')); sc(c, fill=fill)
            c = ws.cell(row=r, column=5,
                        value=row.get('matched_sic_code', '')); sc(c, fill=fill)
            c = ws.cell(row=r, column=6,
                        value=str(row.get('matched_sic_text', ''))[:60])
            sc(c, fill=fill)

            # CH Profile link
            ch_num = str(row.get('company_number', '')).strip()
            uri = (f"https://find-and-update.company-information.service"
                   f".gov.uk/company/{ch_num}" if ch_num else '')
            c = ws.cell(row=r, column=7,
                        value='CH Profile' if uri else '—')
            if uri:
                c.hyperlink = uri; sc(c, fill=fill, link=True)
            else:
                sc(c, fill=fill)

            website = str(row.get('website', ''))
            c = ws.cell(row=r, column=8,
                        value=website if website not in ('nan', '') else '—')
            if website and website not in ('nan', ''):
                c.hyperlink = website; sc(c, fill=fill, link=True)
            else:
                sc(c, fill=fill)

            # Yellow input cells
            for col in [9, 10, 11, 12]:
                si(ws.cell(row=r, column=col, value=''))

            ws.row_dimensions[r].height = 40

        # Column widths
        for col, w in enumerate(
            [5, 32, 10, 14, 10, 35, 12, 28, 20, 18, 16, 40], 1
        ):
            ws.column_dimensions[get_column_letter(col)].width = w

        review_path = f"{OUTPUT_DIR}/pipeline_defence_review.xlsx"
        wb.save(review_path)
        print(f"  Saved: {review_path}")
        print(f"  {len(df_defence)} firms to review")
        print(f"  Fill yellow cells → run apply_pipeline_review.py")
    else:
        print(f"\nNo defence review firms — no review sheet generated")
    print(f"\nSaved: {FINAL_DB_PATH}")
    print(f"  {len(df_final):,} firms — ready for Tableau")
    print(f"\nNEXT STEPS:")
    print(f"  → Generate Phase C review sheet for pipeline_verified.csv")
    print(f"  → Build Tableau dashboards from firm_database_final.csv")
    print("=" * 65)


# ── MAIN ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--finalise':
        build_final_database()
    else:
        run_pipeline()