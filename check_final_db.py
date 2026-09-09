"""
UK Space Sector — Tableau Data Preparation
MSc Business Analytics and Big Data Dissertation
University of Liverpool

Reads firm_database_final.csv and adds columns needed for Tableau:
  - region          — UK region from postcode prefix
  - postcode_area   — first 2-4 chars of postcode (for map grouping)
  - node_order      — integer 1-9 for sorting nodes in Tableau
  - node_short      — short node label for chart axes
  - supply_hierarchy_label — Prime / Integrator / Supplier / Service Provider
  - firm_age        — years since incorporation
  - has_website     — Yes/No for filtering
  - source_label    — readable source description
  - defence_label   — readable defence status
  - confidence_label — readable confidence level

Output:
  data/firm_database_tableau.csv — Tableau-ready file
"""

import pandas as pd
import re
import os
from datetime import date

INPUT_PATH  = "/Users/keerthanate/dissertation/data/firm_database_final.csv"
OUTPUT_PATH = "/Users/keerthanate/dissertation/data/firm_database_tableau.csv"
DATE_TODAY  = str(date.today())

# ── UK POSTCODE TO REGION MAP ──────────────────────────────────────────────
# Maps postcode area prefix to UK region
# Source: ONS postcode directory

POSTCODE_REGION = {
    # Greater London
    'E': 'Greater London', 'EC': 'Greater London', 'N': 'Greater London',
    'NW': 'Greater London', 'SE': 'Greater London', 'SW': 'Greater London',
    'W': 'Greater London', 'WC': 'Greater London', 'WD': 'Greater London',
    # South East
    'AL': 'South East', 'BN': 'South East', 'BR': 'South East',
    'CM': 'South East', 'CR': 'South East', 'CT': 'South East',
    'DA': 'South East', 'EN': 'South East', 'GU': 'South East',
    'HA': 'South East', 'HP': 'South East', 'KT': 'South East',
    'ME': 'South East', 'MK': 'South East', 'OX': 'South East',
    'RG': 'South East', 'RH': 'South East', 'SL': 'South East',
    'SM': 'South East', 'SN': 'South East', 'SO': 'South East',
    'SP': 'South East', 'SS': 'South East', 'TN': 'South East',
    'TW': 'South East', 'UB': 'South East',
    # South West
    'BA': 'South West', 'BH': 'South West', 'BS': 'South West',
    'DT': 'South West', 'EX': 'South West', 'GL': 'South West',
    'PL': 'South West', 'TA': 'South West', 'TQ': 'South West',
    'TR': 'South West',
    # East of England
    'CB': 'East of England', 'CO': 'East of England', 'IP': 'East of England',
    'LU': 'East of England', 'NR': 'East of England', 'PE': 'East of England',
    'SG': 'East of England',
    # East Midlands
    'DE': 'East Midlands', 'DN': 'East Midlands', 'LE': 'East Midlands',
    'LN': 'East Midlands', 'NG': 'East Midlands', 'NN': 'East Midlands',
    'S': 'East Midlands',
    # West Midlands
    'B': 'West Midlands', 'CV': 'West Midlands', 'DY': 'West Midlands',
    'HR': 'West Midlands', 'ST': 'West Midlands', 'TF': 'West Midlands',
    'WR': 'West Midlands', 'WS': 'West Midlands', 'WV': 'West Midlands',
    # Yorkshire and The Humber
    'BD': 'Yorkshire and The Humber', 'HD': 'Yorkshire and The Humber',
    'HG': 'Yorkshire and The Humber', 'HU': 'Yorkshire and The Humber',
    'HX': 'Yorkshire and The Humber', 'LS': 'Yorkshire and The Humber',
    'WF': 'Yorkshire and The Humber', 'YO': 'Yorkshire and The Humber',
    # North West
    'BB': 'North West', 'BL': 'North West', 'CA': 'North West',
    'CH': 'North West', 'CW': 'North West', 'FY': 'North West',
    'L': 'North West', 'LA': 'North West', 'M': 'North West',
    'OL': 'North West', 'PR': 'North West', 'SK': 'North West',
    'WA': 'North West', 'WN': 'North West',
    # North East
    'DH': 'North East', 'DL': 'North East', 'NE': 'North East',
    'SR': 'North East', 'TS': 'North East',
    # Scotland
    'AB': 'Scotland', 'DD': 'Scotland', 'DG': 'Scotland',
    'EH': 'Scotland', 'FK': 'Scotland', 'G': 'Scotland',
    'HS': 'Scotland', 'IV': 'Scotland', 'KA': 'Scotland',
    'KW': 'Scotland', 'KY': 'Scotland', 'ML': 'Scotland',
    'PA': 'Scotland', 'PH': 'Scotland', 'TD': 'Scotland',
    'ZE': 'Scotland',
    # Wales
    'CF': 'Wales', 'LD': 'Wales', 'LL': 'Wales', 'NP': 'Wales',
    'SA': 'Wales', 'SY': 'Wales',
    # Northern Ireland
    'BT': 'Northern Ireland',
}

