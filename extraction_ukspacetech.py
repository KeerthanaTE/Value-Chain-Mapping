"""
UK Space Sector — ukspacetech.com Scraper (Source 2) v2
MSc Business Analytics and Big Data Dissertation
University of Liverpool

Scrapes the UK Space Tech Landscape directory (ukspacetech.com) to extract
127 pre-curated UK space sector firms with category, description, and website.

Source quality:
  ukspacetech.com draws on 18 UK Government and industry sources including
  UK Space Agency, Innovate UK, SCC, Harwell Campus, UKspace, Seraphim Space,
  BryceTech, Know.space, Crunchbase, and PitchBook. Data current as of May 2026.

Why this source adds value over Source 1 (CH Bulk):
  - Pre-curated: 127 verified space firms vs 449,917 SIC-based candidates
  - Pre-categorised: 9 categories map to value-chain nodes N1-N9
  - Descriptions: enable firm-level node assignment at Stage 3
  - N6 coverage: constellation operators and in-orbit firms not captured by SIC
  - Node correction: e.g. Surrey Satellite correctly N3, not N1 (SIC 26110)

Changes from v1:
  - ALL nine categories now flagged review_needed=Yes
  - SatCom Operators: primary node corrected N8→N6 (operators are N6 by definition)
  - In-Space Economy: primary node corrected N6→N3 (firms primarily build spacecraft)
  - Review reasons updated to be firm-specific and precise for every category
  - Specific dual-node and misclassification cases documented per category

Category to node mapping derived from OECD/BEA/ESA/Eurostat/JRC (2023) Table 1:
  Launchers                → N5 primary (N2 secondary for some)
  Satellite Manufacturers  → N3 primary (N6 secondary for operators)
  Components & Subsystems  → N1 primary (N2/N4/N7/N9 secondary — wide split)
  Propulsion               → N2 primary (N5 secondary for European Astrotech)
  SatCom Operators         → N6 primary (N8 secondary — operators before services)
  EO & Geospatial          → N7 primary (N6/N8 secondary — constellation ops and apps)
  In-Space Economy         → N3 primary (N6 secondary — build then operate)
  Ground Segment & SDA     → N4 primary (N6/N9 secondary — infra then services)
  Secure & Quantum Comms   → N2 primary (N8/N9 secondary — hardware then services)

Output:
  data/seed_firms_ukspacetech.csv

References:
  ukspacetech.com (2026) UK Space Tech Landscape 2026.
  https://www.ukspacetech.com/ [Data current as of 26 May 2026]

  OECD/BEA/ESA/Eurostat/JRC (2023) International, North American and
  European Statistical Classifications for Space Economy Measurement.
  doi:10.2785/695530
"""

import requests
import pandas as pd
import re
import os
import urllib3
from datetime import date
from bs4 import BeautifulSoup

urllib3.disable_warnings()

URL        = "https://www.ukspacetech.com/"
OUTPUT_DIR = "/Users/keerthanate/dissertation/data"
DATE_TODAY = str(date.today())

# ── CATEGORY TO NODE MAPPING ───────────────────────────────────────────────
# All nine categories flagged review_needed=Yes.
# Primary node is the most common node for that category.
# Specific dual-node and misclassification cases documented in review_reason.
# Final node assignments confirmed at Stage 3 using firm descriptions
# and company website evidence.
# Source: OECD/BEA/ESA/Eurostat/JRC (2023) Table 1 activity categories.

