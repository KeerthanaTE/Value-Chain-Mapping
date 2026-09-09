"""
UK Space Sector — Defence and Node Review Sheet Generator

Reads the merged firm database and produces a structured Excel review sheet
for manual assessment of:
  1. Defence status (defence_primary: Yes / Partial / No)
  2. Node correction (primary_node and secondary_node)

Review is done in phases by confidence level:
  Phase A — High confidence (appears in both sources) — review all
  Phase B — Medium confidence (Source 2 only) — review all
  Phase C — Low confidence (Source 1 only) — review after Stage 3 pipeline

Usage:
  1. Run this script to generate the review sheet
  2. Open the Excel file
  3. For each firm, visit the website link and Companies House link
  4. Fill in the yellow cells: defence_primary, primary_node_confirmed,
     secondary_node, evidence_notes
  5. Run apply_review.py to merge your assessments back into the database

Output:
  data/review_sheet.xlsx  — two sheets (Phase A and Phase B)
"""

import pandas as pd
import openpyxl
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side
)
from openpyxl.utils import get_column_letter
import os
from datetime import date

MERGED_PATH  = "/Users/keerthanate/dissertation/data/seed_firms_merged.csv"
OUTPUT_DIR   = "/Users/keerthanate/dissertation/data"
DATE_TODAY   = str(date.today())

# ── COLOURS ────────────────────────────────────────────────────────────────
NAVY       = PatternFill('solid', fgColor='1F3864')
BLUE       = PatternFill('solid', fgColor='2E75B6')
YELLOW     = PatternFill('solid', fgColor='FFD700')   # cells to fill in
GREEN      = PatternFill('solid', fgColor='E2EFDA')   # confirmed civil
ORANGE     = PatternFill('solid', fgColor='FCE4D6')   # requires check
GREY_ALT   = PatternFill('solid', fgColor='F2F2F2')
WHITE      = PatternFill('solid', fgColor='FFFFFF')

HDR_FONT   = Font(name='Arial', bold=True, color='FFFFFF', size=10)
BODY_FONT  = Font(name='Arial', size=10)
BOLD_FONT  = Font(name='Arial', bold=True, size=10)
LINK_FONT  = Font(name='Arial', size=10, color='0563C1', underline='single')
INPUT_FONT = Font(name='Arial', bold=True, size=10, color='000080')

thin  = Side(style='thin',   color='BFBFBF')
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def style_header(cell, fill=None):
    cell.font      = HDR_FONT
    cell.fill      = fill or NAVY
    cell.alignment = Alignment(horizontal='center', vertical='center',
                                wrap_text=True)
    cell.border    = BORDER


def style_cell(cell, fill=None, bold=False, center=False, link=False):
    cell.font      = LINK_FONT if link else (BOLD_FONT if bold else BODY_FONT)
    cell.fill      = fill or WHITE
    cell.alignment = Alignment(horizontal='center' if center else 'left',
                                vertical='center', wrap_text=True)
    cell.border    = BORDER


def style_input(cell):
    """Yellow input cell — this is what the reviewer fills in."""
    cell.font      = INPUT_FONT
    cell.fill      = YELLOW
    cell.alignment = Alignment(horizontal='left', vertical='center',
                                wrap_text=True)
    cell.border    = BORDER


def set_col_width(ws, col, width):
    ws.column_dimensions[get_column_letter(col)].width = width


