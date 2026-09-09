import pandas as pd
import re
import os
from datetime import date

OUTPUT_DIR           = "/Users/keerthanate/dissertation/data"
PIPELINE_REVIEW_PATH = f"{OUTPUT_DIR}/pipeline_review.csv"
FINAL_PATH           = f"{OUTPUT_DIR}/firm_database_final.csv"
EXCLUDED_PATH        = f"{OUTPUT_DIR}/pipeline_excluded_defence.csv"
DATE_TODAY           = str(date.today())

NODE_LABELS = {
    'N1':'Components and Materials','N2':'Subsystems and Payloads',
    'N3':'Satellite and Spacecraft Manufacturing','N4':'Ground Segment',
    'N5':'Launch','N6':'Satellite Operations',
    'N7':'Data Processing and Analytics','N8':'Applications and Services',
    'N9':'Enabling and Ancillary',
}
CHAIN_MAP = {
    'N1':'Upstream','N2':'Upstream','N3':'Upstream',
    'N4':'Midstream','N5':'Midstream','N7':'Midstream',
    'N6':'Downstream','N8':'Downstream','N9':'Downstream',
}

SPACE_POSITIVE = [
    r'satellite',r'\bspace\b',r'spacecraft',r'orbital',
    r'cubesat',r'smallsat',r'nanosat',r'gnss',
    r'earth\s*obs',r'geospat',r'remote\s*sens',
    r'astro(?!nomy)',r'rocket',r'telemetry',r'satcom',
    r'spaceport',r'in.orbit',r'debris\s*remov',
    r'haps\b',r'stratospher',r'launcher',r'propellant',
]
DEFENCE_SIGNALS = [
    r'\bdefenc\b',r'\bdefens\b',r'\bmilitar\b',
    r'\bnato\b',r'\btactical\b',r'\bweapon\b',
    r'\bcombat\b',r'\bsigint\b',r'\bisr\b',
]

# Manual overrides — your 5 reviewed firms + known space firms
MANUAL_OVERRIDES = {
    'AXSCEND LIMITED':              ('No',  'Yes'),
    'BULK TAINER TELEMATICS LIMITED':('No', 'Yes'),
    'SCHIEBEL UK LIMITED':          ('Yes', 'Yes'),
    'STELLARCUBE LIMITED':          ('No',  ''),
    'TPI AEROSPACE LTD':            ('No',  'Yes'),
    'REACTION ENGINES LIMITED':     ('No',  ''),
    'REACTION ENGINES LTD':         ('No',  ''),
    'ORBEX LIMITED':                ('No',  ''),
    'ORBEX LTD':                    ('No',  ''),
    'SKYRORA LTD':                  ('No',  ''),
    'SKYRORA LIMITED':              ('No',  ''),
}

def classify(name, sic_code):
    name_l = str(name).lower()
    # Convert SIC code to clean string — handle float like 33160.0
    sic_clean = str(sic_code).replace('.0','').strip()
    sic_l     = name_l + ' ' + sic_clean

    has_space   = any(re.search(p, sic_l) for p in SPACE_POSITIVE)
    has_defence = any(re.search(p, name_l) for p in DEFENCE_SIGNALS)

    # These SIC codes cover BOTH aviation AND spacecraft
    # Default = peripheral unless positive space keyword confirmed
    # SIC 33160 = Repair and maintenance of aircraft AND spacecraft
    # SIC 30300 = Manufacture of air AND spacecraft and related machinery
    AVIATION_SPACE_SICS = {'33160', '30300', '51100', '51210'}

    is_aviation_sic = sic_clean in AVIATION_SPACE_SICS

    if has_defence and not has_space:
        return 'Yes', '', 'defence signal, no space keyword'

    if is_aviation_sic and not has_space:
        return '', 'Yes', f'SIC {sic_clean} — no space keyword — aviation default'

    if has_space and not has_defence:
        return 'No', '', 'space keyword confirmed'

    if has_space and has_defence:
        return 'Partial', '', 'space + defence dual-use'

    return '', 'Yes', 'no space keyword — exclude'

