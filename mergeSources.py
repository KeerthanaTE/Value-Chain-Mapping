"""
UK Space Sector — Source Merge Script

Merges Source 1 (Companies House Bulk) and Source 2 (ukspacetech.com)
into a single unified seed firm database.

Merge logic:
  1. Load both sources
  2. Standardise company names for matching
  3. Find firms appearing in both sources
  4. For matched firms: combine data, set source flags, use Source 2
     node assignment as it is more reliable (pre-curated, human-verified)
  5. For unmatched firms: retain from both sources with appropriate flags
  6. Output unified seed CSV ready for Stage 3 pipeline

Output:
  data/seed_firms_merged.csv

Source priority for node assignment:
  Source 2 (ukspacetech) > Source 1 (CH Bulk)
  Reason: ukspacetech is pre-curated and human-verified. Surrey Satellite
  appears as N3 in Source 2 vs N1 in Source 1 — Source 2 is correct.

Source priority for address/postcode:
  Source 1 (CH Bulk) > Source 2 (ukspacetech)
  Reason: Companies House has verified registered addresses.
"""

import pandas as pd
import re
import os
from datetime import date

# ── CONFIGURATION ──────────────────────────────────────────────────────────

SOURCE1_PATH = "/Users/keerthanate/dissertation/data/seed_firms_ch_bulk.csv"
SOURCE2_PATH = "/Users/keerthanate/dissertation/data/seed_firms_ukspacetech.csv"
OUTPUT_DIR   = "/Users/keerthanate/dissertation/data"
DATE_TODAY   = str(date.today())

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

# ── NAME NORMALISATION ─────────────────────────────────────────────────────

def normalise_name(name):
    """
    Normalise company name for fuzzy matching.
    Removes legal suffixes, punctuation, case differences.
    """
    if not name or str(name) == 'nan':
        return ''
    name = str(name).upper().strip()
    # Remove legal suffixes
    suffixes = [
        r'\bLIMITED\b', r'\bLTD\b', r'\bPLC\b', r'\bLLP\b',
        r'\bINC\b', r'\bCORPORATION\b', r'\bCORP\b', r'\bLLC\b',
        r'\bUK\b', r'\bU\.K\.\b', r'\bGROUP\b', r'\bHOLDINGS\b',
        r'\(UK\)', r'\(GB\)',
    ]
    for s in suffixes:
        name = re.sub(s, '', name)
    # Remove punctuation and extra spaces
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


# ── LOAD SOURCES ───────────────────────────────────────────────────────────

def load_sources():
    print("Loading Source 1 — Companies House Bulk...")
    df1 = pd.read_csv(SOURCE1_PATH, low_memory=False)
    print(f"  {len(df1):,} firms")

    print("Loading Source 2 — ukspacetech.com...")
    df2 = pd.read_csv(SOURCE2_PATH, low_memory=False)
    print(f"  {len(df2):,} firms")

    return df1, df2


# ── MERGE ─────────────────────────────────────────────────────────────────

