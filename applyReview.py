"""
UK Space Sector — Apply Review Assessments Back to Merged Database

Reads the completed review_sheet.xlsx and merges your manual assessments
(defence_primary, node_confirmed, secondary_node, evidence_notes) back
into the seed_firms_merged.csv database.

Usage:
  1. Complete review_sheet.xlsx (fill in yellow cells)
  2. Run: python apply_review.py
  3. Output: seed_firms_reviewed.csv — ready for Stage 3 pipeline

Exclusion logic applied here:
  defence_primary=Yes  → firm excluded from final database
  defence_primary=Partial → firm included with dual_use=Yes flag
  defence_primary=No   → firm included as civil/commercial
"""

import pandas as pd
import openpyxl
import os
from datetime import date

MERGED_PATH  = "/Users/keerthanate/dissertation/data/seed_firms_merged.csv"
REVIEW_PATH  = "/Users/keerthanate/dissertation/data/review_sheet.xlsx"
OUTPUT_DIR   = "/Users/keerthanate/dissertation/data"
DATE_TODAY   = str(date.today())


def read_review_sheet(path):
    """Read completed review sheets from Excel."""
    wb = openpyxl.load_workbook(path, data_only=True)
    reviews = {}

    for sheet_name in ['Phase A — High Confidence',
                        'Phase B — Medium Confidence']:
        if sheet_name not in wb.sheetnames:
            continue

        ws = wb[sheet_name]

        # Data starts at row 6, columns:
        # 2=company_name, 10=defence_primary, 11=node_confirmed,
        # 12=secondary_node, 13=evidence_notes
        for row in ws.iter_rows(min_row=6, values_only=True):
            if not row[1]:  # no company name
                continue
            company_name = str(row[1]).strip()
            defence      = str(row[9]).strip()  if row[9]  else ''
            node_conf    = str(row[10]).strip() if row[10] else ''
            secondary    = str(row[11]).strip() if row[11] else ''
            evidence     = str(row[12]).strip() if row[12] else ''

            reviews[company_name] = {
                'defence_primary':    defence,
                'node_confirmed':     node_conf,
                'secondary_node':     secondary,
                'evidence_notes':     evidence,
            }

    print(f"Reviews loaded: {len(reviews)} firms assessed")
    return reviews


def apply_reviews(df, reviews):
    """Apply manual review assessments to the merged database."""

    applied = 0
    excluded = []

    for idx, row in df.iterrows():
        name = str(row['company_name']).strip()
        rev  = reviews.get(name, {})

        if not rev:
            continue

        applied += 1

        # Apply defence assessment
        defence = rev.get('defence_primary', '')
        if defence:
            df.at[idx, 'defence_primary'] = defence

        # Apply node correction if provided
        node_conf = rev.get('node_confirmed', '')
        if node_conf and node_conf not in ('', 'nan', '—'):
            df.at[idx, 'primary_node_original'] = row['primary_node']
            df.at[idx, 'primary_node'] = node_conf

        # Apply secondary node
        secondary = rev.get('secondary_node', '')
        if secondary and secondary not in ('', 'nan', '—'):
            df.at[idx, 'secondary_node'] = secondary

        # Add evidence notes to notes field
        evidence = rev.get('evidence_notes', '')
        if evidence:
            existing_notes = str(row.get('notes', ''))
            df.at[idx, 'notes'] = existing_notes + f' | Defence review: {evidence}'

        # Flag for exclusion
        if defence == 'Yes':
            excluded.append(name)

    return df, applied, excluded


