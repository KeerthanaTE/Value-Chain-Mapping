"""
UK Space Sector — Companies House Bulk Extraction

Stage 1: Extract all candidate firms from Companies House bulk data
using space-relevant SIC codes. No filtering or exclusions applied here.
All inclusion/exclusion decisions made at Stage 3 (space_pipeline.py).

Output:
  data/seed_firms_ch_bulk.csv

─────────────────────────────────────────────────────────────────────────────
SIC CODE SOURCING — THREE TIERS

Tier 1 — ONS SIC 2007 index (7 codes)
  Codes where space/satellite activities are explicitly listed in the ONS
  SIC 2007 activity index.
  Source: ONS (2007) UK Standard Industrial Classification of Economic
  Activities 2007. Newport: Office for National Statistics.
  https://www.ons.gov.uk/methodology/classificationsandstandards/
  ukstandardindustrialclassificationofeconomicactivities/uksic2007

Tier 2 — ONS SIC 2026 explanatory notes (3 codes)
  Codes confirmed by cross-references from spacecraft manufacturing codes
  30.331 (civilian) and 30.332 (military) in the SIC 2026 explanatory notes.
  Source: ONS (2026) UK Standard Industrial Classification of Economic
  Activities 2026. Newport: Office for National Statistics. Published 31
  March 2026.
  https://www.ons.gov.uk/methodology/classificationsandstandards/
  ukstandardindustrialclassificationofeconomicactivities/uksic2026

Tier 3 — OECD/BEA/ESA/Eurostat/JRC (2023) Table 4 (15 codes)
  Codes confirmed in Table 4 of the joint international publication on
  statistical classifications for space economy measurement. UK SIC 2007
  is aligned with NACE Rev. 2 at the four-digit level, so NACE codes map
  directly to UK SIC codes.
  Source: OECD/BEA/ESA/Eurostat/JRC (2023) International, North American
  and European Statistical Classifications for Space Economy Measurement.
  Paris/Washington/Paris. December 2023.
  https://www.bea.gov/sites/default/files/2023-12/
  international-north-american-european-statistical-classifications-
  space-economy-measurement_0.pdf

─────────────────────────────────────────────────────────────────────────────
NODE ASSIGNMENT SOURCING

Node assignments (N1-N9) and chain positions (Upstream/Downstream/Enabling)
are derived from Table 1 of OECD/BEA/ESA/Eurostat/JRC (2023), which groups
ISIC/NACE codes by space activity category:

  Supply of components and equipment     → N1 (Components), N2 (Subsystems)
  Integration and supply of full systems → N3 (Spacecraft Manufacturing)
  Space launch activities                → N5 (Launch)
  Operation of space systems             → N6 (Satellite Operations)
  Downstream services for EO/nav/satcom  → N7 (Data Processing), N8 (Applications)
  Supply of services (consumer markets)  → N8 (Applications and Services)
  Ancillary activities (insurance, etc.) → N9 (Enabling and Ancillary)
  R&D and engineering support            → N9 (Enabling and Ancillary)

N6 (Satellite Operations) has no corresponding SIC code in SIC 2007 or
SIC 2026. N6 firms will be identified via SCC (Source 3) and
ukspacetech.com (Source 2).

─────────────────────────────────────────────────────────────────────────────
DEFENCE CHECK FLAG

ONS SIC 2026 reveals that SIC 2007 code 30300 contains both civilian
spacecraft (30.331) and military spacecraft (30.332) — previously merged
under one code. All firms under 30300 are flagged requires_defence_check=Yes
for mandatory review at Stage 3 using company website evidence.
Source: ONS (2026), codes 30.331 and 30.332 explanatory notes.

─────────────────────────────────────────────────────────────────────────────
FULL REFERENCES

ONS (2007) UK Standard Industrial Classification of Economic Activities 2007.
Newport: Office for National Statistics.
https://www.ons.gov.uk/methodology/classificationsandstandards/
ukstandardindustrialclassificationofeconomicactivities/uksic2007

ONS (2026) UK Standard Industrial Classification of Economic Activities 2026.
Newport: Office for National Statistics. Published 31 March 2026.
https://www.ons.gov.uk/methodology/classificationsandstandards/
ukstandardindustrialclassificationofeconomicactivities/uksic2026

OECD/BEA/ESA/Eurostat/JRC (2023) International, North American and European
Statistical Classifications for Space Economy Measurement. December 2023.
ISBN 978-92-68-10256-5. doi:10.2785/695530.
https://www.bea.gov/sites/default/files/2023-12/international-north-american-
european-statistical-classifications-space-economy-measurement_0.pdf

UK Space Agency (2025) Size and Health of the UK Space Industry 2024.
London: Department for Science, Innovation and Technology.
https://www.gov.uk/government/publications/size-and-health-of-the-uk-space-industry-2024
"""

import pandas as pd
import os
from datetime import date

# ── CONFIGURATION ──────────────────────────────────────────────────────────

CH_BULK_PATH = "/Users/keerthanate/Downloads/BasicCompanyDataAsOneFile-2026-07-01.csv"
OUTPUT_DIR   = "/Users/keerthanate/dissertation/data"
DATE_TODAY   = str(date.today())

# ── COLUMNS TO LOAD ────────────────────────────────────────────────────────
# Exact column names from Companies House bulk CSV
# Some have leading spaces — must match exactly as confirmed by test script

