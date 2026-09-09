"""
UK Space Sector — UKspace Member Directory Scraper (Source 3)
MSc Business Analytics and Big Data Dissertation
University of Liverpool

Scrapes three UKspace membership pages — all publicly accessible,
no login required:
  1. Council Members  — large established firms (~44 firms)
  2. SME Members      — small/medium enterprises (~110 firms)
  3. Start-ups        — early stage companies (~19 firms)

Why UKspace adds value over Sources 1 and 2:
  - Official trade association of the UK space industry
  - Membership verification — joining requires active space sector work
  - Captures firms with no obvious space keywords in their name
    e.g. Teledyne, Filtronic, Spirent, Enersys, Jaltek, TML Precision
  - Covers the full chain from components to applications
  - Publicly citable: UKspace is the official trade body, over 35 years

Source quality:
  UKspace (2026) UKspace Member Directory. Available at:
  https://www.ukspace.org/membership/ [Accessed: July 2026]

Each member page links to an individual profile page which contains
the firm's description and website. The scraper fetches these profiles
for firms not already in Sources 1 or 2.

Output:
  data/seed_firms_ukspace.csv

References:
  UKspace (2026) UKspace Member Directory.
  https://www.ukspace.org/membership/
  OECD/BEA/ESA/Eurostat/JRC (2023) doi:10.2785/695530 — node assignments
"""

import requests
import pandas as pd
import re
import os
import time
import urllib3
from datetime import date
from bs4 import BeautifulSoup

urllib3.disable_warnings()

OUTPUT_DIR = "/Users/keerthanate/dissertation/data"
DATE_TODAY = str(date.today())

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; academic-research-bot/1.0)'
}

# Three membership pages to scrape
PAGES = [
    {
        'url':      'https://www.ukspace.org/membership/ukspace-members/',
        'category': 'Council Member',
        'profile_prefix': '/member/',
    },
    {
        'url':      'https://www.ukspace.org/membership/sme-members/',
        'category': 'SME Member',
        'profile_prefix': '/sme-member/',
    },
    {
        'url':      'https://www.ukspace.org/membership/ukspace-start-ups/',
        'category': 'Start-up Member',
        'profile_prefix': '/start-up-member/',
    },
]

# ── NODE ASSIGNMENT MAP ────────────────────────────────────────────────────
# Derived from member descriptions and OECD/BEA/ESA/Eurostat/JRC (2023)
# Table 1 activity categories.
# These are indicative — confirmed during Stage 3 verification.
# All UKspace members are flagged review_needed=Yes because
# individual profile descriptions are needed for definitive assignment.