def build_review_sheet(ws, df_phase, phase_name, phase_desc):
    """Build one review sheet for a given phase."""

    ws.sheet_view.showGridLines = False

    # ── TITLE ──────────────────────────────────────────────────────────────
    ws.merge_cells('A1:L1')
    ws['A1'] = f'UK Space Sector — Firm Review Sheet: {phase_name}'
    ws['A1'].font      = Font(name='Arial', bold=True, size=14,
                              color='1F3864')
    ws['A1'].alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 28

    ws.merge_cells('A2:L2')
    ws['A2'] = phase_desc
    ws['A2'].font      = Font(name='Arial', italic=True, size=10,
                              color='595959')
    ws['A2'].alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[2].height = 18

    ws.merge_cells('A3:L3')
    ws['A3'] = (
        f'Instructions: For each firm, open the Website and CH Profile links. '
        f'Fill in the YELLOW cells. '
        f'defence_primary: Yes=primarily defence | Partial=mixed | No=civil/commercial primary. '
        f'Leave node_confirmed blank if current assignment is correct.'
    )
    ws['A3'].font      = Font(name='Arial', size=9, color='7F7F7F')
    ws['A3'].alignment = Alignment(horizontal='left', vertical='center',
                                    wrap_text=True)
    ws.row_dimensions[3].height = 30

    ws.row_dimensions[4].height = 6

    # ── COLUMN HEADERS ─────────────────────────────────────────────────────
    headers = [
        '#',
        'Company Name',
        'Current Node',
        'Node Label',
        'Current Secondary',
        'SIC / Category',
        'Description',
        'Website',
        'CH Profile',
        'defence_primary\n(fill in)',
        'node_confirmed\n(fill in if different)',
        'secondary_node\n(fill in if applicable)',
        'evidence_notes\n(fill in — what you found)',
    ]

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=h)
        style_header(cell)
    ws.row_dimensions[5].height = 35

    ws.freeze_panes = 'A6'

    # ── DATA ROWS ──────────────────────────────────────────────────────────
    for i, (_, row) in enumerate(df_phase.iterrows()):
        r = i + 6

        needs_defence_check = str(row.get('requires_defence_check','')).strip() == 'Yes'
        fill = ORANGE if needs_defence_check else GREY_ALT if i % 2 == 0 else WHITE

        # Col 1 — row number
        cell = ws.cell(row=r, column=1, value=i + 1)
        style_cell(cell, fill=fill, center=True)

        # Col 2 — company name
        cell = ws.cell(row=r, column=2, value=row.get('company_name',''))
        style_cell(cell, fill=fill, bold=True)

        # Col 3 — current primary node
        cell = ws.cell(row=r, column=3, value=row.get('primary_node',''))
        style_cell(cell, fill=fill, center=True)

        # Col 4 — node label
        cell = ws.cell(row=r, column=4, value=row.get('node_label',''))
        style_cell(cell, fill=fill)

        # Col 5 — current secondary node
        cell = ws.cell(row=r, column=5,
                       value=row.get('secondary_node','') or '—')
        style_cell(cell, fill=fill, center=True)

        # Col 6 — SIC or ukspacetech category
        sic_cat = (
            row.get('ukspacetech_category','') or
            row.get('matched_sic_code','') + ' ' +
            str(row.get('matched_sic_text',''))[:40]
        )
        cell = ws.cell(row=r, column=6, value=str(sic_cat)[:60])
        style_cell(cell, fill=fill)

        # Col 7 — description
        desc = str(row.get('description',''))[:120]
        cell = ws.cell(row=r, column=7, value=desc or '—')
        style_cell(cell, fill=fill)

        # Col 8 — website (as hyperlink)
        website = str(row.get('website',''))
        cell = ws.cell(row=r, column=8, value=website or '—')
        if website and website != 'nan':
            cell.hyperlink = website
            style_cell(cell, fill=fill, link=True)
        else:
            style_cell(cell, fill=fill)

        # Col 9 — Companies House profile link
        uri = str(row.get('uri',''))
        ch_num = str(row.get('company_number',''))
        if not uri or uri == 'nan':
            if ch_num and ch_num != 'nan':
                uri = f"https://find-and-update.company-information.service.gov.uk/company/{ch_num}"
        cell = ws.cell(row=r, column=9, value='CH Profile' if uri else '—')
        if uri and uri != 'nan':
            cell.hyperlink = uri
            style_cell(cell, fill=fill, link=True)
        else:
            style_cell(cell, fill=fill)

        # Col 10 — defence_primary INPUT CELL
        cell = ws.cell(row=r, column=10, value='')
        style_input(cell)

        # Col 11 — node_confirmed INPUT CELL
        cell = ws.cell(row=r, column=11, value='')
        style_input(cell)

        # Col 12 — secondary_node INPUT CELL
        cell = ws.cell(row=r, column=12, value='')
        style_input(cell)

        # Col 13 — evidence_notes INPUT CELL
        cell = ws.cell(row=r, column=13, value='')
        style_input(cell)

        ws.row_dimensions[r].height = 40

    # ── COLUMN WIDTHS ──────────────────────────────────────────────────────
    set_col_width(ws, 1,  5)
    set_col_width(ws, 2,  32)
    set_col_width(ws, 3,  10)
    set_col_width(ws, 4,  28)
    set_col_width(ws, 5,  12)
    set_col_width(ws, 6,  30)
    set_col_width(ws, 7,  35)
    set_col_width(ws, 8,  28)
    set_col_width(ws, 9,  12)
    set_col_width(ws, 10, 16)
    set_col_width(ws, 11, 18)
    set_col_width(ws, 12, 16)
    set_col_width(ws, 13, 40)