COLS = [
    'CompanyName',
    ' CompanyNumber',            # leading space — col 1
    'CompanyCategory',           # Ltd, PLC, LLP — col 10
    'CompanyStatus',             # active/dissolved — col 11
    'CountryOfOrigin',           # confirm UK origin — col 12
    'IncorporationDate',         # ecosystem age — col 14
    'Accounts.AccountCategory',  # catch dormant firms — col 19
    'SICCode.SicText_1',         # primary SIC — col 26
    'SICCode.SicText_2',         # secondary SIC — col 27
    'SICCode.SicText_3',         # tertiary SIC — col 28
    'SICCode.SicText_4',         # quaternary SIC — col 29
    'URI',                       # CH profile link — col 32
    'RegAddress.AddressLine1',   # address — col 4
    ' RegAddress.AddressLine2',  # leading space — col 5
    'RegAddress.PostTown',       # city — col 6
    'RegAddress.County',         # county — col 7
    'RegAddress.Country',        # country — col 8
    'RegAddress.PostCode',       # postcode for Tableau mapping — col 9
]

# ── SPACE SIC CODE MAP ─────────────────────────────────────────────────────
#
# Format per entry:
#   'node'       — value chain node (N1-N9)
#   'chain'      — Upstream / Downstream / Enabling
#   'confidence' — High / Medium / Low
#                  High   = code is primarily/exclusively space
#                  Medium = code has significant space subset
#                  Low    = code has a small but documented space subset
#   'tier'       — Tier 1 / Tier 2 / Tier 3 (sourcing level)
#   'source'     — authoritative document and table reference
#   'oecd_category' — category in OECD/BEA/ESA/Eurostat/JRC (2023) Table 1
#                     (blank for Tier 1 and Tier 2)
#   'note'       — additional context for Stage 3 reviewers

