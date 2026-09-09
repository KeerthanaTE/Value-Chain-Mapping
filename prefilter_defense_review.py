"""
UK Space Sector — Defence Review Pre-Filter

Reads pipeline_defence_review.xlsx and auto-classifies firms
using keyword rules before manual review.

Classification logic:
  Auto → space_peripheral=Yes (not space sector at all):
    Aviation MRO, flight training, aircraft leasing, cabin interiors,
    helicopter services, pilot training, aircraft painting/detailing

  Auto → defence_primary=Partial (confirmed space, dual-use):
    Firms with space/satellite keywords + defence signals

  Auto → defence_primary=No (confirmed space, civil):
    Firms with clear space keywords, no defence signals

  Manual review needed:
    Ambiguous names — no clear aviation OR space signal
    Defence-adjacent names — needs website check

Output:
  pipeline_defence_review_filtered.xlsx
    Sheet 1: Auto-classified (pre-filled yellow cells)
    Sheet 2: Manual review only (~50-100 firms)
    Sheet 3: Summary statistics
"""

import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import re
import os
from datetime import date

OUTPUT_DIR  = "/Users/keerthanate/dissertation/data"
INPUT_PATH  = f"{OUTPUT_DIR}/pipeline_defence_review.xlsx"
OUTPUT_PATH = f"{OUTPUT_DIR}/pipeline_defence_review_filtered.xlsx"
DATE_TODAY  = str(date.today())

# ── CLASSIFICATION PATTERNS ────────────────────────────────────────────────

# These patterns in company name → space_peripheral=Yes (not space sector)
AVIATION_PERIPHERAL = [
    # MRO and maintenance
    r'\baircraf[t]?\s*maintenance\b', r'\baero\s*maintenance\b',
    r'\bmro\b', r'\bline\s*maintenance\b', r'\bpart.?145\b',
    r'\bengine\s*overhaul\b', r'\baircraft\s*engineer\b',
    r'\baircraft\s*service\b', r'\baircraft\s*repair\b',
    r'\baviation\s*service\b', r'\baviation\s*maintenance\b',
    r'\baog\b', r'\bc.check\b', r'\bborescope\b',
    r'\bavionics\s*repair\b', r'\bbase\s*maintenance\b',
    # Flight training and schools
    r'\bflight\s*train\b', r'\bflight\s*school\b',
    r'\bpilot\s*train\b', r'\bflight\s*acade\b',
    r'\bcommercial\s*pilot\b', r'\bppl\b', r'\batpl\b',
    r'\bflight\s*instructor\b',
    # Cabin and interiors
    r'\bcabin\s*interior\b', r'\baircraft\s*seating\b',
    r'\baircraft\s*interior\b', r'\baircraft\s*cabin\b',
    r'\baircraft\s*paint\b', r'\baircraft\s*detail\b',
    r'\baero\s*detail\b', r'\baerospace\s*detail\b',
    r'\baero\s*shine\b', r'\baero\s*paint\b',
    r'\baero\s*lux\b', r'\baircamo\b',
    # Aircraft leasing and asset management
    r'\baircraft\s*leas\b', r'\baircraft\s*asset\b',
    r'\baircraft\s*trading\b', r'\baero\s*cap\b',
    r'\baircraft\s*financ\b', r'\baircraft\s*manag\b',
    # Helicopter specific
    r'\bhelicopter\b', r'\bheli\b', r'\brotor\b(?!.*space)',
    # Air charter and operations
    r'\bair\s*charter\b', r'\bair\s*ambu\b',
    r'\bair\s*taxi\b', r'\bair\s*cargo\b',
    # Generic aviation with no space signal
    r'\bairline\b', r'\baeroplane\b', r'\bairfield\b',
    r'\bparachute\b', r'\bglider\b', r'\bballoon\b',
]