def run():
    print("=" * 65)
    print("Apply Review Assessments to Merged Database")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    # Load merged database
    print(f"\nLoading merged database: {MERGED_PATH}")
    try:
        df = pd.read_csv(MERGED_PATH, low_memory=False)
    except FileNotFoundError:
        print("Merged CSV not found — run merge_sources.py first")
        return

    print(f"Total firms: {len(df):,}")

    # Load review sheet
    print(f"\nLoading review sheet: {REVIEW_PATH}")
    try:
        reviews = read_review_sheet(REVIEW_PATH)
    except FileNotFoundError:
        print("Review sheet not found — run generate_review_sheet.py first")
        return

    # Apply reviews
    df, applied, excluded = apply_reviews(df, reviews)
    print(f"\nReviews applied: {applied} firms updated")
    print(f"Firms flagged defence_primary=Yes: {len(excluded)}")
    if excluded:
        print(f"  These will be excluded from the final database:")
        for name in excluded:
            print(f"    — {name}")

    # ── SPLIT BY CONFIDENCE AND DEFENCE STATUS ────────────────────────────

    reviewed_names = set(reviews.keys())

    # High and Medium confidence — manually reviewed firms only
    df_verified = df[
        df['confidence_level'].isin(['High', 'Medium'])
    ].copy()

    # Low confidence — Source 1 CH bulk candidates not yet verified
    # These go through Stage 3 pipeline FIRST before manual review
    df_ch_unverified = df[
        df['confidence_level'] == 'Low'
    ].copy()

    # Apply review status to verified firms
    df_verified['review_status'] = df_verified['company_name'].apply(
        lambda x: 'Reviewed' if x in reviewed_names else 'Pending'
    )

    # Split verified into included and excluded
    df_included = df_verified[df_verified['defence_primary'] != 'Yes'].copy()
    df_excluded = df_verified[df_verified['defence_primary'] == 'Yes'].copy()

    print(f"\nVerified firms (High + Medium confidence): {len(df_verified):,}")
    print(f"  Included (defence_primary != Yes): {len(df_included):,}")
    print(f"  Excluded (defence_primary=Yes):    {len(df_excluded):,}")
    print(f"  Not yet reviewed:                  "
          f"{len(df_verified[df_verified['review_status']=='Pending']):,}")

    print(f"\nCH Bulk unverified (Low confidence):  {len(df_ch_unverified):,}")
    print(f"  These go through Stage 3 pipeline")
    print(f"  before manual defence/node review")

    # Summary by defence status for reviewed firms
    print(f"\nBy defence_primary (reviewed firms only):")
    for status in ['No', 'Partial', 'Yes', '']:
        label = status if status else '(not yet assessed)'
        count = len(df_verified[df_verified['defence_primary'] == status])
        print(f"  {label:<25} {count:>5,}")

    # Save outputs
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    included_path     = f"{OUTPUT_DIR}/seed_firms_reviewed.csv"
    excluded_path     = f"{OUTPUT_DIR}/seed_firms_excluded_defence.csv"
    unverified_path   = f"{OUTPUT_DIR}/seed_firms_ch_unverified.csv"

    df_included.to_csv(included_path, index=False)
    df_excluded.to_csv(excluded_path, index=False)
    df_ch_unverified.to_csv(unverified_path, index=False)

    print(f"\n{'='*65}")
    print("FILES SAVED")
    print(f"{'='*65}")
    print(f"  {included_path}")
    print(f"    → {len(df_included):,} reviewed firms (included in analysis)")
    print(f"  {excluded_path}")
    print(f"    → {len(df_excluded):,} firms (excluded — defence primary)")
    print(f"  {unverified_path}")
    print(f"    → {len(df_ch_unverified):,} CH bulk candidates")
    print(f"       (await Stage 3 pipeline before review)")
    print(f"\nNEXT STEPS:")
    print(f"  1. Complete yellow cells in review_sheet.xlsx if not done")
    print(f"     then run apply_review.py again")
    print(f"  2. Run space_pipeline.py on seed_firms_ch_unverified.csv")
    print(f"     to verify CH bulk candidates via Companies House API")
    print(f"  3. After pipeline, generate Phase C review sheet")
    print(f"     for surviving verified candidates")
    print("=" * 65)


if __name__ == "__main__":
    run()