def add_legend_sheet(wb):
    """Add a legend sheet explaining what to fill in."""
    ws = wb.create_sheet('Legend')
    ws.sheet_view.showGridLines = False

    ws.merge_cells('A1:D1')
    ws['A1'] = 'Review Sheet — Legend and Instructions'
    ws['A1'].font = Font(name='Arial', bold=True, size=14, color='1F3864')
    ws['A1'].alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 28

    rows = [
        ('YELLOW CELLS — what to fill in', '', '', ''),
        ('defence_primary', 'Yes',
         'Defence is the primary business — civil space is incidental or absent',
         'Firm will be EXCLUDED from final database'),
        ('defence_primary', 'Partial',
         'Genuine mix — civil space is significant alongside defence',
         'Firm will be INCLUDED with dual-use flag'),
        ('defence_primary', 'No',
         'Civil or commercial space is the primary business',
         'Firm will be INCLUDED'),
        ('node_confirmed', 'e.g. N3',
         'Leave BLANK if current node assignment is correct. '
         'Fill in only if you are changing the node based on website evidence.',
         'Use N1 through N9'),
        ('secondary_node', 'e.g. N6',
         'Fill in if firm operates across two nodes — '
         'e.g. builds satellites (N3) AND operates them (N6)',
         'Use N1 through N9 or leave blank'),
        ('evidence_notes', 'Free text',
         'Brief note on what you found — e.g. '
         '"Homepage says defence prime, no civil space products listed" or '
         '"About page confirms commercial EO satellite operator"',
         'Required for all defence_primary=Yes or Partial assessments'),
        ('', '', '', ''),
        ('NODE REFERENCE', '', '', ''),
        ('N1', 'Components and Materials',
         'Raw components, electronics, specialist materials',
         'Upstream'),
        ('N2', 'Subsystems and Payloads',
         'Functional subsystems — propulsion, ADCS, payloads, instruments',
         'Upstream'),
        ('N3', 'Satellite and Spacecraft Manufacturing',
         'Full satellite/spacecraft integration, AIT',
         'Upstream'),
        ('N4', 'Ground Segment',
         'Ground station hardware, TT&C systems, mission control',
         'Upstream'),
        ('N5', 'Launch',
         'Launch vehicles, launch services, spaceports',
         'Upstream'),
        ('N6', 'Satellite Operations',
         'Satellite fleet management, in-orbit servicing, SSA',
         'Downstream'),
        ('N7', 'Data Processing and Analytics',
         'EO data processing, analytics platforms, data products',
         'Downstream'),
        ('N8', 'Applications and Services',
         'End-user satcoms, DTH, navigation apps, EO services',
         'Downstream'),
        ('N9', 'Enabling and Ancillary',
         'Insurance, legal, R&D, engineering consultancy, market intel',
         'Enabling'),
        ('', '', '', ''),
        ('ORANGE ROWS', '',
         'Firms flagged requires_defence_check=Yes (SIC codes confirmed by '
         'ONS SIC 2026 to contain both civilian and military manufacturers). '
         'These must be assessed first.',
         ''),
        ('WHITE/GREY ROWS', '',
         'Firms not flagged for defence check — still review node assignment.',
         ''),
    ]

    fills = {
        'YELLOW CELLS — what to fill in': BLUE,
        'NODE REFERENCE': BLUE,
        'ORANGE ROWS': NAVY,
        'WHITE/GREY ROWS': NAVY,
    }

    for i, (col1, col2, col3, col4) in enumerate(rows):
        row = i + 3
        for col, val in enumerate([col1, col2, col3, col4], 1):
            cell = ws.cell(row=row, column=col, value=val)
            f = fills.get(col1)
            if f:
                cell.fill = f
                cell.font = HDR_FONT
            else:
                cell.font = BODY_FONT
                cell.fill = GREY_ALT if i % 2 == 0 else WHITE
            cell.alignment = Alignment(horizontal='left', vertical='center',
                                        wrap_text=True)
            cell.border = BORDER
        ws.row_dimensions[row].height = 35

    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 55
    ws.column_dimensions['D'].width = 20


