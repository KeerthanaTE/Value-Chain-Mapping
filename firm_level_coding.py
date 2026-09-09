"""
UK Space Sector — Firm-Level Qualitative Coding
MSc Business Analytics and Big Data Dissertation
University of Liverpool

Codes each firm against qualitative attributes for segment-level analysis.
Aggregates to Upstream / Midstream / Downstream segments.

Coding dimensions:
  1. activity_type      — what the firm does (from ukspacetech_category + matched_sic_text)
  2. commercial_maturity — pre-2000 (Established), 2000-2015 (Mature), post-2015 (NewSpace)
  3. governance_type    — Civil/Commercial, Dual-Use, Not assessed
  4. supply_tier        — from supply_hierarchy_label
  5. segment            — Upstream / Midstream / Downstream (from chain_position)

Outputs:
  1. firm_database_coded.csv     — full firm database with qualitative codes
  2. segment_activity_types.csv  — activity type distribution per segment
  3. segment_maturity.csv        — commercial maturity profile per segment
  4. segment_governance.csv      — governance mix per segment
  5. segment_supply_tier.csv     — supply hierarchy per segment
  6. segment_summary.csv         — combined summary table for Chapter 5
"""

import pandas as pd
import re
import os
from datetime import date

INPUT_PATH  = "/Users/keerthanate/dissertation/data/firm_database_tableau.csv"
OUTPUT_DIR  = "/Users/keerthanate/dissertation/data/qualitative"
DATE_TODAY  = str(date.today())

# ── ACTIVITY TYPE CLASSIFICATION ───────────────────────────────────────────
# Maps ukspacetech_category and SIC text to readable activity types
# Used for qualitative characterisation of what firms actually do

ACTIVITY_PATTERNS = {
    # Upstream
    'Components and Materials':
        [r'component', r'material', r'electron', r'sensor',
         r'optic', r'structure', r'thermal', r'mechanic'],
    'Subsystems and Payloads':
        [r'subsystem', r'payload', r'instrument', r'antenna',
         r'power system', r'propulsion', r'reaction wheel',
         r'attitude control', r'avionics'],
    'Satellite Manufacturing':
        [r'satellite.*manuf', r'spacecraft.*manuf',
         r'satellite.*design', r'spacecraft.*design',
         r'satellite.*integrat', r'smallsat', r'cubesat'],
    # Midstream
    'Launch Services':
        [r'launch', r'rocket', r'launcher', r'propellant',
         r'spaceport', r'launch.*vehicle', r'orbital.*transport'],
    'Ground Infrastructure':
        [r'ground.*station', r'ground.*segment', r'telemetry',
         r'tracking', r'command', r'mission.*control',
         r'antenna.*network', r'ground.*system'],
    'Data Processing and Analytics':
        [r'data.*process', r'data.*analytic', r'earth.*obs',
         r'remote.*sens', r'geospat', r'imagery', r'algorithm',
         r'machine.*learn', r'ai.*space', r'satellite.*data'],
    # Downstream
    'Satellite Operations':
        [r'satellite.*operat', r'fleet.*manag', r'in.orbit',
         r'debris.*remov', r'space.*logistic', r'orbital.*service'],
    'Satellite Communications':
        [r'satcom', r'satellite.*commun', r'broadband.*satellite',
         r'vsat', r'dth', r'direct.*broadcast', r'connectivity'],
    'Navigation and Positioning':
        [r'gnss', r'gps', r'navigation', r'positioning',
         r'timing', r'navic', r'galileo.*service'],
    'Earth Observation Applications':
        [r'earth.*observ', r'eo.*service', r'mapping',
         r'disaster.*monitor', r'agriculture.*space',
         r'climate.*monitor', r'environmental.*monitor'],
    'Space Applications and Services':
        [r'space.*application', r'space.*service',
         r'downstream.*service', r'value.*added.*service'],
    # Enabling
    'Space Consultancy and R&D':
        [r'consult', r'research', r'r.d', r'innovation',
         r'engineering.*service', r'technical.*service'],
    'Space Finance and Legal':
        [r'insur', r'financ', r'legal', r'law', r'regulat',
         r'licens', r'patent', r'investment.*space'],
    'Space Education and Training':
        [r'educat', r'train', r'academ', r'universit',
         r'institute', r'research.*centre'],
    'Other Enabling':
        [],  # catch-all
}


