"""
Join firm postcodes to ONS Postcode Lookup to get precise lat/lon.

Source: Office for National Statistics (2026)
National Statistics Postcode Lookup (May 2026)
Available at: https://geoportal.statistics.gov.uk

This adds:
  - latitude / longitude  — precise coordinates per postcode
  - rgn25cd               — ONS region code
  - ctry25cd              — country code
"""
import pandas as pd
import json
import os

FIRM_PATH    = "/Users/keerthanate/dissertation/data/firm_database_tableau.csv"
LOOKUP_PATH  = "/Users/keerthanate/Downloads/National_Statistics_Postcode_Lookup_(May_2026)_for_the_United_Kingdom.geojson"
OUTPUT_PATH  = "/Users/keerthanate/dissertation/data/firm_database_tableau.csv"

# ONS region codes to region names
# Source: ONS (2026) Register of Geographic Codes
RGN_NAMES = {
    'E12000001': 'North East',
    'E12000002': 'North West',
    'E12000003': 'Yorkshire and The Humber',
    'E12000004': 'East Midlands',
    'E12000005': 'West Midlands',
    'E12000006': 'East of England',
    'E12000007': 'Greater London',
    'E12000008': 'South East',
    'E12000009': 'South West',
    'W92000004': 'Wales',
    'S92000003': 'Scotland',
    'N92000002': 'Northern Ireland',
}

def run():
    print("=" * 65)
    print("Adding precise lat/lon from ONS Postcode Lookup")
    print("=" * 65)

    # Load firm database
    print(f"\nLoading firm database...")
    df_firms = pd.read_csv(FIRM_PATH, low_memory=False)
    print(f"  {len(df_firms):,} firms")

    # Extract postcodes to look up
    postcodes = df_firms['postcode_best'].dropna().astype(str)
    postcodes = postcodes[postcodes != 'nan'].str.strip().str.upper()
    unique_postcodes = set(postcodes.tolist())
    print(f"  Unique postcodes to look up: {len(unique_postcodes):,}")

    # Read GeoJSON and extract only what we need
    print(f"\nReading postcode lookup (2.7M records — takes ~60 seconds)...")
    lookup = {}

    with open(LOOKUP_PATH, 'r') as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"  Total features in lookup: {len(features):,}")

    matched = 0
    for feature in features:
        props = feature.get('properties', {})
        pcds = str(props.get('pcds', '')).strip().upper()

        if pcds in unique_postcodes:
            lookup[pcds] = {
                'lat_ons':    props.get('lat'),
                'lon_ons':    props.get('long'),
                'rgn25cd':    props.get('rgn25cd', ''),
                'ctry25cd':   props.get('ctry25cd', ''),
            }
            matched += 1

    print(f"  Postcodes matched: {matched:,} / {len(unique_postcodes):,}")

    # Join to firm database
    print(f"\nJoining coordinates to firm database...")

    def get_field(postcode, field, default=None):
        pc = str(postcode).strip().upper() if postcode else ''
        return lookup.get(pc, {}).get(field, default)

    df_firms['latitude']  = df_firms['postcode_best'].apply(
        lambda p: get_field(p, 'lat_ons'))
    df_firms['longitude'] = df_firms['postcode_best'].apply(
        lambda p: get_field(p, 'lon_ons'))
    df_firms['rgn25cd']   = df_firms['postcode_best'].apply(
        lambda p: get_field(p, 'rgn25cd', ''))
    df_firms['ctry25cd']  = df_firms['postcode_best'].apply(
        lambda p: get_field(p, 'ctry25cd', ''))

    # Add region name from ONS code
    df_firms['region_ons'] = df_firms['rgn25cd'].map(RGN_NAMES).fillna(
        df_firms['region'])  # fall back to existing region column

    # Summary
    with_coords = df_firms['latitude'].notna().sum()
    print(f"  Firms with precise coordinates: {with_coords:,} / {len(df_firms):,}")

    print(f"\nBy ONS region:")
    for rgn, name in RGN_NAMES.items():
        count = (df_firms['rgn25cd'] == rgn).sum()
        if count:
            print(f"  {name:<35} {count:>5,}")

    no_region = (df_firms['rgn25cd'] == '').sum()
    print(f"  {'No region assigned':<35} {no_region:>5,}")

    # Save
    df_firms.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved: {OUTPUT_PATH}")
    print(f"\nNew columns added:")
    print(f"  latitude   — precise lat from ONS postcode lookup")
    print(f"  longitude  — precise lon from ONS postcode lookup")
    print(f"  rgn25cd    — ONS region code")
    print(f"  region_ons — ONS region name (use this in Tableau)")
    print(f"\nIn Tableau:")
    print(f"  1. Data menu → firm_database_tableau → Refresh")
    print(f"  2. New sheet → double-click 'Longitude'")
    print(f"  3. Double-click 'Latitude'")
    print(f"  4. Change both to Dimension")
    print(f"  5. Change mark type to Circle")
    print(f"  6. Drag 'Region Ons' to Color")
    print(f"  7. Drag Count to Size")
    print(f"  8. Zoom to UK")
    print("=" * 65)

if __name__ == "__main__":
    run()