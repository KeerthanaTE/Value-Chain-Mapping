import pandas as pd

PATH = "/Users/keerthanate/dissertation/data/firm_database_tableau.csv"
df = pd.read_csv(PATH, low_memory=False)

# Pipeline verified firms that passed all filters are civil by default
# They were not flagged requires_defence_check=Yes
# So they cleared the defence screen — assign No
mask = (
    (df['defence_primary'].isna() | (df['defence_primary'] == '')) &
    (df['pipeline_status'] == 'verified')
)
df.loc[mask, 'defence_primary'] = 'No'

# Update defence_label
df['defence_label'] = df['defence_primary'].map({
    'No':      'Civil / Commercial',
    'Partial': 'Dual-Use (Civil + Defence)',
    'Yes':     'Defence Primary',
}).fillna('Not assessed')

print(f"Updated: {mask.sum()} firms")
print(df['defence_label'].value_counts())

df.to_csv(PATH, index=False)
print("Saved")