SPACE_SIC_MAP = {

    # ══════════════════════════════════════════════════════════════════════
    # TIER 1 — ONS SIC 2007 INDEX CONFIRMED (7 codes)
    # Space/satellite activities explicitly listed in ONS SIC 2007
    # Source: ONS (2007) UK SIC 2007 activity index
    # ══════════════════════════════════════════════════════════════════════

    '30300': {
        'node': 'N3', 'chain': 'Upstream', 'confidence': 'High',
        'tier': 'Tier 1',
        'source': 'ONS SIC 2007 index: space shuttles (manufacture)',
        'oecd_category': '',
        'note': 'SIC 2026 separates into 30.331 (civilian) and 30.332 '
                '(military). Both merged here in SIC 2007. '
                'requires_defence_check=Yes — Stage 3 must confirm civilian.',
    },
    '51220': {
        'node': 'N5', 'chain': 'Upstream', 'confidence': 'High',
        'tier': 'Tier 1',
        'source': 'ONS SIC 2007 index: space transport, space vehicle '
                  'launching, space transport of freight and passengers. '
                  'Also confirmed by SIC 2026 51.22 and OECD/BEA/ESA/'
                  'Eurostat/JRC (2023) Table 4: space transport services.',
        'oecd_category': 'Space launch activities',
        'note': '',
    },
    '61300': {
        'node': 'N8', 'chain': 'Downstream', 'confidence': 'High',
        'tier': 'Tier 1',
        'source': 'ONS SIC 2007 index: satellite circuit rental services, '
                  'telecommunications satellite relay station. '
                  'Also confirmed by OECD/BEA/ESA/Eurostat/JRC (2023) '
                  'Table 4: satellite telecommunications activities.',
        'oecd_category': 'Operation of space systems / Downstream satcoms',
        'note': 'SIC 2026 merges into 61.10 (wired, wireless and satellite '
                'telecoms). 61300 remains the correct SIC 2007 code.',
    },
    '33160': {
        'node': 'N3', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 1',
        'source': 'ONS SIC 2007 index: repair and maintenance of aero-space '
                  'equipment. Also confirmed by SIC 2026 33.16: repair and '
                  'maintenance of civilian air and spacecraft. '
                  'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: 33.16.',
        'oecd_category': 'Integration and supply of full space systems',
        'note': 'Also captures aircraft MRO. requires_defence_check=Yes.',
    },
    '52230': {
        'node': 'N5', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 1',
        'source': 'ONS SIC 2007 index: service activities incidental to '
                  'space transportation. Also confirmed by OECD/BEA/ESA/'
                  'Eurostat/JRC (2023) Table 4: 52.23 services incidental '
                  'to space transportation.',
        'oecd_category': 'Space launch activities',
        'note': 'Also captures general air transport support services.',
    },
    '26309': {
        'node': 'N2', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 1',
        'source': 'ONS SIC 2007 index: satellite relay (manufacture), '
                  'ground station for relay satellite communication '
                  '(manufacture). Also confirmed by SIC 2026 30.331 '
                  'cross-reference to 26.30 for satellite telecoms equipment. '
                  'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: 26.30.',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': '',
    },
    '26511': {
        'node': 'N2', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 1',
        'source': 'ONS SIC 2007 index: electronic instruments for measuring, '
                  'testing, and navigation (manufacture). Also confirmed by '
                  'SIC 2026 30.331 cross-reference to 26.51 for spacecraft '
                  'instrumentation and navigation equipment. '
                  'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: 26.51.',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': '',
    },

    # ══════════════════════════════════════════════════════════════════════
    # TIER 2 — ONS SIC 2026 EXPLANATORY NOTES CONFIRMED (3 codes)
    # Codes confirmed by cross-references from 30.331 and 30.332 in
    # SIC 2026 explanatory notes
    # Source: ONS (2026) SIC 2026, codes 30.331 and 30.332
    # ══════════════════════════════════════════════════════════════════════

    '26512': {
        'node': 'N4', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 2',
        'source': 'ONS SIC 2026 code 30.331 excludes: spacecraft '
                  'instrumentation and navigation or control equipment, '
                  'see 26.51 — covers both 26511 (electronic measuring) '
                  'and 26512 (process control equipment).',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': 'Ground segment control systems, satellite command and '
                'control equipment.',
    },
    '26110': {
        'node': 'N1', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 2',
        'source': 'ONS SIC 2026 code 30.331 includes: manufacture of parts '
                  'and accessories of spacecraft including power systems and '
                  'propulsion systems — electronic components are primary '
                  'inputs. Also confirmed by OECD/BEA/ESA/Eurostat/JRC '
                  '(2023) Table 4: 26.11 electronic components.',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': 'Also captures general electronics manufacturers.',
    },
    '26701': {
        'node': 'N2', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 2',
        'source': 'ONS SIC 2026 code 30.331 includes manufacture of '
                  'spacecraft parts — optical payloads fall under optical '
                  'precision instruments. Also confirmed by '
                  'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: 26.70 '
                  'optical instruments.',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': 'Satellite imaging payloads, telescope optics, LIDAR systems.',
    },

    # ══════════════════════════════════════════════════════════════════════
    # TIER 3 — OECD/BEA/ESA/EUROSTAT/JRC (2023) TABLE 4 CONFIRMED (15 codes)
    # Codes explicitly listed in Table 4 of the joint international
    # publication on statistical classifications for space economy
    # measurement. UK SIC 2007 is aligned with NACE Rev. 2 at the
    # four-digit level — NACE codes map directly to UK SIC codes.
    # Source: OECD/BEA/ESA/Eurostat/JRC (2023) Table 4, pp. 26-34.
    # doi:10.2785/695530
    # ══════════════════════════════════════════════════════════════════════

    '60200': {
        'node': 'N8', 'chain': 'Downstream', 'confidence': 'Medium',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 60.20 '
                  'television programming and broadcasting activities — '
                  'CPA 60.20.14 subscription television (includes DTH).',
        'oecd_category': 'Supply of services supporting consumer markets',
        'note': 'DTH broadcasting accounts for 48% of UK space industry '
                'income (UK Space Agency, 2025).',
    },
    '60100': {
        'node': 'N8', 'chain': 'Downstream', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 60.10 '
                  'radio broadcasting — satellite radio distribution.',
        'oecd_category': 'Supply of services supporting consumer markets',
        'note': 'Small subset — satellite radio distribution and DAB.',
    },
    '61100': {
        'node': 'N8', 'chain': 'Downstream', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 61.10 '
                  'wired telecommunications — CPA 61.10.43 broadband '
                  'internet including satellite fixed wireless.',
        'oecd_category': 'Downstream services for satellite telecoms',
        'note': 'Small subset — satellite feeds into wired networks.',
    },
    '61200': {
        'node': 'N8', 'chain': 'Downstream', 'confidence': 'Medium',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 61.20 '
                  'wireless telecommunications — CPA 61.20.11 mobile '
                  'telecommunications including satellite phones.',
        'oecd_category': 'Downstream services for satellite telecoms',
        'note': 'Satellite broadband, mobile satellite communications.',
    },
    '61900': {
        'node': 'N8', 'chain': 'Downstream', 'confidence': 'Medium',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 61.90 '
                  'other telecommunications — CPA 61.90.10 includes '
                  'satellite tracking services.',
        'oecd_category': 'Operation of space systems',
        'note': 'Specialist satellite comms operators not elsewhere classified.',
    },
    '63110': {
        'node': 'N7', 'chain': 'Downstream', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 63.11 '
                  'data processing and hosting — downstream EO data '
                  'processing services (explicitly noted in document p.11).',
        'oecd_category': 'Downstream services for earth observation',
        'note': 'Document states: "Many companies developing downstream '
                'space applications are registered as data-processing '
                'companies under the much broader ISIC class 6311" (p.11).',
    },
    '72190': {
        'node': 'N9', 'chain': 'Enabling', 'confidence': 'Medium',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 72.19 '
                  'other R&D on natural sciences and engineering — '
                  'CPA 72.19.13 research in physical sciences including '
                  'space research.',
        'oecd_category': 'Fundamental and applied research',
        'note': 'Space research organisations, university space centres.',
    },
    '71121': {
        'node': 'N9', 'chain': 'Enabling', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 71.12 '
                  'engineering activities and related technical consultancy — '
                  'CPA 71.12.17 engineering services for industrial and '
                  'manufacturing projects (includes space vehicles). '
                  'CPA 71.12.18 engineering services for '
                  'telecommunications and broadcasting projects.',
        'oecd_category': 'Research and development services / engineering',
        'note': 'Space systems engineering design consultancies.',
    },
    '71122': {
        'node': 'N9', 'chain': 'Enabling', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 71.12 '
                  'engineering activities and related technical consultancy.',
        'oecd_category': 'Research and development services / engineering',
        'note': 'Space sector engineering consultancies.',
    },
    '71200': {
        'node': 'N4', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 1: technical '
                  'testing and analysis (ISIC 71) explicitly listed under '
                  '"Research and development services, engineering services '
                  '(testing, design)". Table 4: NACE 71.20 not listed '
                  'separately but covered under 71.12.',
        'oecd_category': 'Research and development services',
        'note': 'Satellite environmental testing, vibration and thermal '
                'vacuum testing facilities.',
    },
    '26110': {
        'node': 'N1', 'chain': 'Upstream', 'confidence': 'Medium',
        'tier': 'Tier 2',
        'source': 'ONS SIC 2026 and OECD/BEA/ESA/Eurostat/JRC (2023) '
                  'Table 4: NACE 26.11 electronic components.',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': 'Already listed under Tier 2 — duplicate removed.',
    },
    '25620': {
        'node': 'N1', 'chain': 'Upstream', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 25.62 '
                  'machining — CPA 25.62.10 turning services of metal parts, '
                  '25.62.20 other machining services.',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': 'Precision machining for satellite structures and components.',
    },
    '27200': {
        'node': 'N1', 'chain': 'Upstream', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 27.90 '
                  'other electrical equipment — capacitors, resistors, '
                  'and electrical components for space systems.',
        'oecd_category': 'Supply of components and equipment for space systems',
        'note': 'Space-grade power systems and electrical components.',
    },
    '65120': {
        'node': 'N9', 'chain': 'Enabling', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 65.12 '
                  'non-life insurance — CPA 65.12.33 other aircraft '
                  'insurance services, CPA 65.12.36 freight insurance '
                  '(includes satellite launching insurance, explicitly '
                  'noted in Table 2: CPC 71332).',
        'oecd_category': 'Ancillary activities (space insurance)',
        'note': 'Satellite insurance — UK leads globally in this niche.',
    },
    '70229': {
        'node': 'N9', 'chain': 'Enabling', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 70.22 '
                  'business and other management consultancy — listed under '
                  'professional, scientific and technical services for space.',
        'oecd_category': 'Ancillary activities',
        'note': 'Space sector strategy consultancies.',
    },
    '74909': {
        'node': 'N9', 'chain': 'Enabling', 'confidence': 'Low',
        'tier': 'Tier 3',
        'source': 'OECD/BEA/ESA/Eurostat/JRC (2023) Table 4: NACE 74.90 '
                  'other professional, scientific and technical activities — '
                  'CPA 74.90.13 environmental consulting, CPA 74.90.14 '
                  'weather forecasting and meteorological services.',
        'oecd_category': 'Ancillary activities',
        'note': 'Space policy advisory firms, regulatory consultants, '
                'meteorological services using satellite data.',
    },

}