def run():
    print("="*65)
    print("Apply Pipeline Defence Review — Final")
    print(f"Date: {DATE_TODAY}")
    print("="*65)

    try:
        df_review = pd.read_csv(PIPELINE_REVIEW_PATH, low_memory=False)
        print(f"\nPipeline review firms: {len(df_review):,}")
    except FileNotFoundError:
        print("pipeline_review.csv not found"); return

    try:
        df_final = pd.read_csv(FINAL_PATH, low_memory=False)
        print(f"Final database: {len(df_final):,} firms")
    except FileNotFoundError:
        print("firm_database_final.csv not found"); return

    approved, excluded = [], []

    for _, row in df_review.iterrows():
        name     = str(row.get('company_name','')).strip()
        sic_code = str(row.get('matched_sic_code','')).strip()
        sic_text = str(row.get('sic_codes_full','') or
                       row.get('matched_sic_text','')).strip()

        if name in MANUAL_OVERRIDES:
            defence, peripheral = MANUAL_OVERRIDES[name]
            reason = 'manual review'
        else:
            defence, peripheral, reason = classify(name, sic_code)

        firm = row.to_dict()
        firm['defence_primary']       = defence
        firm['space_peripheral']      = peripheral
        firm['classification_reason'] = reason
        node = str(firm.get('primary_node',''))
        if not firm.get('chain_position'):
            firm['chain_position'] = CHAIN_MAP.get(node,'')

        if peripheral == 'Yes' or defence == 'Yes':
            excluded.append(firm)
        else:
            approved.append(firm)

    print(f"\nResults:")
    print(f"  Approved: {len(approved):,}")
    print(f"  Excluded: {len(excluded):,}")
    print(f"    peripheral=Yes: {sum(1 for f in excluded if f.get('space_peripheral')=='Yes'):,}")
    print(f"    defence=Yes:    {sum(1 for f in excluded if f.get('defence_primary')=='Yes'):,}")

    print(f"\nSample APPROVED:")
    for f in approved[:15]:
        print(f"  {f.get('company_name','')[:50]:<52} node={f.get('primary_node','')}")

    print(f"\nSample EXCLUDED:")
    for f in excluded[:10]:
        print(f"  {f.get('company_name','')[:50]:<52} reason={f.get('classification_reason','')[:40]}")

    # Deduplicate
    existing = set(df_final['company_number'].dropna().astype(str))
    df_new   = pd.DataFrame(approved) if approved else pd.DataFrame()
    if len(df_new):
        df_new = df_new[~df_new['company_number'].astype(str).isin(existing)]

    df_out = pd.concat([df_final, df_new], ignore_index=True)
    df_out['data_collection_date'] = DATE_TODAY

    print(f"\nFinal database: {len(df_out):,} firms")
    print(f"  ({len(df_final):,} existing + {len(df_new):,} added)")

    print(f"\nBy primary node:")
    for node in ['N1','N2','N3','N4','N5','N6','N7','N8','N9']:
        c = len(df_out[df_out['primary_node']==node])
        if c: print(f"  {node}  {NODE_LABELS.get(node,''):<42} {c:>5,}")

    print(f"\nBy chain position:")
    for pos in ['Upstream','Downstream','Enabling']:
        c = len(df_out[df_out['chain_position']==pos])
        if c: print(f"  {pos:<14} {c:>5,}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df_out.to_csv(FINAL_PATH, index=False)
    if excluded:
        pd.DataFrame(excluded).to_csv(EXCLUDED_PATH, index=False)

    print(f"\n{'='*65}")
    print("FILES SAVED")
    print(f"  {FINAL_PATH} → {len(df_out):,} firms")
    if excluded:
        print(f"  {EXCLUDED_PATH} → {len(excluded):,} excluded")
    print("="*65)

if __name__ == "__main__":
    run()