# Known node assignments from Council Members page we already reviewed
KNOWN_NODES = {
    'AAC Clyde Space':            ('N3', 'Upstream'),
    'Aerospace UK Ltd':           ('N9', 'Enabling'),
    'AIRBUS':                     ('N3', 'Upstream'),
    'Airbus':                     ('N3', 'Upstream'),
    'Alden Legal':                ('N9', 'Enabling'),
    'Astroscale':                 ('N3', 'Upstream'),
    'Babcock':                    ('N9', 'Enabling'),
    'BAE Systems':                ('N3', 'Upstream'),
    'BT':                         ('N8', 'Downstream'),
    'ClearSpace':                 ('N3', 'Upstream'),
    'Craft Prospect':             ('N9', 'Enabling'),
    'CRITICAL Software':          ('N9', 'Enabling'),
    'D-Orbit':                    ('N3', 'Upstream'),
    'Deimos Space UK Ltd':        ('N9', 'Enabling'),
    'Enersys':                    ('N1', 'Upstream'),
    'Eutelsat OneWeb':            ('N6', 'Downstream'),
    'Filtronic':                  ('N2', 'Upstream'),
    'Frazer Nash Consultancy':    ('N9', 'Enabling'),
    'GMV-NSL':                    ('N9', 'Enabling'),
    'Goonhilly':                  ('N4', 'Upstream'),
    'Honeywell':                  ('N2', 'Upstream'),
    'ICEYE Information Solutions UK Ltd': ('N6', 'Downstream'),
    'Lockheed Martin UK':         ('N4', 'Upstream'),
    'Lockton':                    ('N9', 'Enabling'),
    'Mace Consult':               ('N9', 'Enabling'),
    'MDA Space':                  ('N2', 'Upstream'),
    'Northrop Grumman':           ('N3', 'Upstream'),
    'NPL (National Physical Laboratory)': ('N9', 'Enabling'),
    'OHB Space UK':               ('N3', 'Upstream'),
    'PA Consulting':              ('N9', 'Enabling'),
    'Raytheon':                   ('N3', 'Upstream'),
    'Satellite Applications Catapult': ('N9', 'Enabling'),
    'Space Forge':                ('N3', 'Upstream'),
    'Spire':                      ('N6', 'Downstream'),
    'Spirent Communications plc': ('N9', 'Enabling'),
    'Starion UK':                 ('N3', 'Upstream'),
    'Surrey Satellite Technology Ltd (SSTL)': ('N3', 'Upstream'),
    'Teledyne':                   ('N1', 'Upstream'),
    'Telespazio UK':              ('N6', 'Downstream'),
    'Thales':                     ('N2', 'Upstream'),
    'Thales Alenia Space':        ('N3', 'Upstream'),
    'Viasat UK':                  ('N6', 'Downstream'),
    # SME known nodes
    'Albora Technologies':        ('N8', 'Downstream'),
    'Archangel Lightworks':       ('N4', 'Upstream'),
    'Assimila':                   ('N7', 'Downstream'),
    'Astro42':                    ('N4', 'Upstream'),
    'Bright Ascension':           ('N4', 'Upstream'),
    'Earth-i':                    ('N7', 'Downstream'),
    'ESR Technology':             ('N9', 'Enabling'),
    'Exobotics':                  ('N3', 'Upstream'),
    'Geospatial Insight':         ('N8', 'Downstream'),
    'Horizon Technologies':       ('N3', 'Upstream'),
    'Kayser Space':               ('N3', 'Upstream'),
    'Lacuna Space':               ('N6', 'Downstream'),
    'Lodestar Space':             ('N2', 'Upstream'),
    'Lunasa Space':               ('N2', 'Upstream'),
    'Magdrive':                   ('N2', 'Upstream'),
    'Open Cosmos':                ('N3', 'Upstream'),
    'Oxford Space Systems':       ('N2', 'Upstream'),
    'Satellite Finance Network':  ('N9', 'Enabling'),
    'Satellite Vu':               ('N6', 'Downstream'),
    'SaxaVord Spaceport':         ('N5', 'Upstream'),
    'Skyrora':                    ('N5', 'Upstream'),
    'Space Solar':                ('N3', 'Upstream'),
    'Spaceflux':                  ('N4', 'Upstream'),
    'Theta Systems':              ('N2', 'Upstream'),
}

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

# ── SCRAPER ────────────────────────────────────────────────────────────────

def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def parse_member_list(html, category, profile_prefix):
    """
    Parse a UKspace membership page.
    Extracts firm names and profile URLs from logo links.
    Structure: <a href="/member/firm-name/"><img alt="Firm Name logo"></a>
    """
    soup  = BeautifulSoup(html, 'html.parser')
    firms = []
    seen  = set()

    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        # Match profile links e.g. /member/astroscale/
        if profile_prefix in href and href != profile_prefix:
            # Extract firm name from img alt text
            img = a.find('img')
            if img:
                alt = img.get('alt', '').strip()
                # Clean up alt text — remove "logo", trailing numbers etc.
                name = re.sub(
                    r'\s*(logo|Logo|LOGO)\s*.*$', '', alt
                ).strip()
                name = re.sub(r'\s+\d+\s*$', '', name).strip()

                if name and name not in seen and len(name) > 2:
                    seen.add(name)
                    firms.append({
                        'name':         name,
                        'profile_url':  'https://www.ukspace.org' + href
                                        if href.startswith('/') else href,
                        'category':     category,
                    })

    return firms


def fetch_profile(profile_url):
    """
    Fetch individual member profile page to get description and website.
    Rate limited to be polite — 0.5s between requests.
    """
    html = fetch_page(profile_url)
    if not html:
        return '', ''
    soup = BeautifulSoup(html, 'html.parser')

    # Description — first substantial paragraph after the header
    desc = ''
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if len(text) > 50 and 'member' not in text.lower()[:20]:
            desc = text[:300]
            break

    # Website — look for "Visit Website" link or external link
    website = ''
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        text = a.get_text(strip=True).lower()
        if ('visit website' in text or 'website' in text) and \
           href.startswith('http') and 'ukspace.org' not in href:
            website = href
            break

    return desc, website