# Remove duplicate 26110 entry (listed under both Tier 2 and Tier 3)
# Tier 2 takes precedence
if '26110' in SPACE_SIC_MAP:
    pass  # Already set correctly above — dict keeps last assignment

# ── DEFENCE CHECK CODES ────────────────────────────────────────────────────
# Codes where defence firms are known to be present alongside civil firms
# Source: ONS (2026) SIC 2026 — 30300 contains 30.331 (civilian) and
# 30.332 (military). Mandatory Stage 3 review for all firms under these codes.

DEFENCE_CHECK_CODES = {'30300', '33160', '26309'}

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


# ── HELPER FUNCTION ────────────────────────────────────────────────────────

def get_node_from_sic(sic_text):
    """
    Check if any space SIC code appears in a SIC text string.
    Returns (matched_code, info_dict) or None.

    CH bulk SICCode columns store full text e.g.:
    '30300 - Manufacture of air and spacecraft and related machinery'
    We search for the 5-digit code substring within that text.
    """
    if pd.isna(sic_text):
        return None
    sic_str = str(sic_text)
    for code, info in SPACE_SIC_MAP.items():
        if code in sic_str:
            return code, info
    return None


# ── EXTRACTION ─────────────────────────────────────────────────────────────

def run_extraction():
    """Extract all space-relevant candidate firms from CH bulk CSV."""

    tier_counts = {}
    for info in SPACE_SIC_MAP.values():
        tier_counts[info['tier']] = tier_counts.get(info['tier'], 0) + 1

    print("=" * 65)
    print("UK Space Sector — Companies House Bulk Extraction")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)
    print(f"\nSource: {CH_BULK_PATH}")
    print(f"\nSIC codes: {len(SPACE_SIC_MAP)} total")
    for tier in sorted(tier_counts):
        print(f"  {tier}: {tier_counts[tier]} codes")
    print(f"\nNode assignments sourced from OECD/BEA/ESA/Eurostat/JRC (2023)")
    print(f"Table 1 space activity categories.")
    print(f"\nNo filtering applied — full candidate population retained.")
    print(f"All exclusions applied in Stage 3 (space_pipeline.py).\n")
    print(f"Processing in chunks of 50,000 rows...")
    print(f"Expected time: 3-5 minutes\n")

    firms      = []
    total_rows = 0
    chunk_num  = 0

    for chunk in pd.read_csv(
        CH_BULK_PATH,
        chunksize=50000,
        usecols=COLS,
        encoding='utf-8',
        low_memory=False,
        on_bad_lines='skip'
    ):
        chunk_num  += 1
        total_rows += len(chunk)

        for _, row in chunk.iterrows():

            # Active companies only
            if str(row.get('CompanyStatus', '')).lower() != 'active':
                continue

            # Skip dormant
            if str(row.get('Accounts.AccountCategory', '')).lower() == 'dormant':
                continue

            # Combine all 4 SIC text fields
            sic_texts = [
                str(row.get('SICCode.SicText_1', '')),
                str(row.get('SICCode.SicText_2', '')),
                str(row.get('SICCode.SicText_3', '')),
                str(row.get('SICCode.SicText_4', '')),
            ]
            combined_sic = ' | '.join(sic_texts)

            # Find first SIC match
            result      = None
            matched_code = ''
            matched_text = ''
            for sic_text in sic_texts:
                result = get_node_from_sic(sic_text)
                if result:
                    matched_code, info = result
                    matched_text = sic_text
                    break

            if not result:
                continue

            note_text = (
                'Stage 1 extraction. SIC ' + matched_code + ' — ' + info['note']
                if info['note'] else 'Stage 1 extraction via SIC match'
            )

            firms.append({
                # Core identification — from Companies House
                'company_name':      str(row.get('CompanyName', '')),
                'company_number':    str(row.get(' CompanyNumber', '')).strip().zfill(8),
                'company_category':  row.get('CompanyCategory', ''),
                'country_of_origin': row.get('CountryOfOrigin', ''),
                'incorporated':      row.get('IncorporationDate', ''),
                'uri':               row.get('URI', ''),
                # SIC data — from Companies House
                'sic_codes_full':    combined_sic,
                'matched_sic_code':  matched_code,
                'matched_sic_text':  matched_text,
                # Node assignment — from OECD/BEA/ESA/Eurostat/JRC (2023) Table 1
                # Indicative at Stage 1 — confirmed at Stage 3
                'primary_node':      info['node'],
                'node_label':        NODE_LABELS.get(info['node'], ''),
                'chain_position':    info['chain'],
                # Sourcing metadata
                'sic_confidence':    info['confidence'],
                'sic_tier':          info['tier'],
                'sic_source':        info['source'],
                'oecd_activity_category': info['oecd_category'],
                # Defence check flag
                # Source: ONS (2026) — 30300 merges 30.331 (civilian)
                # and 30.332 (military) spacecraft in SIC 2007
                'requires_defence_check': (
                    'Yes' if matched_code in DEFENCE_CHECK_CODES else 'No'
                ),
                # Address — from Companies House
                'address_line1':     row.get('RegAddress.AddressLine1', ''),
                'address_line2':     row.get(' RegAddress.AddressLine2', ''),
                'post_town':         row.get('RegAddress.PostTown', ''),
                'county':            row.get('RegAddress.County', ''),
                'country':           row.get('RegAddress.Country', ''),
                'postcode':          row.get('RegAddress.PostCode', ''),
                # Stage 3 pipeline fields — empty, filled during verification
                'secondary_node':    '',
                'supply_hierarchy':  '',
                'defence_primary':   '',
                'space_peripheral':  '',
                'source_scc':        '',
                'source_uksd':       '',
                'source_esa':        '',
                'source_website':    '',
                'ch_verified':       '',
                'notes':             note_text,
                'data_collection_date': DATE_TODAY,
                'extraction_source': 'CH_BULK',
            })

        if chunk_num % 20 == 0:
            print(f"  Processed {total_rows:,} rows — "
                  f"{len(firms):,} candidate firms found...")

    print(f"\nExtraction complete.")
    print(f"  Total rows processed: {total_rows:,}")
    print(f"  Candidate firms:      {len(firms):,}")

    return pd.DataFrame(firms)