def merge_sources(df1, df2):
    """
    Merge Source 1 and Source 2 into unified firm database.

    Matching strategy:
      1. Exact normalised name match
      2. Partial match — Source 2 name contained in Source 1 name
         (handles "Airbus" matching "Airbus Defence and Space Limited")
    """

    print("\nNormalising company names for matching...")
    df1['name_norm'] = df1['company_name'].apply(normalise_name)
    df2['name_norm'] = df2['company_name'].apply(normalise_name)

    # Build lookup from normalised name to Source 1 rows
    s1_lookup = {}
    for _, row in df1.iterrows():
        key = row['name_norm']
        if key and key not in s1_lookup:
            s1_lookup[key] = row

    # ── MATCH SOURCE 2 FIRMS TO SOURCE 1 ──────────────────────────────────

    print("Matching Source 2 firms to Source 1...")

    merged_rows = []
    s2_matched_names = set()
    match_count = 0

    for _, s2_row in df2.iterrows():
        s2_norm = s2_row['name_norm']
        s1_match = None

        # Strategy 1: exact normalised name match
        if s2_norm in s1_lookup:
            s1_match = s1_lookup[s2_norm]
            match_type = 'exact'

        # Strategy 2: Source 2 name contained within Source 1 name
        if s1_match is None:
            for s1_norm, s1_row in s1_lookup.items():
                if s2_norm and len(s2_norm) > 5 and s2_norm in s1_norm:
                    s1_match = s1_row
                    match_type = 'partial'
                    break

        # Strategy 3: Source 1 name contained within Source 2 name
        if s1_match is None:
            for s1_norm, s1_row in s1_lookup.items():
                if s1_norm and len(s1_norm) > 5 and s1_norm in s2_norm:
                    s1_match = s1_row
                    match_type = 'partial'
                    break

        if s1_match is not None:
            # MATCHED — combine data from both sources
            match_count += 1
            s2_matched_names.add(s2_norm)

            row = {
                # Identity — prefer Source 2 display name (cleaner)
                'company_name':           s2_row.get('company_name', ''),
                'company_name_ch':        s1_match.get('company_name', ''),
                'company_number':         s1_match.get('company_number', ''),
                'company_category':       s1_match.get('company_category', ''),
                'country_of_origin':      s1_match.get('country_of_origin', ''),
                'incorporated':           s1_match.get('incorporated', ''),
                'uri':                    s1_match.get('uri', ''),

                # Node assignment — Source 2 takes priority (more reliable)
                'primary_node':           s2_row.get('primary_node', '') or s1_match.get('primary_node', ''),
                'node_label':             s2_row.get('node_label', '') or s1_match.get('node_label', ''),
                'chain_position':         s2_row.get('chain_position', '') or s1_match.get('chain_position', ''),
                'secondary_node':         s2_row.get('secondary_node', ''),
                'review_needed':          s2_row.get('review_needed', 'Yes'),
                'review_reason':          s2_row.get('review_reason', ''),

                # SIC data from Source 1
                'sic_codes_full':         s1_match.get('sic_codes_full', ''),
                'matched_sic_code':       s1_match.get('matched_sic_code', ''),
                'matched_sic_text':       s1_match.get('matched_sic_text', ''),
                'sic_confidence':         s1_match.get('sic_confidence', ''),
                'sic_tier':               s1_match.get('sic_tier', ''),
                'sic_source':             s1_match.get('sic_source', ''),
                'oecd_activity_category': s2_row.get('oecd_activity_category', '') or s1_match.get('oecd_activity_category', ''),
                'requires_defence_check': s1_match.get('requires_defence_check', ''),

                # ukspacetech data from Source 2
                'website':                s2_row.get('website', ''),
                'description':            s2_row.get('description', ''),
                'location_hint':          s2_row.get('location_hint', ''),
                'ukspacetech_category':   s2_row.get('ukspacetech_category', ''),

                # Address from Source 1 (Companies House verified)
                'address_line1':          s1_match.get('address_line1', ''),
                'address_line2':          s1_match.get('address_line2', ''),
                'post_town':              s1_match.get('post_town', '') or s2_row.get('location_hint', ''),
                'county':                 s1_match.get('county', ''),
                'country':                s1_match.get('country', ''),
                'postcode':               s1_match.get('postcode', ''),

                # Source flags — appears in both
                'source_ch':              'Yes',
                'source_uksd':            'Yes',
                'source_scc':             '',
                'source_esa':             '',
                'source_website':         'Yes' if s2_row.get('website') else '',

                # Pipeline fields
                'supply_hierarchy':       '',
                'defence_primary':        '',
                'space_peripheral':       '',
                'ch_verified':            '',

                # Metadata
                'notes': (
                    f"Matched: Source 1 ({match_type}) + Source 2 (ukspacetech). "
                    f"Node from Source 2. Address from Source 1."
                ),
                'data_collection_date':   DATE_TODAY,
                'extraction_source':      'CH_BULK+UKSPACETECH',
                'match_type':             match_type,
                'confidence_level':       'High',  # appears in both sources
            }
            merged_rows.append(row)

        else:
            # Source 2 ONLY — not found in Source 1
            row = {
                'company_name':           s2_row.get('company_name', ''),
                'company_name_ch':        '',
                'company_number':         '',
                'company_category':       '',
                'country_of_origin':      '',
                'incorporated':           '',
                'uri':                    '',
                'primary_node':           s2_row.get('primary_node', ''),
                'node_label':             s2_row.get('node_label', ''),
                'chain_position':         s2_row.get('chain_position', ''),
                'secondary_node':         '',
                'review_needed':          s2_row.get('review_needed', 'Yes'),
                'review_reason':          s2_row.get('review_reason', ''),
                'sic_codes_full':         '',
                'matched_sic_code':       '',
                'matched_sic_text':       '',
                'sic_confidence':         '',
                'sic_tier':               '',
                'sic_source':             '',
                'oecd_activity_category': s2_row.get('oecd_activity_category', ''),
                'requires_defence_check': '',
                'website':                s2_row.get('website', ''),
                'description':            s2_row.get('description', ''),
                'location_hint':          s2_row.get('location_hint', ''),
                'ukspacetech_category':   s2_row.get('ukspacetech_category', ''),
                'address_line1':          '',
                'address_line2':          '',
                'post_town':              s2_row.get('location_hint', ''),
                'county':                 '',
                'country':                'United Kingdom',
                'postcode':               '',
                'source_ch':              'No',
                'source_uksd':            'Yes',
                'source_scc':             '',
                'source_esa':             '',
                'source_website':         'Yes' if s2_row.get('website') else '',
                'supply_hierarchy':       '',
                'defence_primary':        '',
                'space_peripheral':       '',
                'ch_verified':            '',
                'notes': (
                    'Source 2 only (ukspacetech). '
                    'Not found in CH Bulk — may use different legal name. '
                    'CH number to be found at Stage 3 via API search.'
                ),
                'data_collection_date':   DATE_TODAY,
                'extraction_source':      'UKSPACETECH',
                'match_type':             'no_match',
                'confidence_level':       'Medium',
            }
            merged_rows.append(row)

    # ── ADD SOURCE 1 ONLY FIRMS ────────────────────────────────────────────
    # Firms in CH Bulk that did not match any Source 2 firm

    print("Adding Source 1-only firms...")
    s1_only_count = 0

    for _, s1_row in df1.iterrows():
        s1_norm = s1_row['name_norm']
        if s1_norm in s2_matched_names:
            continue  # already included via match

        # Check if this Source 1 firm was matched via partial match
        already_matched = False
        for s2_norm in s2_matched_names:
            if (s2_norm and s1_norm and
                (s2_norm in s1_norm or s1_norm in s2_norm)):
                already_matched = True
                break

        if already_matched:
            continue

        s1_only_count += 1
        row = {
            'company_name':           s1_row.get('company_name', ''),
            'company_name_ch':        s1_row.get('company_name', ''),
            'company_number':         s1_row.get('company_number', ''),
            'company_category':       s1_row.get('company_category', ''),
            'country_of_origin':      s1_row.get('country_of_origin', ''),
            'incorporated':           s1_row.get('incorporated', ''),
            'uri':                    s1_row.get('uri', ''),
            'primary_node':           s1_row.get('primary_node', ''),
            'node_label':             s1_row.get('node_label', ''),
            'chain_position':         s1_row.get('chain_position', ''),
            'secondary_node':         '',
            'review_needed':          'Yes',
            'review_reason':          'Source 1 only — node assignment from SIC code, not verified.',
            'sic_codes_full':         s1_row.get('sic_codes_full', ''),
            'matched_sic_code':       s1_row.get('matched_sic_code', ''),
            'matched_sic_text':       s1_row.get('matched_sic_text', ''),
            'sic_confidence':         s1_row.get('sic_confidence', ''),
            'sic_tier':               s1_row.get('sic_tier', ''),
            'sic_source':             s1_row.get('sic_source', ''),
            'oecd_activity_category': s1_row.get('oecd_activity_category', ''),
            'requires_defence_check': s1_row.get('requires_defence_check', ''),
            'website':                '',
            'description':            '',
            'location_hint':          '',
            'ukspacetech_category':   '',
            'address_line1':          s1_row.get('address_line1', ''),
            'address_line2':          s1_row.get('address_line2', ''),
            'post_town':              s1_row.get('post_town', ''),
            'county':                 s1_row.get('county', ''),
            'country':                s1_row.get('country', ''),
            'postcode':               s1_row.get('postcode', ''),
            'source_ch':              'Yes',
            'source_uksd':            'No',
            'source_scc':             '',
            'source_esa':             '',
            'source_website':         '',
            'supply_hierarchy':       '',
            'defence_primary':        '',
            'space_peripheral':       '',
            'ch_verified':            '',
            'notes':                  'Source 1 only (CH Bulk). Node indicative from SIC match.',
            'data_collection_date':   DATE_TODAY,
            'extraction_source':      'CH_BULK',
            'match_type':             'source1_only',
            'confidence_level':       'Low',
        }
        merged_rows.append(row)

    df_merged = pd.DataFrame(merged_rows)

    # Clean up working column
    df1.drop(columns=['name_norm'], inplace=True, errors='ignore')
    df2.drop(columns=['name_norm'], inplace=True, errors='ignore')

    return df_merged, match_count, s1_only_count