def classify_activity(row):
    """Classify firm activity type from ukspacetech_category and SIC text."""
    node = str(row.get('primary_node', ''))
    cat  = str(row.get('ukspacetech_category', '') or '').lower()
    sic  = str(row.get('matched_sic_text', '') or '').lower()
    name = str(row.get('company_name', '') or '').lower()
    combined = cat + ' ' + sic + ' ' + name

    # Try each pattern
    for activity, patterns in ACTIVITY_PATTERNS.items():
        for p in patterns:
            if re.search(p, combined):
                return activity

    # Fall back to node-based defaults
    defaults = {
        'N1': 'Components and Materials',
        'N2': 'Subsystems and Payloads',
        'N3': 'Satellite Manufacturing',
        'N4': 'Ground Infrastructure',
        'N5': 'Launch Services',
        'N6': 'Satellite Operations',
        'N7': 'Data Processing and Analytics',
        'N8': 'Space Applications and Services',
        'N9': 'Space Consultancy and R&D',
    }
    return defaults.get(node, 'Other')


def classify_maturity(incorporation_year):
    """Classify firm commercial maturity from incorporation year."""
    if not incorporation_year or pd.isna(incorporation_year):
        return 'Unknown'
    try:
        year = int(float(incorporation_year))
        if year < 2000:
            return 'Established (pre-2000)'
        elif year <= 2015:
            return 'Mature (2000-2015)'
        else:
            return 'NewSpace (post-2015)'
    except Exception:
        return 'Unknown'