CATEGORY_MAP = {

    'Launchers': {
        'primary_node':   'N5',
        'node_label':     'Launch',
        'chain_position': 'Upstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Most firms are N5 (launch services) but several span nodes. '
            'Astron Systems: N5 primary, N2 secondary — develops both the '
            'Aurora launch vehicle and its hybrid engines (N2 subsystem). '
            'Skyrora: N5 primary, N2 secondary, N6 tertiary — develops '
            'rockets (N2), provides launch services (N5), and is developing '
            'a space tug for in-orbit operations (N6). '
            'Black Arrow Space Technologies: N5 only at current stage. '
            'Review each firm description to assign secondary nodes.'
        ),
        'oecd_category':  'Space launch activities',
    },

    'Satellite Manufacturers': {
        'primary_node':   'N3',
        'node_label':     'Satellite and Spacecraft Manufacturing',
        'chain_position': 'Upstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Category spans multiple nodes. Confirmed dual-node N3/N6: '
            'Surrey Satellite Technology (builds and operates EO, navigation, '
            'science satellites), In-Space Missions (builds and operates '
            'hosted-payload missions), Alba Orbital (builds PocketQubes and '
            'operates Unicorn-2 and Night Lights), NanoAvionics (bus '
            'manufacturer and mission integrator), Open Cosmos (builds '
            'smallsats and operates OpenConstellation). '
            'Node corrections required: '
            'Blue Skies Space is N6 primary (operates Mauve mission, '
            'delivers data by subscription) with N3 secondary. '
            'Honeywell is N2 (manufactures components and subsystems — not '
            'a full satellite integrator). '
            'L3Harris is N2 primary (RF payloads, comms subsystems) with '
            'N9 secondary (defence advisory). '
            'Lockheed Martin is N4 primary (satellite ground systems, '
            'spaceport support) with N9 secondary. '
            'MDA Space is N2 primary (software-defined payloads, subsystems). '
            'AAC Clyde Space spans N3/N6/N7 — builds satellites, operates '
            'VIREON constellation, delivers Space-Data-as-a-Service. '
            'Defence firms requiring defence_primary check: BAE Systems, '
            'L3Harris, Lockheed Martin, RTX.'
        ),
        'oecd_category':  'Integration and supply of full space systems',
    },

    'Components & Subsystems': {
        'primary_node':   'N1',
        'node_label':     'Components and Materials',
        'chain_position': 'Upstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Category spans N1 (raw components, materials, electronics, '
            'connectors, cables, PCBs) and N2 (functional subsystems — '
            'antennas, RF systems, optical terminals, sensor payloads, '
            'flight software). Additionally several firms are misplaced '
            'in this category and belong elsewhere: '
            'Aerospace Corporation UK → N9 (technical advisory only). '
            'Astro42 → N4 primary/N7 secondary (mission control software '
            'and ML for EO). '
            'Bright Ascension → N4 primary (flight and ground software for '
            'satellite operations). '
            'ESR Technology → N9 (tribology services — ancillary enabling). '
            'Maya HTT → N9 (engineering simulation software). '
            'Opteran → N9 (autonomy software — enabling technology). '
            'Oxford Dynamics → N9 (AI tools — enabling technology). '
            'QinetiQ → N9 primary/N4 secondary (technology services and '
            'PNT/SDA advisory). '
            'Spirent → N9 (test and assurance — enabling). '
            'Telespazio UK → N6 primary/N7 secondary/N9 tertiary (satellite '
            'operations, EO data platforms, consulting). '
            'Review every firm description individually to assign node.'
        ),
        'oecd_category':  'Supply of components and equipment for space systems',
    },

    'Propulsion': {
        'primary_node':   'N2',
        'node_label':     'Subsystems and Payloads',
        'chain_position': 'Upstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Most firms are N2 (propulsion subsystem manufacturers). '
            'One exception: European Astrotech is N2 primary (propulsion, '
            'propellant chemistry) with N5 secondary (launch-site fuelling '
            'services — directly supports launch operations). '
            'Magdrive, ProtoLaunch, Pulsar Fusion, SteamJet: N2 only. '
            'Review European Astrotech to assign N5 as secondary node.'
        ),
        'oecd_category':  'Supply of components and equipment for space systems',
    },

    'SatCom Operators': {
        'primary_node':   'N6',
        'node_label':     'Satellite Operations',
        'chain_position': 'Downstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Primary node corrected from N8 to N6: firms in this category '
            'operate satellite constellations, which by your node definition '
            'is N6 (Satellite Operations), not N8 (Applications and Services). '
            'N8 applies to the end-user service built on those satellites. '
            'Most firms here span N6 (operates satellites) and N8 (provides '
            'comms services to customers): Avanti Communications, Inmarsat, '
            'Lacuna Space, OneWeb, Viasat UK. '
            'AST SpaceMobile is N3 primary (developing and building its '
            'satellite network) with N8 secondary (cellular broadband service). '
            'Two firms are N8 only — they resell services using third-party '
            'satellites and do not operate their own: '
            'SatCom Global (VSAT and airtime distributor), '
            'Wyld Networks UK (satellite IoT connectivity service). '
            'Review each firm description to assign primary and secondary nodes.'
        ),
        'oecd_category':  'Operation of space systems / downstream satcoms',
    },

    'Earth Observation & Geospatial': {
        'primary_node':   'N7',
        'node_label':     'Data Processing and Analytics',
        'chain_position': 'Downstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Category spans three nodes. N7 (data processing, algorithm '
            'development, analytics platforms): ARGANS, Assimila, Earth Blox, '
            'Earth-i, Earthwave, isardSAT, Pixalytics. '
            'N8 (end-user applications built on EO data): Asterra, ChAI, '
            'Climate X, Ecometrica, Gentian, Geospatial Insight, Hummingbird '
            'Technologies, McKenzie Intelligence, Omanos Analytics, '
            'OpenWeather, PlanetWatchers, PowerMarket, Resilience '
            'Constellation, Rezatec, Satsense, Spottitt, Sylvera, Terrabotics. '
            'Additionally four firms operate their own satellite constellations '
            'making them N6 primary with N7 secondary: '
            'ICEYE (operates SAR constellation), '
            'Satellite Vu (operates HotSat thermal EO constellation), '
            'Spire Global (operates LEO constellation for weather/AIS/ADS-B), '
            'Horizon Technologies (operates AMBER constellation for MDA). '
            'Albora Technologies is N8 (geolocation service — end-user). '
            'Review every firm description individually to assign node.'
        ),
        'oecd_category':  'Downstream services for earth observation',
    },

    'In-Space Economy': {
        'primary_node':   'N3',
        'node_label':     'Satellite and Spacecraft Manufacturing',
        'chain_position': 'Upstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Primary node corrected from N6 to N3: firms in this category '
            'primarily manufacture novel spacecraft before operating them. '
            'The manufacture of the spacecraft is the core IP and primary '
            'activity. Operation follows from manufacturing. '
            'Confirmed dual-node N3/N6 (build and operate): '
            'Astroscale (develops ELSA-M servicer, operates debris removal '
            'missions), D-Orbit (builds ION orbital transfer vehicle, '
            'operates last-mile deployment), Space Forge (builds ForgeStar '
            'returnable satellites, provides microgravity-as-a-service), '
            'Frontier Space Technologies (builds in-orbit biotech labs, '
            'operates SpaceLab payloads), Kayser Space (designs and operates '
            'microgravity payloads on ISS). '
            'N3 only: Photocentric (3D printer manufacturer developing '
            'CosmicMaker in-space printing — at development stage only), '
            'Space Solar (developing CASSIOPeiA space-based solar power — '
            'at development stage only). '
            'Node correction: Lúnasa Space → N2 primary (develops RPO '
            'technology — a subsystem/sensor system, not an operator). '
            'Node correction: Gravitilab → N5 primary/N6 secondary (provides '
            'suborbital launch services and microgravity testing platform). '
            'Review each firm description to assign secondary nodes.'
        ),
        'oecd_category':  'Integration and supply of full space systems / '
                          'Operation of space systems',
    },

    'Ground Segment & SDA': {
        'primary_node':   'N4',
        'node_label':     'Ground Segment',
        'chain_position': 'Upstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Category spans N4 (ground infrastructure) and N6/N9 (services). '
            'N4 primary: Goonhilly Earth Station (teleport and ground station '
            'infrastructure — N4 primary, N6 secondary for operational '
            'services), Satellite Mediaport Services (teleport operator — '
            'N4 only), Spaceflux (optical SSA telescope network — N4 primary, '
            'N9 secondary for SDA services), Lumi Space (satellite laser '
            'ranging infrastructure — N4 primary, N9 secondary). '
            'Node corrections required: '
            'Lodestar Space → N2 (develops machine-vision sensors and '
            'edge-compute payloads for SDA — a hardware subsystem, '
            'not a ground station operator). '
            'NORSS (Raytheon) → N9 (SSA and SST services provider — '
            'ancillary enabling service, not ground infrastructure). '
            'Seradata → N9 (SpaceTrak database — market intelligence and '
            'data service, ancillary enabling). '
            'Review each firm description to assign corrected nodes.'
        ),
        'oecd_category':  'Operation of space systems / ground infrastructure',
    },

    'Secure & Quantum Comms': {
        'primary_node':   'N2',
        'node_label':     'Subsystems and Payloads',
        'chain_position': 'Upstream',
        'review_needed':  'Yes',
        'review_reason': (
            'Category spans N2 (hardware), N8 (services), and N9 (enabling). '
            'N2 primary (security hardware manufacturers): '
            'KETS Quantum Security (chip-scale QKD hardware — N2 only), '
            'Quantum Dice (QRNG hardware — N2 primary, N8 secondary for '
            'secure comms service). '
            'Angoka → N2 primary (hardware-rooted security hardware), '
            'N8 secondary (IoT and satellite security services). '
            'Node corrections required: '
            'Nu Quantum → N9 (quantum networking technology for distributed '
            'quantum computing — enabling technology, not space-specific '
            'hardware). Space is one application among many. '
            'Quantinuum → N9 (trapped-ion quantum computing — enabling '
            'technology platform, not space-specific hardware manufacturer). '
            'Review each firm description to assign corrected nodes.'
        ),
        'oecd_category':  'Supply of components and equipment for space systems',
    },

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