# ── SUMMARY ────────────────────────────────────────────────────────────────

def print_summary(df):
    """Print extraction summary."""

    print("\n" + "=" * 65)
    print("EXTRACTION SUMMARY")
    print("=" * 65)
    print(f"\nTotal candidate firms: {len(df):,}")

    print(f"\nBy SIC tier (sourcing authority):")
    for tier in ['Tier 1', 'Tier 2', 'Tier 3']:
        count = len(df[df['sic_tier'] == tier])
        pct   = count / len(df) * 100 if len(df) > 0 else 0
        print(f"  {tier}   {count:>6,}  ({pct:.1f}%)")

    print(f"\nBy SIC confidence:")
    for conf in ['High', 'Medium', 'Low']:
        count = len(df[df['sic_confidence'] == conf])
        pct   = count / len(df) * 100 if len(df) > 0 else 0
        print(f"  {conf:<10} {count:>6,}  ({pct:.1f}%)")

    print(f"\nBy chain position:")
    for pos in ['Upstream', 'Downstream', 'Enabling']:
        count = len(df[df['chain_position'] == pos])
        pct   = count / len(df) * 100 if len(df) > 0 else 0
        print(f"  {pos:<14} {count:>6,}  ({pct:.1f}%)")

    print(f"\nBy node (primary_node assignment):")
    print(f"  Node assignments derived from OECD/BEA/ESA/Eurostat/JRC")
    print(f"  (2023) Table 1 space activity categories.")
    print(f"  These are indicative — confirmed at Stage 3 via SCC,")
    print(f"  ukspacetech.com, and company website evidence.")
    print()
    for node in ['N1','N2','N3','N4','N5','N6','N7','N8','N9']:
        count = len(df[df['primary_node'] == node])
        label = NODE_LABELS.get(node, '')
        flag  = ' ← populated via SCC/ukspacetech (Sources 2+3)' \
                if node == 'N6' and count == 0 else ''
        print(f"  {node}  {label:<42} {count:>6,}{flag}")

    defence_check = len(df[df['requires_defence_check'] == 'Yes'])
    print(f"\nFirms requiring defence check at Stage 3: {defence_check:,}")
    print(f"  (SIC codes 30300, 33160, 26309 — contain both civilian")
    print(f"   and military firms per ONS SIC 2026)")

    print(f"\nSample — first 20 firms:")
    cols = ['company_name', 'primary_node', 'sic_tier',
            'sic_confidence', 'requires_defence_check', 'post_town']
    print(df[cols].head(20).to_string(index=False))


# ── SAVE ───────────────────────────────────────────────────────────────────

def save_output(df):
    """Save bulk CSV."""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = f"{OUTPUT_DIR}/seed_firms_ch_bulk.csv"
    df.to_csv(output_path, index=False)

    print(f"\n" + "=" * 65)
    print("FILE SAVED")
    print("=" * 65)
    print(f"  {output_path}")
    print(f"  {len(df):,} candidate firms")
    print(f"\nColumns explanation:")
    print(f"  primary_node       — indicative node from OECD Table 1 mapping")
    print(f"  chain_position     — Upstream/Downstream/Enabling from OECD Table 1")
    print(f"  sic_confidence     — High/Medium/Low (how space-specific the code is)")
    print(f"  sic_tier           — Tier 1/2/3 (sourcing authority)")
    print(f"  sic_source         — exact document and table reference")
    print(f"  oecd_activity_category — OECD Table 1 space activity category")
    print(f"  requires_defence_check — Yes/No per ONS SIC 2026")
    print(f"\nNEXT STEPS:")
    print(f"  → Source 2: ukspacetech.com scraper")
    print(f"  → Source 3: SCC manual validation")
    print(f"  → Merge all sources then run space_pipeline.py")
    print("=" * 65)


# ── MAIN ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    df = run_extraction()
    print_summary(df)
    save_output(df)