def run():
    print("=" * 65)
    print("Firm-Level Qualitative Coding")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    # Load database
    print(f"\nLoading: {INPUT_PATH}")
    df = pd.read_csv(INPUT_PATH, low_memory=False)
    print(f"  {len(df):,} firms, {len(df.columns)} columns")

    # ── APPLY QUALITATIVE CODES ────────────────────────────────────────────

    # 1. Activity type
    print("\nCoding activity types...")
    df['activity_type'] = df.apply(classify_activity, axis=1)

    # 2. Commercial maturity
    print("Coding commercial maturity...")
    inc_col = 'incorporation_year' if 'incorporation_year' in df.columns \
              else 'ch_incorporated'
    df['commercial_maturity'] = df[inc_col].apply(classify_maturity) \
        if inc_col in df.columns else 'Unknown'

    # 3. Governance type — already in defence_label
    df['governance_type'] = df['defence_label'].fillna('Not assessed')

    # 4. Supply tier — already in supply_hierarchy_label
    df['supply_tier'] = df['supply_hierarchy_label'].fillna('Unclassified')

    # 5. Segment — from chain_position
    df['segment'] = df['chain_position'].fillna('Unknown')

    # ── SAVE CODED DATABASE ────────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    coded_path = f"{OUTPUT_DIR}/firm_database_coded.csv"
    df.to_csv(coded_path, index=False)
    print(f"\nCoded database saved: {coded_path}")

    # ── AGGREGATIONS ───────────────────────────────────────────────────────

    segments = ['Upstream', 'Midstream', 'Downstream']

    # Summary statistics per segment
    print("\nGenerating segment summaries...")
    summary_rows = []
    for seg in segments:
        seg_df = df[df['segment'] == seg]
        total = len(seg_df)
        if total == 0:
            continue

        pct = round(total / len(df) * 100, 1)
        nodes = ', '.join(sorted(seg_df['primary_node'].unique()))

        # Maturity
        maturity = seg_df['commercial_maturity'].value_counts()
        newspace_pct = round(
            maturity.get('NewSpace (post-2015)', 0) / total * 100, 1)
        established_pct = round(
            maturity.get('Established (pre-2000)', 0) / total * 100, 1)

        # Governance
        gov = seg_df['governance_type'].value_counts()
        civil_pct = round(
            gov.get('Civil / Commercial', 0) / total * 100, 1)
        dualuse_pct = round(
            gov.get('Dual-Use (Civil + Defence)', 0) / total * 100, 1)

        # Mean firm age
        if 'firm_age' in seg_df.columns:
            mean_age = round(seg_df['firm_age'].dropna().mean(), 1)
        else:
            mean_age = None

        # Geographic spread
        if 'region_ons' in seg_df.columns:
            regions = seg_df['region_ons'].nunique()
        else:
            regions = None

        # Top activity types
        top_activities = seg_df['activity_type'].value_counts().head(3)
        top_act_str = '; '.join(
            [f"{k} ({v})" for k, v in top_activities.items()])

        # Top nodes
        top_nodes = seg_df.groupby('primary_node').size()\
            .sort_values(ascending=False).head(3)
        top_nodes_str = '; '.join(
            [f"{k} ({v})" for k, v in top_nodes.items()])

        # Supply tier
        top_tier = seg_df['supply_tier'].value_counts().index[0] \
            if len(seg_df) > 0 else 'N/A'

        summary_rows.append({
            'segment':              seg,
            'nodes':                nodes,
            'firm_count':           total,
            'pct_of_total':         pct,
            'mean_firm_age':        mean_age,
            'geographic_regions':   regions,
            'established_pct':      established_pct,
            'newspace_pct':         newspace_pct,
            'civil_commercial_pct': civil_pct,
            'dual_use_pct':         dualuse_pct,
            'dominant_supply_tier': top_tier,
            'top_activity_types':   top_act_str,
            'top_nodes':            top_nodes_str,
        })

    df_summary = pd.DataFrame(summary_rows)
    summary_path = f"{OUTPUT_DIR}/segment_summary.csv"
    df_summary.to_csv(summary_path, index=False)

    # Activity type distribution per segment
    act_rows = []
    for seg in segments:
        seg_df = df[df['segment'] == seg]
        counts = seg_df['activity_type'].value_counts()
        for act, count in counts.items():
            act_rows.append({
                'segment': seg,
                'activity_type': act,
                'firm_count': count,
                'pct_of_segment': round(count / len(seg_df) * 100, 1)
            })
    pd.DataFrame(act_rows).to_csv(
        f"{OUTPUT_DIR}/segment_activity_types.csv", index=False)

    # Maturity distribution per segment
    mat_rows = []
    for seg in segments:
        seg_df = df[df['segment'] == seg]
        counts = seg_df['commercial_maturity'].value_counts()
        for mat, count in counts.items():
            mat_rows.append({
                'segment': seg,
                'maturity': mat,
                'firm_count': count,
                'pct_of_segment': round(count / len(seg_df) * 100, 1)
            })
    pd.DataFrame(mat_rows).to_csv(
        f"{OUTPUT_DIR}/segment_maturity.csv", index=False)

    # Governance per segment
    gov_rows = []
    for seg in segments:
        seg_df = df[df['segment'] == seg]
        counts = seg_df['governance_type'].value_counts()
        for gov, count in counts.items():
            gov_rows.append({
                'segment': seg,
                'governance_type': gov,
                'firm_count': count,
                'pct_of_segment': round(count / len(seg_df) * 100, 1)
            })
    pd.DataFrame(gov_rows).to_csv(
        f"{OUTPUT_DIR}/segment_governance.csv", index=False)

    # ── PRINT SUMMARY ─────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("SEGMENT SUMMARY")
    print(f"{'='*65}")

    for _, row in df_summary.iterrows():
        print(f"\n{row['segment'].upper()} — {row['firm_count']} firms "
              f"({row['pct_of_total']}% of total)")
        print(f"  Nodes: {row['nodes']}")
        print(f"  Mean firm age: {row['mean_firm_age']} years")
        print(f"  Geographic spread: {row['geographic_regions']} regions")
        print(f"  Established (pre-2000): {row['established_pct']}%")
        print(f"  NewSpace (post-2015): {row['newspace_pct']}%")
        print(f"  Civil/Commercial: {row['civil_commercial_pct']}%")
        print(f"  Dual-Use: {row['dual_use_pct']}%")
        print(f"  Dominant supply tier: {row['dominant_supply_tier']}")
        print(f"  Top activities: {row['top_activity_types']}")

    print(f"\n{'='*65}")
    print("FILES SAVED")
    print(f"{'='*65}")
    print(f"  {OUTPUT_DIR}/firm_database_coded.csv")
    print(f"  {OUTPUT_DIR}/segment_summary.csv")
    print(f"  {OUTPUT_DIR}/segment_activity_types.csv")
    print(f"  {OUTPUT_DIR}/segment_maturity.csv")
    print(f"  {OUTPUT_DIR}/segment_governance.csv")
    print("=" * 65)


if __name__ == "__main__":
    run()