# ── FETCH ──────────────────────────────────────────────────────────────────

def fetch_page():
    print(f"Fetching: {URL}")
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; academic-research-bot/1.0)'}
    r = requests.get(URL, headers=headers, timeout=30, verify=False)
    r.raise_for_status()
    print(f"  Status: {r.status_code} — {len(r.text):,} chars received")
    return r.text

# ── PARSE ──────────────────────────────────────────────────────────────────

def parse_firms(html):
    """
    Parse all 127 firms from the ukspacetech.com single-page HTML.
    Structure: <h3> for category headers and firm names,
               <a> for website, <p> for description.
    """
    soup = BeautifulSoup(html, 'html.parser')
    firms = []
    known_cats = set(CATEGORY_MAP.keys())
    current_cat = None

    for h3 in soup.find_all('h3'):
        text = h3.get_text(strip=True)

        if text in known_cats:
            current_cat = text
            continue

        if not current_cat or not text or len(text) < 2:
            continue

        website = ''
        desc    = ''
        for sib in h3.next_siblings:
            if getattr(sib, 'name', None) == 'h3':
                break
            if getattr(sib, 'name', None) == 'a' and not website:
                href = sib.get('href', '').strip()
                if href and not href.startswith('#'):
                    website = href
            if getattr(sib, 'name', None) == 'p' and not desc:
                desc = sib.get_text(strip=True)

        cat = CATEGORY_MAP.get(current_cat, {})

        loc_hint = ''
        loc_match = re.match(r'^([A-Z][a-zA-Z\s\-]+?)[\-\s]based', desc)
        if loc_match:
            loc_hint = loc_match.group(1).strip()

        firms.append({
            'company_name':           text,
            'website':                website,
            'description':            desc,
            'location_hint':          loc_hint,
            'ukspacetech_category':   current_cat,
            'primary_node':           cat.get('primary_node', ''),
            'node_label':             cat.get('node_label', ''),
            'chain_position':         cat.get('chain_position', ''),
            'oecd_activity_category': cat.get('oecd_category', ''),
            'review_needed':          cat.get('review_needed', 'Yes'),
            'review_reason':          cat.get('review_reason', ''),
            'company_number':         '',
            'secondary_node':         '',
            'supply_hierarchy':       '',
            'defence_primary':        '',
            'space_peripheral':       '',
            'source_scc':             '',
            'source_ch':              '',
            'source_esa':             '',
            'source_website':         'Yes',
            'ch_verified':            '',
            'postcode':               '',
            'post_town':              '',
            'county':                 '',
            'notes': (
                'Stage 1 extraction from ukspacetech.com 2026. '
                'CH number and address to be added at Stage 3. '
                'Node assignment indicative — confirm at Stage 3 '
                'using firm description and website evidence.'
            ),
            'data_collection_date':   DATE_TODAY,
            'extraction_source':      'UKSPACETECH',
        })

    return firms