# ── SUMMARY ────────────────────────────────────────────────────────────────

def print_summary(df, match_count, s1_only_count):
    total = len(df)
    s2_only = len(df[df['match_type'] == 'no_match'])
    both    = len(df[df['match_type'].isin(['exact', 'partial'])])

    print(f"\n{'='*65}")
    print("MERGE SUMMARY")
    print(f"{'='*65}")
    print(f"\nTotal firms in merged database: {total:,}")
    print(f"\nBreakdown by source:")
    print(f"  In both Source 1 and Source 2:  {both:>6,}  (confidence=High)")
    print(f"  Source 2 only (ukspacetech):    {s2_only:>6,}  (confidence=Medium)")
    print(f"  Source 1 only (CH Bulk):        {s1_only_count:>6,}  (confidence=Low)")

    print(f"\nBy confidence level:")
    for conf in ['High', 'Medium', 'Low']:
        count = len(df[df['confidence_level'] == conf])
        print(f"  {conf:<8} {count:>6,}")

    print(f"\nBy primary node:")
    for node in ['N1','N2','N3','N4','N5','N6','N7','N8','N9']:
        count = len(df[df['primary_node'] == node])
        if count > 0:
            label = NODE_LABELS.get(node, '')
            print(f"  {node}  {label:<42} {count:>6,}")

    print(f"\nHigh confidence firms — appear in both sources (sample 20):")
    high = df[df['confidence_level'] == 'High']
    cols = ['company_name', 'primary_node', 'ukspacetech_category', 'postcode']
    print(high[cols].head(20).to_string(index=False))

    print(f"\nFirms needing Stage 3 node review: {len(df[df['review_needed']=='Yes']):,}")
    print(f"Firms requiring defence check:      {len(df[df['requires_defence_check']=='Yes']):,}")
    print(f"Firms with website:                 {len(df[df['website'].notna() & (df['website']!='')]):,}")
    print(f"Firms with CH number:               {len(df[df['company_number'].notna() & (df['company_number']!='')]):,}")
    print(f"Firms with postcode:                {len(df[df['postcode'].notna() & (df['postcode']!='')]):,}")


