"""Fix postcode_best for N6 firms that have postcode but not postcode_best"""
import pandas as pd
import re

PATH = "/Users/keerthanate/dissertation/data/firm_database_tableau.csv"
df = pd.read_csv(PATH, low_memory=False)

# For rows where postcode_best is empty but postcode exists
mask = (
    (df['postcode_best'].isna() | (df['postcode_best'].astype(str).isin(['', 'nan']))) &
    (df['postcode'].notna()) &
    (~df['postcode'].astype(str).isin(['', 'nan']))
)

df.loc[mask, 'postcode_best'] = df.loc[mask, 'postcode'].astype(str).str.strip()

# Also fix postcode_area for these
def get_area(pc):
    if not pc or str(pc) in ('nan', ''):
        return ''
    m = re.match(r'^([A-Z]{1,2})', str(pc).upper().strip())
    return m.group(1) if m else ''

df['postcode_area'] = df['postcode_best'].apply(get_area)

fixed = mask.sum()
print(f"Fixed postcode_best for {fixed} firms")

# Check N6 specifically
n6 = df[df['primary_node'] == 'N6']
print(f"\nN6 firms after fix:")
for _, r in n6.iterrows():
    print(f"  {r['company_name']}: postcode_best={r['postcode_best']}")

df.to_csv(PATH, index=False)
print(f"\nSaved: {PATH}")
print("Refresh Tableau to see N6 firms on the map")