def scrape_all():
    """Scrape all three UKspace membership pages."""

    print("=" * 65)
    print("UKspace Member Directory Scraper (Source 3)")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)
    print(f"\nScraping 3 membership pages:")
    print(f"  1. Council Members  — {PAGES[0]['url']}")
    print(f"  2. SME Members      — {PAGES[1]['url']}")
    print(f"  3. Start-ups        — {PAGES[2]['url']}")
    print(f"\nAll pages are publicly accessible — no login required.")

    all_firms = []

    for page in PAGES:
        print(f"\nFetching {page['category']} page...")
        html = fetch_page(page['url'])
        if not html:
            print(f"  Failed to fetch {page['url']}")
            continue

        firms = parse_member_list(html, page['category'],
                                   page['profile_prefix'])
        print(f"  Found {len(firms)} members")

        # Fetch individual profiles for description and website
        print(f"  Fetching profiles...")
        for i, firm in enumerate(firms):
            desc, website = fetch_profile(firm['profile_url'])
            firm['description'] = desc
            firm['website']     = website
            if (i + 1) % 10 == 0:
                print(f"    {i+1}/{len(firms)} profiles fetched...")
            time.sleep(0.5)

        all_firms.extend(firms)
        print(f"  Complete: {len(firms)} firms with descriptions")

    print(f"\nTotal firms extracted: {len(all_firms)}")

    return all_firms


def build_output(all_firms):
    """Build output CSV in common pipeline template format."""

    records = []
    for firm in all_firms:
        name     = firm['name']
        category = firm['category']

        # Look up known node assignment
        node_info = KNOWN_NODES.get(name)
        if node_info:
            node, chain = node_info
            review = 'Yes'
            review_reason = (
                'Node pre-assigned from earlier review — '
                'confirm at Stage 3 using profile description.'
            )
        else:
            node, chain = '', ''
            review = 'Yes'
            review_reason = (
                'Node not pre-assigned — assign at Stage 3 '
                'using UKspace profile description and website.'
            )

        records.append({
            'company_name':           name,
            'website':                firm.get('website', ''),
            'description':            firm.get('description', ''),
            'ukspace_category':       category,
            'ukspace_profile_url':    firm.get('profile_url', ''),
            'primary_node':           node,
            'node_label':             NODE_LABELS.get(node, ''),
            'chain_position':         chain,
            'oecd_activity_category': '',
            'review_needed':          review,
            'review_reason':          review_reason,
            'company_number':         '',
            'secondary_node':         '',
            'supply_hierarchy':       '',
            'defence_primary':        '',
            'space_peripheral':       '',
            'source_scc':             '',
            'source_ch':              '',
            'source_uksd':            '',
            'source_esa':             '',
            'source_website':         'Yes' if firm.get('website') else '',
            'ch_verified':            '',
            'postcode':               '',
            'post_town':              '',
            'county':                 '',
            'notes': (
                f'Source 3 extraction from UKspace {category} directory. '
                f'UKspace is the official UK space industry trade association. '
                f'CH number and address to be added at Stage 3.'
            ),
            'data_collection_date':   DATE_TODAY,
            'extraction_source':      'UKSPACE',
        })

    return pd.DataFrame(records)


def run():
    all_firms = scrape_all()

    if not all_firms:
        print("\nNo firms extracted — check network and retry.")
        return

    df = build_output(all_firms)

    # Summary
    print(f"\n{'='*65}")
    print("EXTRACTION SUMMARY")
    print(f"{'='*65}")
    print(f"\nTotal firms: {len(df)}")

    print(f"\nBy membership category:")
    for cat, grp in df.groupby('ukspace_category'):
        print(f"  {cat:<25} {len(grp):>3} firms")

    pre_assigned = len(df[df['primary_node'] != ''])
    print(f"\nWith pre-assigned node: {pre_assigned}")
    print(f"Needing Stage 3 assignment: {len(df) - pre_assigned}")

    print(f"\nBy primary node (pre-assigned):")
    for node in ['N1','N2','N3','N4','N5','N6','N7','N8','N9']:
        count = len(df[df['primary_node'] == node])
        if count > 0:
            print(f"  {node}  {NODE_LABELS.get(node,''):<42} {count:>3}")

    print(f"\nFirms with website extracted: "
          f"{len(df[df['website'] != ''])}")
    print(f"Firms with description extracted: "
          f"{len(df[df['description'] != ''])}")

    # Save
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = f"{OUTPUT_DIR}/seed_firms_ukspace.csv"
    df.to_csv(output_path, index=False)

    print(f"\n{'='*65}")
    print("FILE SAVED")
    print(f"{'='*65}")
    print(f"  {output_path}")
    print(f"  {len(df)} firms")
    print(f"\nKey columns:")
    print(f"  company_name        — firm name from UKspace directory")
    print(f"  ukspace_category    — Council Member / SME Member / Start-up")
    print(f"  ukspace_profile_url — link to UKspace member profile")
    print(f"  description         — extracted from profile page")
    print(f"  website             — company website where found")
    print(f"  primary_node        — pre-assigned where known")
    print(f"\nNEXT STEPS:")
    print(f"  → Merge with Sources 1 and 2 using merge_sources.py")
    print(f"    (update merge script to include seed_firms_ukspace.csv)")
    print(f"  → Run Stage 3 pipeline on merged output")
    print("=" * 65)


if __name__ == "__main__":
    run()