# These in company name → likely space sector, check for defence
SPACE_POSITIVE = [
    r'satellite', r'\bspace\b', r'spacecraft', r'orbital',
    r'launch\s*vehicle', r'cubesat', r'smallsat', r'nanosat',
    r'gnss', r'propulsion\s*system', r'payload\s*system',
    r'earth\s*obs', r'geospat', r'remote\s*sens',
    r'astro(?!nomy|naut)', r'cosm', r'rocket',
    r'telemetry', r'ground\s*station', r'satcom',
    r'spaceport', r'in.orbit', r'debris\s*remov',
]

# These in company name → defence signal (needs manual check)
DEFENCE_SIGNALS = [
    r'\bdefenc\b', r'\bdefens\b', r'\bmilitar\b',
    r'\bmod\b', r'\bnato\b', r'\bsovereign\b',
    r'\btactical\b', r'\bcovert\b', r'\bclassif\b',
    r'\bweapon\b', r'\barma\b', r'\bcombat\b',
    r'\bintelligen\b', r'\bisig\b', r'\bsigint\b',
    r'\bisr\b', r'\bsurveill\b', r'\bcontra\b',
]

# These in company name → generic non-space (not aviation, not space)
GENERIC_NONSPACE = [
    r'\bconsult(?!.*space)\b', r'\bmanag(?!.*space)\b',
    r'\baccoun\b', r'\blegal\b', r'\blaw\b',
    r'\bproper\b', r'\brestat\b', r'\bconstruct\b',
    r'\bretail\b', r'\bcater\b', r'\brestaurant\b',
    r'\bcleaning\b', r'\bpaint(?!.*space)\b',
    r'\bpluimb\b', r'\belectric(?!.*space)\b',
    r'\btransport(?!.*space)\b', r'\blogistic(?!.*space)\b',
]


def classify_firm(name, sic_text=''):
    """
    Classify a firm based on company name and SIC description.

    Returns (defence_primary, space_peripheral, confidence, reason)
    confidence: 'auto' = no manual review needed
                'manual' = needs website check
    """
    name_lower = str(name).lower()
    sic_lower  = str(sic_text).lower()
    combined   = name_lower + ' ' + sic_lower

    has_space    = any(re.search(p, combined) for p in SPACE_POSITIVE)
    has_aviation = any(re.search(p, name_lower) for p in AVIATION_PERIPHERAL)
    has_defence  = any(re.search(p, name_lower) for p in DEFENCE_SIGNALS)
    has_generic  = any(re.search(p, name_lower) for p in GENERIC_NONSPACE)

    # Clear aviation MRO — not space sector
    if has_aviation and not has_space:
        return ('', 'Yes', 'auto',
                'Aviation MRO/training/leasing keyword in name — '
                'not space sector')

    # Clear generic non-space, no space signal
    if has_generic and not has_space and not has_aviation:
        return ('', 'Yes', 'auto',
                'Generic non-space business keyword — '
                'no space sector signal')

    # Clear space sector, no defence signal
    if has_space and not has_defence:
        return ('No', '', 'auto',
                'Space sector keyword confirmed, no defence signal')

    # Space + defence signal — needs manual check
    if has_space and has_defence:
        return ('', '', 'manual',
                'Space keyword + defence signal — '
                'check website for primary business')

    # Defence signal, no space keyword — likely defence non-space
    if has_defence and not has_space:
        return ('Yes', '', 'auto',
                'Defence signal in name, no space keyword — '
                'likely defence-primary non-space firm')

    # Ambiguous — no clear signal either way
    return ('', '', 'manual',
            'No clear space or non-space signal — '
            'check Companies House profile and website')