# ── SUMMARY AND SAVE ───────────────────────────────────────────────────────

def run_scraper():
    print("=" * 65)
    print("UK Space Sector — ukspacetech.com Scraper (Source 2) v2")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)
    print(f"\nSource: {URL}")
    print(f"Data current as of: 26 May 2026")
    print(f"Expected: 127 firms across 9 categories\n")

    html  = fetch_page()
    firms = parse_firms(html)

    if not firms:
        print("\nNo firms extracted — HTML structure may have changed.")
        return None

    df = pd.DataFrame(firms)

    print(f"\n{'='*65}")
    print("EXTRACTION SUMMARY")
    print(f"{'='*65}")
    print(f"\nTotal firms extracted: {len(df)}")

    print(f"\nBy category (primary node assignment):")
    for cat in CATEGORY_MAP:
        grp = df[df['ukspacetech_category'] == cat]
        if len(grp) == 0:
            continue
        node = grp['primary_node'].iloc[0]
        print(f"  {cat:<37} {len(grp):>3} firms  → {node}  review=Yes")

    print(f"\nBy chain position:")
    for pos in ['Upstream', 'Downstream']:
        count = len(df[df['chain_position'] == pos])
        print(f"  {pos:<14} {count:>3} firms")

    print(f"\nBy primary node (indicative — all require Stage 3 review):")
    for node in ['N1','N2','N3','N4','N5','N6','N7','N8','N9']:
        count = len(df[df['primary_node'] == node])
        if count > 0:
            label = NODE_LABELS.get(node, '')
            print(f"  {node}  {label:<42} {count:>3} firms")

    locs = len(df[df['location_hint'] != ''])
    print(f"\nFirms with location extracted from description: {locs}/127")
    print(f"All 127 firms flagged review_needed=Yes")
    print(f"\nKey node corrections vs v1:")
    print(f"  SatCom Operators: N8→N6 (operators are N6 by node definition)")
    print(f"  In-Space Economy: N6→N3 (firms primarily build spacecraft)")
    print(f"  All categories: review_needed now Yes (was No for 5 categories)")

    print(f"\nSample — first 15 firms:")
    cols = ['company_name', 'ukspacetech_category',
            'primary_node', 'location_hint']
    print(df[cols].head(15).to_string(index=False))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = f"{OUTPUT_DIR}/seed_firms_ukspacetech.csv"
    df.to_csv(output_path, index=False)

    print(f"\n{'='*65}")
    print("FILE SAVED")
    print(f"{'='*65}")
    print(f"  {output_path}")
    print(f"  {len(df)} firms")
    print(f"\nNEXT STEPS:")
    print(f"  → Source 3: SCC manual validation by taxonomy filter")
    print(f"  → Merge Source 1 + Source 2 + Source 3 into unified seed CSV")
    print(f"  → Stage 3: space_pipeline.py — confirm nodes using firm")
    print(f"    descriptions, websites, and SCC taxonomy tags")
    print("=" * 65)

    return df

if __name__ == "__main__":
    run_scraper()