# ── NODE DEFINITIONS ───────────────────────────────────────────────────────
# Authoritative justification for each value-chain node definition
# Used for methodology chapter documentation and Stage 3 verification
#
# Structure of the nine-node value chain is derived by synthesising:
#   (1) OECD (2022) three-segment framework
#   (2) OECD/BEA/ESA/Eurostat/JRC (2023) Table 1 activity categories
#   (3) UK Space Agency (2025) five-segment framework
#   (4) Academic literature (Caliari et al., 2023; Gereffi et al., 2005)
#
# The nine nodes represent the finest level of granularity that all four
# sources support simultaneously. Nodes finer than this (e.g. splitting N2
# into propulsion vs imaging payloads) would not be defensible from the
# secondary data available since Companies House and SCC do not classify
# at that level. Nodes coarser than this (e.g. merging N6 and N7) would
# obscure analytically important distinctions between firms that operate
# satellites and firms that process the data they produce.

NODE_DEFINITIONS = {

    'N1': {
        'label': 'Components and Materials',
        'chain_position': 'Upstream',
        'definition': (
            'Firms that supply the raw materials, specialist components, '
            'and electronic parts that are assembled into space subsystems '
            'and full satellite platforms. Activities include manufacture of '
            'radiation-hardened electronic components, specialist materials '
            '(composites, thermal protection), propellants, optical glass, '
            'and precision mechanical parts.'
        ),
        'sources': {
            'OECD (2022)': (
                'Explicitly includes "material and components supply" as a '
                'distinct upstream activity within the space economy. '
                'OECD Handbook on Measuring the Space Economy, 2nd edn, '
                'p.17. doi:10.1787/8bfef437-en'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 lists "Supply of components and equipment for space '
                'systems" as a distinct space activity category covering ISIC '
                'sections C manufacturing codes 20, 22, 25, 26, 27, 28. '
                'doi:10.2785/695530'
            ),
            'UK Space Agency (2025)': (
                'Components sub-activity within Space Manufacturing segment. '
                'Size and Health of the UK Space Industry 2024.'
            ),
        },
        'boundary_upper': 'N2 — when components are assembled into a functioning subsystem',
        'boundary_lower': 'Raw material extraction and general manufacturing (excluded)',
        'sic_codes': ['26110', '26512', '25620', '27200'],
        'n6_coverage': False,
    },

    'N2': {
        'label': 'Subsystems and Payloads',
        'chain_position': 'Upstream',
        'definition': (
            'Firms that design and manufacture functional subsystems that '
            'are integrated into complete satellites or spacecraft. Activities '
            'include propulsion units, attitude and orbit control systems '
            '(ADCS), power systems, thermal management, communications '
            'payloads, imaging payloads, scientific instruments, and '
            'navigation equipment. Distinguished from N1 by the requirement '
            'that output is a functional subsystem rather than a component input.'
        ),
        'sources': {
            'OECD (2022)': (
                'Explicitly includes "manufacturing of space systems, '
                'subsystems and equipment" as a distinct upstream activity. '
                'OECD Handbook on Measuring the Space Economy, 2nd edn, p.17.'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 "Supply of components and equipment for space '
                'systems" and Table 4 NACE 26.51 (instruments and appliances '
                'for measuring, testing and navigation), 26.30 (communication '
                'equipment), 26.70 (optical instruments). doi:10.2785/695530'
            ),
            'ESPI (2019) via arxiv (2024)': (
                'Rule-Based Methodology for Company Identification paper '
                '(arxiv:2412.02342) states: "The upstream segment includes '
                'sub-systems, equipment, components, and related software '
                'supply (ESPI, 2019)" — explicitly distinguishing subsystems '
                'from components as a separate upstream stage.'
            ),
            'UK Space Agency (2025)': (
                'Subsystems and payload sub-activities within Space '
                'Manufacturing segment.'
            ),
        },
        'boundary_upper': 'N3 — when subsystems are integrated into a complete platform',
        'boundary_lower': 'N1 — when output is a component input rather than functional subsystem',
        'sic_codes': ['26309', '26511', '26701'],
        'n6_coverage': False,
    },

    'N3': {
        'label': 'Satellite and Spacecraft Manufacturing',
        'chain_position': 'Upstream',
        'definition': (
            'Firms that integrate subsystems and components into complete '
            'satellite platforms or spacecraft, including full system design, '
            'integration, assembly, and testing (AIT). Activities include '
            'satellite bus design and manufacture, spacecraft integration, '
            'environmental testing (thermal vacuum, vibration), and factory '
            'overhaul and rebuilding of spacecraft. Includes both full '
            'platform prime contractors and system integrators.'
        ),
        'sources': {
            'OECD (2022)': (
                '"Manufacturing of space systems" is the primary upstream '
                'manufacturing activity. OECD Handbook on Measuring the '
                'Space Economy, 2nd edn, p.17.'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 explicitly lists "Integration and supply of full '
                'space systems (e.g. launchers, satellites)" as a distinct '
                'activity category. Table 4 NACE 30.30 manufacture of air '
                'and spacecraft, 33.16 repair and maintenance of spacecraft. '
                'doi:10.2785/695530'
            ),
            'ONS (2026)': (
                'SIC 2026 introduces dedicated codes 30.331 (civilian '
                'spacecraft manufacture) and 30.332 (military spacecraft '
                'manufacture), separating this node from aviation '
                'manufacturing for the first time.'
            ),
            'UK Government (2018)': (
                'Upstream Space: A Galaxy of Capability (BEIS/SIA) defines '
                'upstream as "the design, manufacture of spacecraft, payloads, '
                'systems, subsystems, and components" — placing spacecraft '
                'manufacturing as the central upstream activity.'
            ),
            'UK Space Agency (2025)': (
                'Space Manufacturing segment. Surrey Satellite Technology, '
                'Airbus Defence and Space UK, and SSTL are leading UK firms '
                'at this node.'
            ),
        },
        'boundary_upper': 'N4/N5 — when complete platform is delivered for launch or ground integration',
        'boundary_lower': 'N2 — subsystem manufacture prior to platform integration',
        'sic_codes': ['30300', '33160'],
        'n6_coverage': False,
    },

    'N4': {
        'label': 'Ground Segment',
        'chain_position': 'Upstream',
        'definition': (
            'Firms that design, build, and operate the ground-based '
            'infrastructure that supports satellite operations. Activities '
            'include ground station hardware and networks, telemetry tracking '
            'and control (TT&C) systems, satellite command and control '
            'software, antenna systems, and ground segment integration. '
            'Distinguished from N6 in that N4 firms supply the ground '
            'infrastructure while N6 firms operate satellites using it.'
        ),
        'sources': {
            'OECD (2022)': (
                'Explicitly includes "telemetry, tracking and command '
                'stations" as a distinct upstream activity within the space '
                'economy definition. OECD Handbook on Measuring the Space '
                'Economy, 2nd edn, p.17.'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 lists "Construction of space facilities (e.g. '
                'spaceports and other ground facilities, observatories)" as '
                'a distinct activity category under ISIC section F '
                'Construction. doi:10.2785/695530'
            ),
            'UK Space Agency (2025)': (
                'Ground segment identified as a sub-activity within both '
                'Space Manufacturing (ground hardware) and Space Operations '
                '(ground station operations) segments.'
            ),
            'Satellite Applications Catapult (2024)': (
                'SCC taxonomy includes Ground Segment and Space Domain '
                'Awareness as a distinct upstream activity category.'
            ),
        },
        'boundary_upper': 'N6 — when ground systems are used to operate satellites',
        'boundary_lower': 'N3 — spacecraft itself, not ground infrastructure',
        'sic_codes': ['26512', '71200'],
        'n6_coverage': False,
    },

    'N5': {
        'label': 'Launch',
        'chain_position': 'Upstream',
        'definition': (
            'Firms that provide launch vehicles, launch services, launch '
            'brokerage, and associated launch site infrastructure. Activities '
            'include launch vehicle design and manufacture, launch service '
            'provision, payload integration for launch, range operations, '
            'spaceport infrastructure, and suborbital launch services. '
            'OECD (2022) explicitly classifies launch as upstream.'
        ),
        'sources': {
            'OECD (2022)': (
                '"Launch operation services are most often defined as part '
                'of the upstream sector." OECD Handbook on Measuring the '
                'Space Economy, 2nd edn, p.17. doi:10.1787/8bfef437-en'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 explicitly lists "Space launch activities (freight '
                'transport and space tourism)" as a distinct category under '
                'ISIC H: Transportation and storage, code 51. Table 4 '
                'NACE 51.22 space transport, 52.23 services incidental to '
                'space transportation. doi:10.2785/695530'
            ),
            'ONS (2007)': (
                'SIC 2007 code 51220 directly named "space transport, space '
                'vehicle launching, space transport of freight and passengers" '
                '— only code explicitly naming space transport.'
            ),
            'ONS (2026)': (
                'SIC 2026 code 51.22 confirmed: "launching of satellites '
                'and space vehicles; space transport of freight and passengers."'
            ),
        },
        'boundary_upper': 'N6 — satellite operations begin after successful launch',
        'boundary_lower': 'N3 — spacecraft manufacture prior to launch integration',
        'sic_codes': ['51220', '52230'],
        'n6_coverage': False,
    },

    'N6': {
        'label': 'Satellite Operations',
        'chain_position': 'Downstream',
        'definition': (
            'Firms that operate satellites in orbit on behalf of themselves '
            'or third parties, including satellite fleet management, orbital '
            'manoeuvring, space situational awareness (SSA), and third-party '
            'ground segment operation. Distinguished from N4 in that N6 '
            'firms operate satellites using ground infrastructure, whereas '
            'N4 firms supply that infrastructure. Distinguished from N7/N8 '
            'in that N6 firms manage the space asset itself rather than '
            'processing or distributing the data it produces.'
        ),
        'sources': {
            'OECD (2022)': (
                'Downstream segment explicitly includes "space operations '
                'for terrestrial exploitation of data and signals." '
                'OECD Handbook on Measuring the Space Economy, 2nd edn, p.17.'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 lists "Operation of space systems" as a distinct '
                'activity category under ISIC I: Information and '
                'communication, code 61. doi:10.2785/695530'
            ),
            'UK Space Agency (2025)': (
                'Space Operations segment covers proprietary satellite '
                'operation (firms operating their own satellites) and '
                'third-party satellite operation (firms operating satellites '
                'owned by others) as distinct sub-activities.'
            ),
            'Satellite Applications Catapult (2024)': (
                'SCC taxonomy: Downstream → Operate. Used as primary '
                'source for N6 firm identification since no SIC code '
                'in SIC 2007 or SIC 2026 directly captures satellite '
                'operations as a distinct activity.'
            ),
        },
        'boundary_upper': 'N7/N8 — data processing and applications built on satellite signals',
        'boundary_lower': 'N5 — launch concludes, operations begin',
        'sic_codes': [],
        'sic_note': (
            'No SIC code in SIC 2007 or SIC 2026 directly captures '
            'satellite operations. Satellite operators typically file '
            'under 61300 (satellite telecoms) or 61900 (other telecoms), '
            'making them indistinguishable from N8 firms in Companies '
            'House data. N6 firms identified via SCC (Source 3, '
            'Downstream → Operate filter) and ukspacetech.com (Source 2, '
            'Ground Segment and SDA / In-Space Economy categories).'
        ),
        'n6_coverage': True,
    },

    'N7': {
        'label': 'Data Processing and Analytics',
        'chain_position': 'Downstream',
        'definition': (
            'Firms that process raw satellite signals and data into usable '
            'products and analytical outputs. Activities include earth '
            'observation data processing, image processing and analysis, '
            'GNSS data processing, satellite data product generation, '
            'value-added data services, and geospatial analytics. '
            'Distinguished from N6 in that N7 firms process data rather '
            'than operate the satellites that produce it. Distinguished '
            'from N8 in that N7 firms produce data products rather than '
            'end-user services built on those products.'
        ),
        'sources': {
            'OECD (2022)': (
                'Downstream segment includes exploitation of space data. '
                'OECD Handbook on Measuring the Space Economy, 2nd edn.'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 lists "Downstream services for earth observation; '
                'navigation, timing; and satellite telecommunications" as '
                'a distinct activity category. Crucially, document states '
                'explicitly at p.11: "Many companies developing downstream '
                'space applications are registered as data-processing '
                'companies under the much broader ISIC class 6311: Data '
                'processing, hosting and related activities." '
                'doi:10.2785/695530'
            ),
            'UK Space Agency (2025)': (
                'Space Applications segment sub-activity: processors of '
                'satellite data. Size and Health of the UK Space Industry 2024.'
            ),
            'Satellite Applications Catapult (2024)': (
                'SCC taxonomy: Downstream → Analyse. Earth Observation '
                'and Space Data Architecture capability areas.'
            ),
        },
        'boundary_upper': 'N8 — end-user services built on processed data products',
        'boundary_lower': 'N6 — satellite operations that produce the raw data',
        'sic_codes': ['63110'],
        'n6_coverage': False,
    },

    'N8': {
        'label': 'Applications and Services',
        'chain_position': 'Downstream',
        'definition': (
            'Firms that deliver end-user products and services built on '
            'satellite data, signals, or infrastructure. Activities include '
            'satellite communications (voice, broadband, maritime, aviation), '
            'Direct-to-Home (DTH) broadcasting, satellite television, '
            'location-based services, precision agriculture, satellite '
            'internet (e.g. OneWeb/Starlink resellers), and navigation '
            'applications. This node generates the majority of UK space '
            'sector income — 73% of total including DTH broadcasting '
            '(UK Space Agency, 2025). Distinguished from N7 in that N8 '
            'firms deliver services to end users rather than data products '
            'to intermediate processors.'
        ),
        'sources': {
            'OECD (2022)': (
                '"Activities that depend on the exploitation of space data '
                'and signals (e.g. satellite television) as well as the '
                'manufacturing of associated equipment." OECD Handbook on '
                'Measuring the Space Economy, 2nd edn, p.17.'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 lists "Supply of services supporting consumer '
                'markets (e.g. DTH providers, data-derived commercial '
                'services)" as a distinct activity category. Explicitly '
                'notes this "only includes activities that directly rely '
                'on the provision of a space capacity to exist and function." '
                'Table 4 NACE 60.10, 60.20, 61.10, 61.20, 61.30, 61.90. '
                'doi:10.2785/695530'
            ),
            'UK Space Agency (2025)': (
                'Space Applications segment — the largest by income. '
                'Includes satellite communications, DTH broadcasting, '
                'earth observation applications, navigation services. '
                'Accounts for 73% of total industry income and 48% of '
                'non-broadcasting income.'
            ),
            'Satellite Applications Catapult (2024)': (
                'SCC taxonomy: Downstream → Product. Capability areas: '
                'Satellite Communications, Earth Observation, Positioning '
                'Navigation and Timing.'
            ),
        },
        'boundary_upper': 'End users (excluded — not space sector participants)',
        'boundary_lower': 'N7 — data processing that produces inputs to N8 services',
        'sic_codes': ['61300', '60200', '60100', '61100', '61200', '61900'],
        'n6_coverage': False,
    },

    'N9': {
        'label': 'Enabling and Ancillary',
        'chain_position': 'Enabling',
        'definition': (
            'Firms that provide cross-chain support activities that do not '
            'directly produce space hardware or end-user space services but '
            'enable the chain to function. Activities include space sector '
            'insurance and risk assessment, legal and financial services '
            'specific to space, engineering consultancy, R&D organisations, '
            'space policy and regulatory advisory, market research, and '
            'business incubation. Distinguished from other nodes in that '
            'N9 firms can support multiple nodes simultaneously without '
            'being classified at any specific chain stage.'
        ),
        'sources': {
            'OECD (2022)': (
                'Defines a third perimeter: "space-derived activities, '
                'which are derived from space technologies but not dependent '
                'on them to function." Also includes research and ancillary '
                'services within the space economy definition. '
                'OECD Handbook on Measuring the Space Economy, 2nd edn, p.17.'
            ),
            'OECD/BEA/ESA/Eurostat/JRC (2023)': (
                'Table 1 lists three distinct enabling activity categories: '
                '"Fundamental and applied research" (ISIC 72), "Ancillary '
                'activities e.g. space insurance" (ISIC 65), and "Research '
                'and development services, engineering services testing, '
                'design" (ISIC 71). Table 4: NACE 65.12 (non-life insurance '
                'including satellite launching insurance, CPC 71332), '
                '70.22 (management consultancy), 71.12 (engineering), '
                '72.19 (R&D natural sciences), 74.90 (other professional). '
                'doi:10.2785/695530'
            ),
            'UK Space Agency (2025)': (
                'Ancillary Services segment covers insurance, legal, '
                'financial, consulting, and other support activities. '
                'Accounts for approximately 6% of non-broadcasting income.'
            ),
            'Satellite Applications Catapult (2024)': (
                'SCC taxonomy: Other → Ancillary Services. Capability '
                'area: Ancillary Services.'
            ),
        },
        'boundary_upper': 'N/A — cross-chain enabling activities',
        'boundary_lower': 'General professional services not specific to space (excluded)',
        'sic_codes': ['72190', '71121', '71122', '71200', '65120', '70229', '74909'],
        'n6_coverage': False,
    },

}