def run():
    print("=" * 65)
    print("Defence Review Pre-Filter")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    # Load review sheet
    print(f"\nLoading: {INPUT_PATH}")
    try:
        wb_in = openpyxl.load_workbook(INPUT_PATH, data_only=True)
    except FileNotFoundError:
        print(f"Not found — run space_pipeline_v3.py --finalise first")
        return

    ws_in = wb_in['Defence Review — Pipeline']

    # Read all rows
    rows = []
    for row in ws_in.iter_rows(min_row=5, values_only=True):
        if not row[1]:
            continue
        rows.append({
            'row_num':        row[0],
            'company_name':   str(row[1]).strip(),
            'primary_node':   str(row[2]).strip() if row[2] else '',
            'chain_position': str(row[3]).strip() if row[3] else '',
            'sic_code':       str(row[4]).strip() if row[4] else '',
            'sic_text':       str(row[5]).strip() if row[5] else '',
            'ch_url':         str(row[6]).strip() if row[6] else '',
            'website':        str(row[7]).strip() if row[7] else '',
        })

    print(f"Firms to classify: {len(rows)}")

    # Classify each firm
    auto_peripheral = []
    auto_civil      = []
    auto_defence    = []
    manual_review   = []

    for r in rows:
        defence, peripheral, confidence, reason = classify_firm(
            r['company_name'], r['sic_text']
        )
        r['defence_primary']   = defence
        r['space_peripheral']  = peripheral
        r['auto_confidence']   = confidence
        r['classification_reason'] = reason

        if confidence == 'auto':
            if peripheral == 'Yes':
                auto_peripheral.append(r)
            elif defence == 'Yes':
                auto_defence.append(r)
            else:
                auto_civil.append(r)
        else:
            manual_review.append(r)

    print(f"\nClassification results:")
    print(f"  Auto → space_peripheral=Yes (not space): {len(auto_peripheral):,}")
    print(f"  Auto → defence_primary=Yes (defence):    {len(auto_defence):,}")
    print(f"  Auto → defence_primary=No (civil space): {len(auto_civil):,}")
    print(f"  Manual review needed:                    {len(manual_review):,}")
    print(f"\nManual review reduced from {len(rows):,} to {len(manual_review):,} firms")
    est_mins = len(manual_review) * 0.5
    print(f"Estimated manual review time: {est_mins:.0f} minutes "
          f"(30s per firm)")

    # ── BUILD OUTPUT EXCEL ─────────────────────────────────────────────────
    print(f"\nBuilding output Excel...")

    # Styles
    NAVY   = PatternFill('solid', fgColor='1F3864')
    BLUE   = PatternFill('solid', fgColor='2E75B6')
    YELLOW = PatternFill('solid', fgColor='FFD700')
    GREEN  = PatternFill('solid', fgColor='E2EFDA')
    ORANGE = PatternFill('solid', fgColor='FCE4D6')
    RED    = PatternFill('solid', fgColor='FFE0E0')
    GREY   = PatternFill('solid', fgColor='F2F2F2')
    WHITE  = PatternFill('solid', fgColor='FFFFFF')

    HDR_F  = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    BODY_F = Font(name='Arial', size=10)
    BOLD_F = Font(name='Arial', bold=True, size=10)
    LINK_F = Font(name='Arial', size=10, color='0563C1', underline='single')
    INP_F  = Font(name='Arial', bold=True, size=10, color='000080')
    GRN_F  = Font(name='Arial', bold=True, size=10, color='1F6B2E')
    RED_F  = Font(name='Arial', bold=True, size=10, color='9C0000')
    thin   = Side(style='thin', color='BFBFBF')
    BDR    = Border(left=thin, right=thin, top=thin, bottom=thin)

    def hdr(cell, fill=None):
        cell.font = HDR_F; cell.fill = fill or NAVY
        cell.alignment = Alignment(horizontal='center',
                                    vertical='center', wrap_text=True)
        cell.border = BDR

    def cel(cell, fill=None, bold=False, link=False,
            green=False, red=False):
        if green:   cell.font = GRN_F
        elif red:   cell.font = RED_F
        elif link:  cell.font = LINK_F
        elif bold:  cell.font = BOLD_F
        else:       cell.font = BODY_F
        cell.fill = fill or WHITE
        cell.alignment = Alignment(horizontal='left',
                                    vertical='center', wrap_text=True)
        cell.border = BDR

    def inp(cell):
        cell.font = INP_F; cell.fill = YELLOW
        cell.alignment = Alignment(horizontal='left',
                                    vertical='center', wrap_text=True)
        cell.border = BDR

    wb = openpyxl.Workbook()

    # ── SHEET 1: MANUAL REVIEW ONLY ────────────────────────────────────────
    ws1 = wb.active
    ws1.title = 'Manual Review Required'
    ws1.sheet_view.showGridLines = False

    ws1.merge_cells('A1:L1')
    ws1['A1'] = (f'Manual Review Required — {len(manual_review)} firms '
                 f'(auto-classified {len(rows)-len(manual_review):,} firms)')
    ws1['A1'].font = Font(name='Arial', bold=True, size=13, color='1F3864')
    ws1['A1'].alignment = Alignment(horizontal='left', vertical='center')
    ws1.row_dimensions[1].height = 26

    ws1.merge_cells('A2:L2')
    ws1['A2'] = ('Only these firms need manual website review. '
                 'All others were auto-classified — see Auto-Classified sheet. '
                 'Fill YELLOW cells: defence_primary (Yes/Partial/No) '
                 'or space_peripheral (Yes if not space sector at all).')
    ws1['A2'].font = Font(name='Arial', italic=True, size=10, color='595959')
    ws1['A2'].alignment = Alignment(horizontal='left', vertical='center',
                                     wrap_text=True)
    ws1.row_dimensions[2].height = 35
    ws1.row_dimensions[3].height = 6

    headers_manual = [
        '#', 'Company Name', 'Node', 'Chain',
        'SIC Code', 'SIC Description', 'CH Profile', 'Website',
        'Why manual?',
        'defence_primary\n(Yes/Partial/No)',
        'space_peripheral\n(Yes if not space)',
        'evidence_notes',
    ]
    for col, h in enumerate(headers_manual, 1):
        cell = ws1.cell(row=4, column=col, value=h)
        hdr(cell)
    ws1.row_dimensions[4].height = 40
    ws1.freeze_panes = 'A5'

    for i, r in enumerate(manual_review):
        row = i + 5
        fill = ORANGE if i % 2 == 0 else WHITE

        ws1.cell(row=row, column=1, value=i+1).fill = fill
        ws1.cell(row=row, column=1).font = BODY_F
        ws1.cell(row=row, column=1).alignment = Alignment(
            horizontal='center', vertical='center')
        ws1.cell(row=row, column=1).border = BDR

        c = ws1.cell(row=row, column=2, value=r['company_name'])
        cel(c, fill=fill, bold=True)
        c = ws1.cell(row=row, column=3, value=r['primary_node'])
        cel(c, fill=fill)
        c = ws1.cell(row=row, column=4, value=r['chain_position'])
        cel(c, fill=fill)
        c = ws1.cell(row=row, column=5, value=r['sic_code'])
        cel(c, fill=fill)
        c = ws1.cell(row=row, column=6,
                     value=str(r['sic_text'])[:60])
        cel(c, fill=fill)

        ch_url = r.get('ch_url', '')
        c = ws1.cell(row=row, column=7,
                     value='CH Profile' if ch_url and ch_url != 'nan' else '—')
        if ch_url and ch_url not in ('nan', '—', ''):
            c.hyperlink = ch_url; cel(c, fill=fill, link=True)
        else:
            cel(c, fill=fill)

        website = r.get('website', '')
        c = ws1.cell(row=row, column=8,
                     value=website if website and website != 'nan' else '—')
        if website and website not in ('nan', '—', ''):
            c.hyperlink = website; cel(c, fill=fill, link=True)
        else:
            cel(c, fill=fill)

        c = ws1.cell(row=row, column=9,
                     value=r['classification_reason'])
        cel(c, fill=fill)

        for col in [10, 11, 12]:
            inp(ws1.cell(row=row, column=col, value=''))

        ws1.row_dimensions[row].height = 40

    for col, w in enumerate(
        [5, 30, 8, 10, 10, 35, 12, 28, 35, 18, 16, 35], 1
    ):
        ws1.column_dimensions[get_column_letter(col)].width = w

    # ── SHEET 2: AUTO-CLASSIFIED ───────────────────────────────────────────
    ws2 = wb.create_sheet('Auto-Classified')
    ws2.sheet_view.showGridLines = False

    ws2.merge_cells('A1:J1')
    ws2['A1'] = (f'Auto-Classified — {len(rows)-len(manual_review):,} firms '
                 f'(no manual review needed)')
    ws2['A1'].font = Font(name='Arial', bold=True, size=13, color='1F3864')
    ws2['A1'].alignment = Alignment(horizontal='left', vertical='center')
    ws2.row_dimensions[1].height = 26

    ws2.merge_cells('A2:J2')
    ws2['A2'] = ('These firms were classified automatically using keyword rules. '
                 'GREEN = confirmed space sector (civil). '
                 'RED = space peripheral (not space sector — aviation MRO etc). '
                 'No manual review needed unless you spot an obvious error.')
    ws2['A2'].font = Font(name='Arial', italic=True, size=10, color='595959')
    ws2['A2'].alignment = Alignment(horizontal='left', vertical='center',
                                     wrap_text=True)
    ws2.row_dimensions[2].height = 35
    ws2.row_dimensions[3].height = 6

    headers_auto = [
        '#', 'Company Name', 'Node', 'Chain', 'SIC Code',
        'defence_primary', 'space_peripheral',
        'Classification', 'Reason', 'CH Profile',
    ]
    for col, h in enumerate(headers_auto, 1):
        cell = ws2.cell(row=4, column=col, value=h)
        hdr(cell)
    ws2.row_dimensions[4].height = 35
    ws2.freeze_panes = 'A5'

    all_auto = auto_peripheral + auto_defence + auto_civil
    # Sort: peripheral first, then defence, then civil
    all_auto_sorted = (
        sorted(auto_peripheral, key=lambda x: x['company_name']) +
        sorted(auto_defence,    key=lambda x: x['company_name']) +
        sorted(auto_civil,      key=lambda x: x['company_name'])
    )

    for i, r in enumerate(all_auto_sorted):
        row = i + 5
        is_civil      = r['defence_primary'] == 'No'
        is_peripheral = r['space_peripheral'] == 'Yes'
        is_def        = r['defence_primary'] == 'Yes'

        if is_civil:
            fill = GREEN
        elif is_peripheral or is_def:
            fill = RED
        else:
            fill = GREY if i % 2 == 0 else WHITE

        ws2.cell(row=row, column=1, value=i+1).fill = fill
        ws2.cell(row=row, column=1).font = BODY_F
        ws2.cell(row=row, column=1).alignment = Alignment(
            horizontal='center', vertical='center')
        ws2.cell(row=row, column=1).border = BDR

        c = ws2.cell(row=row, column=2, value=r['company_name'])
        cel(c, fill=fill, bold=True,
            green=is_civil, red=is_peripheral or is_def)
        c = ws2.cell(row=row, column=3, value=r['primary_node'])
        cel(c, fill=fill)
        c = ws2.cell(row=row, column=4, value=r['chain_position'])
        cel(c, fill=fill)
        c = ws2.cell(row=row, column=5, value=r['sic_code'])
        cel(c, fill=fill)
        c = ws2.cell(row=row, column=6, value=r['defence_primary'])
        cel(c, fill=fill, green=is_civil, red=is_def)
        c = ws2.cell(row=row, column=7, value=r['space_peripheral'])
        cel(c, fill=fill, red=is_peripheral)

        classification = (
            'Civil space ✓' if is_civil else
            'Not space sector ✗' if is_peripheral else
            'Defence primary ✗'
        )
        c = ws2.cell(row=row, column=8, value=classification)
        cel(c, fill=fill, green=is_civil, red=is_peripheral or is_def)
        c = ws2.cell(row=row, column=9,
                     value=r['classification_reason'][:80])
        cel(c, fill=fill)

        ch_url = r.get('ch_url', '')
        c = ws2.cell(row=row, column=10,
                     value='CH Profile' if ch_url and ch_url != 'nan' else '—')
        if ch_url and ch_url not in ('nan', '—', ''):
            c.hyperlink = ch_url; cel(c, fill=fill, link=True)
        else:
            cel(c, fill=fill)

        ws2.row_dimensions[row].height = 32

    for col, w in enumerate(
        [5, 32, 8, 10, 10, 16, 16, 18, 50, 12], 1
    ):
        ws2.column_dimensions[get_column_letter(col)].width = w

    # ── SHEET 3: SUMMARY ───────────────────────────────────────────────────
    ws3 = wb.create_sheet('Summary')
    ws3.sheet_view.showGridLines = False

    summary_data = [
        ('CLASSIFICATION SUMMARY', '', ''),
        ('Total firms in defence review', len(rows), ''),
        ('', '', ''),
        ('AUTO-CLASSIFIED (no manual review needed)', '', ''),
        ('Space peripheral — not space sector (aviation MRO etc)',
         len(auto_peripheral),
         f'{len(auto_peripheral)/len(rows)*100:.1f}%'),
        ('Defence primary — defence non-space',
         len(auto_defence),
         f'{len(auto_defence)/len(rows)*100:.1f}%'),
        ('Civil space confirmed — no defence signal',
         len(auto_civil),
         f'{len(auto_civil)/len(rows)*100:.1f}%'),
        ('', '', ''),
        ('MANUAL REVIEW REQUIRED', '', ''),
        ('Genuinely ambiguous — needs website check',
         len(manual_review),
         f'{len(manual_review)/len(rows)*100:.1f}%'),
        ('', '', ''),
        ('TIME SAVED', '', ''),
        ('Original manual review estimate',
         f'{len(rows)*0.5:.0f} mins', ''),
        ('After auto-classification',
         f'{len(manual_review)*0.5:.0f} mins', ''),
        ('Time saving',
         f'{(len(rows)-len(manual_review))*0.5:.0f} mins', ''),
    ]

    for i, (label, value, pct) in enumerate(summary_data):
        row = i + 2
        c1 = ws3.cell(row=row, column=1, value=label)
        c2 = ws3.cell(row=row, column=2, value=value)
        c3 = ws3.cell(row=row, column=3, value=pct)

        if 'SUMMARY' in str(label) or 'AUTO' in str(label) or \
           'MANUAL' in str(label) or 'TIME' in str(label):
            for c in [c1, c2, c3]:
                c.font = Font(name='Arial', bold=True, size=11,
                               color='1F3864')
                c.fill = BLUE
                c.font = HDR_F
        else:
            for c in [c1, c2, c3]:
                c.font = BODY_F
                c.fill = GREY if i % 2 == 0 else WHITE
        for c in [c1, c2, c3]:
            c.alignment = Alignment(horizontal='left', vertical='center')
            c.border = BDR
        ws3.row_dimensions[row].height = 25

    ws3.column_dimensions['A'].width = 55
    ws3.column_dimensions['B'].width = 15
    ws3.column_dimensions['C'].width = 10

    # Save
    wb.save(OUTPUT_PATH)

    print(f"\n{'='*65}")
    print("OUTPUT SAVED")
    print(f"{'='*65}")
    print(f"  {OUTPUT_PATH}")
    print(f"\n  Sheet 1 — Manual Review Required: {len(manual_review)} firms")
    print(f"  Sheet 2 — Auto-Classified: "
          f"{len(rows)-len(manual_review):,} firms")
    print(f"  Sheet 3 — Summary statistics")
    print(f"\nTime estimate:")
    print(f"  Auto-classified: {len(rows)-len(manual_review):,} firms "
          f"— no review needed")
    print(f"  Manual review:   {len(manual_review)} firms "
          f"— ~{len(manual_review)*0.5:.0f} minutes")
    print(f"\nAFTER COMPLETING MANUAL REVIEW:")
    print(f"  Run apply_pipeline_review.py")
    print(f"  (update REVIEW_PATH to point to this filtered file)")
    print("=" * 65)


if __name__ == "__main__":
    run()