# ── SAVE ───────────────────────────────────────────────────────────────────

def save_output(df):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = f"{OUTPUT_DIR}/seed_firms_merged.csv"
    df.to_csv(output_path, index=False)

    print(f"\n{'='*65}")
    print("FILE SAVED")
    print(f"{'='*65}")
    print(f"  {output_path}")
    print(f"  {len(df):,} firms")
    print(f"\nNew columns vs individual sources:")
    print(f"  company_name_ch   — CH registered name (may differ from display name)")
    print(f"  confidence_level  — High/Medium/Low based on number of sources")
    print(f"  match_type        — exact/partial/no_match/source1_only")
    print(f"  source_ch         — Yes if firm found in Companies House bulk")
    print(f"  source_uksd       — Yes if firm found in ukspacetech.com")
    print(f"\nNEXT STEPS:")
    print(f"  → Stage 3: space_pipeline.py — CH API verification")
    print(f"    For each firm with company_number: verify active status,")
    print(f"    get employee band, confirm address")
    print(f"    For Source 2-only firms: search CH API by name to get number")
    print(f"  → Build Tableau dashboards from verified firm database")
    print("=" * 65)


# ── MAIN ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("UK Space Sector — Source Merge")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    df1, df2 = load_sources()
    df_merged, match_count, s1_only_count = merge_sources(df1, df2)
    print_summary(df_merged, match_count, s1_only_count)
    save_output(df_merged)