# Longer prefixes checked first (e.g. 'NW' before 'N')
POSTCODE_REGION_SORTED = sorted(
    POSTCODE_REGION.items(), key=lambda x: -len(x[0])
)

def get_region(postcode):
    """Derive UK region from postcode prefix."""
    if not postcode or str(postcode) in ('nan', '', 'None'):
        return 'Unknown'
    pc = str(postcode).upper().strip()
    # Extract letter prefix only
    prefix = re.match(r'^([A-Z]{1,2})', pc)
    if not prefix:
        return 'Unknown'
    area = prefix.group(1)
    # Check two-letter first then one-letter
    for key, region in POSTCODE_REGION_SORTED:
        if area == key or pc.startswith(key):
            return region
    return 'Unknown'


def get_postcode_area(postcode):
    """Extract postcode area (e.g. 'SK10 1JE' → 'SK')."""
    if not postcode or str(postcode) in ('nan', '', 'None'):
        return ''
    pc = str(postcode).upper().strip()
    match = re.match(r'^([A-Z]{1,2})', pc)
    return match.group(1) if match else ''


def get_supply_hierarchy(node, confidence, source_uksd):
    """
    Assign supply hierarchy tier based on node and source.
    Prime: N3, N5, N6 — full system integrators and operators
    Integrator: N2, N4 — subsystem integrators
    Supplier: N1 — component and material suppliers
    Service Provider: N7, N8, N9 — downstream and enabling
    """
    node = str(node).strip()
    if node in ('N3', 'N5', 'N6'):
        return 'Prime / Operator'
    elif node in ('N2', 'N4'):
        return 'Integrator'
    elif node == 'N1':
        return 'Supplier'
    elif node in ('N7', 'N8'):
        return 'Service Provider'
    elif node == 'N9':
        return 'Enabling'
    return 'Unclassified'


def get_firm_age(incorporated):
    """Calculate firm age from incorporation date."""
    if not incorporated or str(incorporated) in ('nan', '', 'None'):
        return None
    try:
        year = int(str(incorporated)[:4])
        current_year = int(DATE_TODAY[:4])
        age = current_year - year
        return age if 0 <= age <= 200 else None
    except Exception:
        return None