def run():
    print("=" * 65)
    print("Defence and Node Review Sheet Generator")
    print(f"Date: {DATE_TODAY}")
    print("=" * 65)

    # Load merged CSV
    print(f"\nLoading: {MERGED_PATH}")
    try:
        df = pd.read_csv(MERGED_PATH, low_memory=False)
    except FileNotFoundError:
        print("Merged CSV not found — run merge_sources.py first")
        return

    print(f"Total firms: {len(df):,}")

    # Phase A — High confidence (both sources)
    df_a = df[df['confidence_level'] == 'High'].copy().reset_index(drop=True)

    # Phase B — Medium confidence (Source 2 only)
    df_b = df[df['confidence_level'] == 'Medium'].copy().reset_index(drop=True)

    # Phase C — Low confidence (Source 1 only) — excluded from review sheet
    # These are reviewed after Stage 3 pipeline narrows them down
    df_c_count = len(df[df['confidence_level'] == 'Low'])

    print(f"\nPhase A (High confidence — both sources): {len(df_a):,} firms")
    print(f"Phase B (Medium confidence — Source 2 only): {len(df_b):,} firms")
    print(f"Phase C (Low confidence — Source 1 only): {df_c_count:,} firms")
    print(f"  Phase C excluded from review sheet — reviewed after")
    print(f"  Stage 3 pipeline narrows the Source 1 candidate pool")

    # Build workbook
    wb = openpyxl.Workbook()

    # Phase A sheet
    ws_a = wb.active
    ws_a.title = 'Phase A — High Confidence'
    build_review_sheet(
        ws_a, df_a,
        'Phase A — High Confidence',
        (f'{len(df_a)} firms appearing in BOTH Companies House Bulk (Source 1) '
         f'AND ukspacetech.com (Source 2). These are your highest confidence '
         f'space sector participants. Review ALL firms in this sheet.')
    )

    # Phase B sheet
    ws_b = wb.create_sheet('Phase B — Medium Confidence')
    build_review_sheet(
        ws_b, df_b,
        'Phase B — Medium Confidence',
        (f'{len(df_b)} firms from ukspacetech.com (Source 2) only — not matched '
         f'to Companies House Bulk. These are verified space firms but may use '
         f'different legal names or file under unexpected SIC codes. '
         f'Review ALL firms in this sheet.')
    )

    # Legend sheet
    add_legend_sheet(wb)

    # Save
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = f"{OUTPUT_DIR}/review_sheet.xlsx"
    wb.save(output_path)

    print(f"\n{'='*65}")
    print("REVIEW SHEET SAVED")
    print(f"{'='*65}")
    print(f"  {output_path}")
    print(f"\nSheets:")
    print(f"  Phase A — High Confidence  ({len(df_a):,} firms)")
    print(f"  Phase B — Medium Confidence ({len(df_b):,} firms)")
    print(f"  Legend — instructions and node reference")
    print(f"\nORANGE rows = firms flagged requires_defence_check=Yes")
    print(f"YELLOW cells = fill these in for each firm")
    print(f"\nAfter completing the review:")
    print(f"  → Run apply_review.py to merge assessments into database")


if __name__ == "__main__":
    run()