def run():
    print("=" * 65)
    print("Tableau Data Preparation")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    print(f"\nLoading: {INPUT_PATH}")
    df = pd.read_csv(INPUT_PATH, low_memory=False)
    print(f"  {len(df):,} firms, {len(df.columns)} columns")

    # ── BEST POSTCODE — use ch_postcode if postcode is empty ──────────────
    df['postcode_best'] = df.apply(
        lambda r: str(r.get('ch_postcode','') or r.get('postcode','') or '').strip(),
        axis=1
    )
    df['postcode_best'] = df['postcode_best'].replace('nan','')

    # ── REGION ────────────────────────────────────────────────────────────
    print("  Adding region from postcode...")
    df['region'] = df['postcode_best'].apply(get_region)
    df['postcode_area'] = df['postcode_best'].apply(get_postcode_area)

    # ── NODE ORDER AND SHORT LABELS ────────────────────────────────────────
    NODE_ORDER = {
        'N1':1,'N2':2,'N3':3,'N4':4,'N5':5,
        'N6':6,'N7':7,'N8':8,'N9':9
    }
    NODE_SHORT = {
        'N1': 'N1 Components',
        'N2': 'N2 Subsystems',
        'N3': 'N3 Spacecraft Mfg',
        'N4': 'N4 Ground Segment',
        'N5': 'N5 Launch',
        'N6': 'N6 Operations',
        'N7': 'N7 Data & Analytics',
        'N8': 'N8 Applications',
        'N9': 'N9 Enabling',
    }
    df['node_order']  = df['primary_node'].map(NODE_ORDER)
    df['node_short']  = df['primary_node'].map(NODE_SHORT)

    # ── SUPPLY HIERARCHY ──────────────────────────────────────────────────
    print("  Adding supply hierarchy...")
    df['supply_hierarchy_label'] = df.apply(
        lambda r: get_supply_hierarchy(
            r.get('primary_node',''),
            r.get('confidence_level',''),
            r.get('source_uksd','')
        ), axis=1
    )

    # ── FIRM AGE ──────────────────────────────────────────────────────────
    print("  Calculating firm age...")
    df['firm_age'] = df.apply(
        lambda r: get_firm_age(
            r.get('ch_incorporated','') or r.get('incorporated','')
        ), axis=1
    )
    df['incorporation_year'] = df.apply(
        lambda r: int(str(r.get('ch_incorporated','') or
                          r.get('incorporated','') or '')[:4])
        if str(r.get('ch_incorporated','') or
               r.get('incorporated','') or '')[:4].isdigit()
        else None, axis=1
    )

    # ── HAS WEBSITE ───────────────────────────────────────────────────────
    df['has_website'] = df['website'].apply(
        lambda x: 'Yes' if str(x) not in ('nan','','None') else 'No'
    )

    # ── READABLE LABELS ───────────────────────────────────────────────────
    df['defence_label'] = df['defence_primary'].map({
        'No':      'Civil / Commercial',
        'Partial': 'Dual-Use (Civil + Defence)',
        'Yes':     'Defence Primary',
        '':        'Not assessed',
    }).fillna('Not assessed')

    df['confidence_label'] = df['confidence_level'].map({
        'Very High': 'Very High — all 3 sources',
        'High':      'High — 2 sources',
        'Medium':    'Medium — curated source only',
        'Low':       'Low — SIC code only',
        '':          'Pipeline verified',
    }).fillna('Pipeline verified')

    df['source_label'] = df.apply(lambda r: ' + '.join(filter(None, [
        'Companies House' if str(r.get('source_ch','')) == 'Yes' else '',
        'ukspacetech'     if str(r.get('source_uksd','')) == 'Yes' else '',
        'Pipeline'        if str(r.get('pipeline_status','')) == 'verified' else '',
    ])) or 'Pipeline', axis=1)

    # ── CHAIN POSITION CLEAN ──────────────────────────────────────────────
    # Ensure all firms have chain_position
    CHAIN_MAP = {
    'N1':'Upstream','N2':'Upstream','N3':'Upstream',
    'N4':'Midstream','N5':'Midstream','N7':'Midstream',
    'N6':'Downstream','N8':'Downstream','N9':'Downstream',
}
    df['chain_position'] = df.apply(
        lambda r: CHAIN_MAP.get(str(r.get('primary_node','')),
                                str(r.get('chain_position','') or '')),
        axis=1
    )

    # ── SUMMARY ───────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("PREP SUMMARY")
    print(f"{'='*65}")
    print(f"\nTotal firms: {len(df):,}")

    print(f"\nBy region:")
    for region, count in df['region'].value_counts().items():
        print(f"  {region:<30} {count:>5,}")

    print(f"\nBy node (with short label):")
    for node in ['N1','N2','N3','N4','N5','N6','N7','N8','N9']:
        count = len(df[df['primary_node']==node])
        if count:
            print(f"  {NODE_SHORT.get(node,node):<25} {count:>5,}")

    print(f"\nBy chain position:")
    for pos in ['Upstream','Downstream','Enabling']:
        count = len(df[df['chain_position']==pos])
        if count:
            print(f"  {pos:<14} {count:>5,}")

    print(f"\nBy defence status:")
    for label, count in df['defence_label'].value_counts().items():
        print(f"  {label:<35} {count:>5,}")

    print(f"\nBy supply hierarchy:")
    for label, count in df['supply_hierarchy_label'].value_counts().items():
        print(f"  {label:<25} {count:>5,}")

    print(f"\nWith postcode (for map): {(df['postcode_best']!='').sum():,}")
    print(f"With website:            {(df['has_website']=='Yes').sum():,}")
    print(f"With firm age:           {df['firm_age'].notna().sum():,}")
    print(f"Unknown region:          {(df['region']=='Unknown').sum():,}")

    # ── SAVE ──────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"\n{'='*65}")
    print("FILE SAVED")
    print(f"{'='*65}")
    print(f"  {OUTPUT_PATH}")
    print(f"  {len(df):,} firms | {len(df.columns)} columns")
    print(f"\nNew columns added for Tableau:")
    new_cols = [
        'region','postcode_area','postcode_best',
        'node_order','node_short',
        'supply_hierarchy_label','firm_age','incorporation_year',
        'has_website','defence_label','confidence_label','source_label',
    ]
    for col in new_cols:
        print(f"  {col}")
    print(f"\nNEXT STEPS:")
    print(f"  → Open Tableau Public")
    print(f"  → Connect to firm_database_tableau.csv")
    print(f"  → Build Dashboard 1: UK Value Chain Map")
    print("=" * 65)


if __name__ == "__main__":
    run()