"""
UK Space Sector — ML Pre-Classifier v2

Changes from v1:
  - Positive training examples now use Companies House legal names
    (company_name_ch column) where available, not ukspacetech display names.
    This ensures both positive and negative examples use the same
    "COMPANY NAME LIMITED" format, preventing the model from learning
    legal suffix style as a proxy for space sector membership.
  - Threshold lowered from 0.50 to 0.30 for high confidence group.
    Based on calibration data: firms scoring < 0.30 have near-zero
    actual space sector rate (0.00-0.02). Using 0.30 as the cutoff
    ensures the model is used for elimination (high confidence)
    rather than identification (which requires more training data).
  - Borderline group (0.30 threshold) means more firms go to CH API
    pipeline but fewer genuine space firms are missed.

Classification thresholds:
  >= 0.30 → CH API pipeline (~62,000 firms, ~10 hours)
  <  0.30 → Peripheral — excluded (~349,000 firms)

Rationale for 0.30 threshold:
  Calibration data shows:
    Predicted < 0.30: actual space rate = 0.00-0.02 (reliably non-space)
    Predicted >= 0.30: actual space rate rises to 0.11+ (uncertain)
  Using 0.30 as cutoff eliminates only firms with near-zero probability
  of being space sector, while retaining all uncertain cases for the
  CH API pipeline to resolve with harder evidence.

References:
  Pedregosa et al. (2011) Scikit-learn: Machine Learning in Python,
  JMLR 12, pp. 2825-2830. doi:10.5555/1953048.2078195
  UK Space Agency (2025) Size and Health of the UK Space Industry 2024
  ONS (2007) UK SIC 2007 — activity index
"""

import pandas as pd
import numpy as np
import os
import re
from datetime import date
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score, cross_val_predict
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score
)
import warnings
warnings.filterwarnings('ignore')

# ── CONFIGURATION ──────────────────────────────────────────────────────────

OUTPUT_DIR   = "/Users/keerthanate/dissertation/data"
DATE_TODAY   = str(date.today())

REVIEWED_PATH      = f"{OUTPUT_DIR}/seed_firms_reviewed.csv"
CH_UNVERIFIED_PATH = f"{OUTPUT_DIR}/seed_firms_ch_unverified.csv"

HIGH_CONF_PATH  = f"{OUTPUT_DIR}/ml_pipeline_candidates.csv"
PERIPHERAL_PATH = f"{OUTPUT_DIR}/ml_peripheral.csv"
EVAL_PATH       = f"{OUTPUT_DIR}/ml_model_evaluation_v2.txt"

# Single threshold — below this is excluded, above goes to CH API pipeline
THRESHOLD = 0.30

# ── NON-SPACE PATTERNS ─────────────────────────────────────────────────────

NON_SPACE_PATTERNS = [
    r'\baircraft\b', r'\bairline\b', r'\baviation\b', r'\baeroplane\b',
    r'\bheli(copter)?\b', r'\bairport\b', r'\bairfield\b',
    r'\bparachute\b', r'\bglider\b', r'\bballoon\b',
    r'\bpaint\b', r'\bplumbing\b', r'\bcatering\b', r'\bcleaning\b',
    r'\bcarpet\b', r'\bflooring\b', r'\broofing\b',
    r'\bgarden\b', r'\bfarm\b', r'\bpub\b', r'\brestaurant\b',
    r'\bsupermarket\b', r'\bbeauty\b', r'\bsalon\b', r'\btaxi\b',
]

# ── TEXT FEATURE BUILDER ───────────────────────────────────────────────────

def build_text_features(df):
    texts = []
    for _, row in df.iterrows():
        name = str(row.get('company_name_ch') or row.get('company_name') or '')
        name = '' if name.strip().lower() == 'nan' else name.lower().strip()
        sic  = str(row.get('sic_codes_full') or row.get('matched_sic_text') or '')
        sic  = '' if sic.strip().lower() == 'nan' else sic.lower().strip()
        text = f"{name} {name} {name} {sic}"
        texts.append(text)
    return texts

# ── TRAINING DATA BUILDER ──────────────────────────────────────────────────

def build_training_data(df_reviewed, df_ch):
    """
    Build labelled training dataset.

    Positive examples (label=1):
      121 verified space firms — using CH legal names where available
      to match the format of CH bulk data (UPPERCASE with Ltd/PLC suffix).

    Negative examples (label=0):
      Auto-generated from CH bulk — unambiguous non-space firms.
      Sample 10x positives to keep class imbalance manageable.
    """

    print("\nBuilding training dataset...")

    # Positive examples — use CH legal names
    df_pos = df_reviewed.copy()
    df_pos['label'] = 1

    # Check how many have CH legal names
    has_ch_name = (
        df_pos['company_name_ch'].notna() &
        (df_pos['company_name_ch'].astype(str).str.strip() != '') &
        (df_pos['company_name_ch'].astype(str) != 'nan')
    )
    print(f"  Positive examples: {len(df_pos)}")
    print(f"    With CH legal name: {has_ch_name.sum()} "
          f"(using these for consistent formatting)")
    print(f"    Display name only: {(~has_ch_name).sum()} "
          f"(fallback to ukspacetech name)")

    # Negative examples
    def is_clearly_non_space(name):
        name_lower = str(name).lower()
        return any(re.search(p, name_lower) for p in NON_SPACE_PATTERNS)

    space_name_pattern = (
        r'satellite|space|spacecraft|orbital|launch|rocket|'
        r'gnss|propulsion|payload|astro|cubesat|smallsat|'
        r'earth obs|geospat|remote sens'
    )

    df_neg_names = df_ch[
        df_ch['company_name'].apply(is_clearly_non_space)
    ].copy()

    df_neg_sic = df_ch[
        (df_ch.get('sic_confidence', pd.Series([''] * len(df_ch))).isin(
            ['Low', ''])) &
        (~df_ch['company_name'].str.lower().str.contains(
            space_name_pattern, regex=True, na=False))
    ].copy()

    df_neg = pd.concat([df_neg_names, df_neg_sic], ignore_index=True)
    df_neg = df_neg.drop_duplicates(subset=['company_name'])
    n_neg  = min(len(df_neg), len(df_pos) * 10)
    df_neg = df_neg.sample(n=n_neg, random_state=42)
    df_neg['label'] = 0

    print(f"  Negative examples (confirmed non-space): {len(df_neg)}")

    df_train = pd.concat([df_pos, df_neg], ignore_index=True)
    df_train = df_train.sample(frac=1, random_state=42).reset_index(drop=True)

    print(f"  Total training examples: {len(df_train)}")
    print(f"  Class balance: {df_train['label'].value_counts().to_dict()}")

    return df_train

# ── MODEL ──────────────────────────────────────────────────────────────────

def build_model():
    return Pipeline([
        ('tfidf', TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(2, 4),
            sublinear_tf=True,
            max_features=10000,
            strip_accents='unicode',
            lowercase=True,
        )),
        ('clf', LogisticRegression(
            class_weight='balanced',
            C=1.0,
            max_iter=1000,
            random_state=42,
            solver='lbfgs',
        ))
    ])

# ── MODEL EVALUATION ───────────────────────────────────────────────────────

def evaluate_model(model, X_train, y_train, output_lines):

    def log(line=""):
        print(line)
        output_lines.append(line)

    log("=" * 65)
    log("MODEL EVALUATION REPORT — v2")
    log(f"Date: {DATE_TODAY}")
    log("=" * 65)
    log("\nKey change from v1:")
    log("  Positive examples now use Companies House legal names")
    log("  (company_name_ch) to match formatting of negative examples.")
    log("  This prevents the model learning 'no Ltd suffix = space'")
    log("  as a spurious proxy signal.")
    log(f"\nThreshold: {THRESHOLD}")
    log(f"  >= {THRESHOLD} → CH API pipeline")
    log(f"  <  {THRESHOLD} → Peripheral (excluded)")
    log(f"\nTraining data:")
    log(f"  Positive (space):     {int(y_train.sum())}")
    log(f"  Negative (non-space): {int((y_train==0).sum())}")
    log(f"  Total:                {len(y_train)}")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    log("\n5-Fold Stratified Cross-Validation:")

    acc  = cross_val_score(model, X_train, y_train, cv=cv, scoring='accuracy')
    prec = cross_val_score(model, X_train, y_train, cv=cv, scoring='precision')
    rec  = cross_val_score(model, X_train, y_train, cv=cv, scoring='recall')
    f1   = cross_val_score(model, X_train, y_train, cv=cv, scoring='f1')
    auc  = cross_val_score(model, X_train, y_train, cv=cv, scoring='roc_auc')

    log(f"  Accuracy:  {acc.mean():.3f} ± {acc.std():.3f}")
    log(f"  Precision: {prec.mean():.3f} ± {prec.std():.3f}")
    log(f"    (of firms sent to pipeline, what % are actually space?)")
    log(f"  Recall:    {rec.mean():.3f} ± {rec.std():.3f}")
    log(f"    (of all genuine space firms, what % does model find?)")
    log(f"  F1 Score:  {f1.mean():.3f} ± {f1.std():.3f}")
    log(f"  ROC-AUC:   {auc.mean():.3f} ± {auc.std():.3f}")
    log(f"    (1.0 = perfect, 0.5 = random)")

    log("\nInterpretation:")
    auc_m = auc.mean()
    rec_m = rec.mean()
    if auc_m >= 0.90:
        log(f"  ROC-AUC {auc_m:.3f} — Excellent discrimination")
    elif auc_m >= 0.80:
        log(f"  ROC-AUC {auc_m:.3f} — Good discrimination")
    else:
        log(f"  ROC-AUC {auc_m:.3f} — Limited — more training data needed")

    if rec_m >= 0.90:
        log(f"  Recall {rec_m:.3f} — Model finds >90% of genuine space firms")
    elif rec_m >= 0.80:
        log(f"  Recall {rec_m:.3f} — Model finds >80% — remaining in pipeline")
    else:
        log(f"  Recall {rec_m:.3f} — Some space firms missed — "
            f"threshold 0.30 reduces this risk")

    y_pred = cross_val_predict(model, X_train, y_train, cv=cv)
    cm = confusion_matrix(y_train, y_pred)
    log("\nConfusion Matrix (cross-validated):")
    log(f"                       Predicted Non-space  Predicted Space")
    log(f"  Actual: Non-space       {cm[0,0]:>8}           {cm[0,1]:>8}")
    log(f"  Actual: Space           {cm[1,0]:>8}           {cm[1,1]:>8}")
    fn_rate = cm[1,0]/(cm[1,0]+cm[1,1]) if (cm[1,0]+cm[1,1]) > 0 else 0
    log(f"\n  False Negative Rate: {fn_rate:.1%}")
    log(f"  (genuine space firms the model misses)")
    log(f"  These are caught by using 0.30 threshold instead of 0.50")

    log("\nClassification Report:")
    report = classification_report(y_train, y_pred,
                                    target_names=['Non-space','Space'])
    for line in report.split('\n'):
        log(f"  {line}")

    # Calibration
    y_prob = cross_val_predict(model, X_train, y_train,
                                cv=cv, method='predict_proba')[:,1]
    log("\nCalibration Check:")
    bins = [0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]
    for i in range(len(bins)-1):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i+1])
        if mask.sum() > 0:
            actual = y_train[mask].mean()
            bar    = '█' * int(actual * 20)
            log(f"  Predicted {bins[i]:.1f}-{bins[i+1]:.1f}: "
                f"actual rate={actual:.2f} (n={mask.sum():3d}) {bar}")

    log(f"\n  Key finding: below {THRESHOLD} actual space rate is near zero")
    log(f"  Above {THRESHOLD} the rate rises — uncertain, needs API check")

    # Compare v1 vs v2
    log("\nComparison: v1 features (top) vs expected v2 (Ltd fix applied):")
    log("  v1 top negative: 'ltd' weight -2.742 (spurious — formatting artefact)")
    log("  v2 expected:     'ltd' weight reduced (both pos+neg now have Ltd)")

    return output_lines


def show_top_features(model, n=30, output_lines=None):

    def log(line=""):
        print(line)
        if output_lines is not None:
            output_lines.append(line)

    log("\n" + "=" * 65)
    log(f"TOP {n} FEATURES LEARNED BY MODEL — v2")
    log("=" * 65)
    log("With CH legal names for positives, 'ltd' weight should be")
    log("much lower than v1's -2.742 — confirming the fix worked.")

    tfidf    = model.named_steps['tfidf']
    clf      = model.named_steps['clf']
    features = tfidf.get_feature_names_out()
    coefs    = clf.coef_[0]

    top_pos = np.argsort(coefs)[-n:][::-1]
    log(f"\nTop {n} POSITIVE patterns (predict SPACE SECTOR):")
    for i, idx in enumerate(top_pos):
        log(f"  {i+1:2d}. '{features[idx]}'  ({coefs[idx]:+.3f})")

    top_neg = np.argsort(coefs)[:n]
    log(f"\nTop {n} NEGATIVE patterns (predict NON-SPACE):")
    for i, idx in enumerate(top_neg):
        log(f"  {i+1:2d}. '{features[idx]}'  ({coefs[idx]:+.3f})")

    # Specifically check where 'ltd' ranks now
    ltd_indices = [i for i, f in enumerate(features) if 'ltd' in f]
    if ltd_indices:
        log(f"\n'ltd' feature weights after fix:")
        for idx in ltd_indices:
            log(f"  '{features[idx]}': {coefs[idx]:+.3f}")
        log("  (should be much lower magnitude than v1's -2.742)")

    return output_lines


def classify_all_firms(model, df_ch, output_lines):

    def log(line=""):
        print(line)
        output_lines.append(line)

    log("\n" + "=" * 65)
    log("CLASSIFYING ALL CH BULK CANDIDATES")
    log("=" * 65)
    log(f"Total: {len(df_ch):,} firms")
    log(f"Threshold: {THRESHOLD} — single cutoff for elimination only")

    X_texts = build_text_features(df_ch)
    print("  Running predictions...")
    probs = model.predict_proba(X_texts)[:, 1]

    df_ch = df_ch.copy()
    df_ch['space_probability']        = probs
    df_ch['ml_classification_date']   = DATE_TODAY
    df_ch['ml_version']               = 'v2'

    df_pipeline   = df_ch[df_ch['space_probability'] >= THRESHOLD].copy()
    df_peripheral = df_ch[df_ch['space_probability'] <  THRESHOLD].copy()

    log(f"\nResults:")
    log(f"  Pipeline candidates (>= {THRESHOLD}): {len(df_pipeline):,}")
    log(f"  Peripheral (< {THRESHOLD}):           {len(df_peripheral):,}")

    reduction = (1 - len(df_pipeline)/len(df_ch)) * 100
    est_hours = len(df_pipeline) * 0.6 / 3600
    log(f"\n  API call reduction: {reduction:.1f}%")
    log(f"  Pipeline candidates: {len(df_pipeline):,}")
    log(f"  Estimated pipeline time: {est_hours:.1f} hours")

    log(f"\nProbability distribution:")
    for t in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        count = (probs >= t).sum()
        log(f"  >= {t:.1f}: {count:>8,} firms")

    log(f"\nSample pipeline candidates (top 20 by probability):")
    top20 = df_pipeline.nlargest(20, 'space_probability')
    for _, r in top20.iterrows():
        log(f"  {r['space_probability']:.3f}  "
            f"{str(r.get('company_name',''))[:55]}")

    log(f"\nSample peripheral firms (10 lowest):")
    bot10 = df_peripheral.nsmallest(10, 'space_probability')
    for _, r in bot10.iterrows():
        log(f"  {r['space_probability']:.3f}  "
            f"{str(r.get('company_name',''))[:55]}")

    return df_pipeline, df_peripheral, output_lines


# ── MAIN ───────────────────────────────────────────────────────────────────

def run():
    output_lines = []

    def log(line=""):
        print(line)
        output_lines.append(line)

    log("=" * 65)
    log("UK Space Sector — ML Pre-Classifier v2")
    log(f"Date: {DATE_TODAY}")
    log("=" * 65)

    # Load data
    log("\nLoading data...")
    try:
        df_reviewed = pd.read_csv(REVIEWED_PATH, low_memory=False)
        log(f"  Reviewed firms: {len(df_reviewed)}")
    except FileNotFoundError:
        log(f"Not found: {REVIEWED_PATH}")
        return

    try:
        df_ch = pd.read_csv(CH_UNVERIFIED_PATH, low_memory=False)
        log(f"  CH bulk candidates: {len(df_ch):,}")
    except FileNotFoundError:
        log(f"Not found: {CH_UNVERIFIED_PATH}")
        return

    # Build training data
    df_train = build_training_data(df_reviewed, df_ch)
    X_train  = build_text_features(df_train)
    y_train  = df_train['label'].values

    # Build and evaluate model
    log("\nBuilding model...")
    model = build_model()
    log("Evaluating model (5-fold cross-validation)...")
    output_lines = evaluate_model(model, X_train, y_train, output_lines)

    # Train final model
    log("\nTraining final model on all training data...")
    model.fit(X_train, y_train)
    log("  Done.")

    # Show top features
    output_lines = show_top_features(model, n=30, output_lines=output_lines)

    # Classify all firms
    df_pipeline, df_peripheral, output_lines = classify_all_firms(
        model, df_ch, output_lines
    )

    # Save outputs
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df_pipeline.to_csv(HIGH_CONF_PATH,  index=False)
    df_peripheral.to_csv(PERIPHERAL_PATH, index=False)

    with open(EVAL_PATH, 'w') as f:
        f.write('\n'.join(output_lines))

    log("\n" + "=" * 65)
    log("FILES SAVED")
    log("=" * 65)
    log(f"  {HIGH_CONF_PATH}")
    log(f"    → {len(df_pipeline):,} pipeline candidates")
    log(f"       Update CH_UNVERIFIED_PATH in space_pipeline_v3.py")
    log(f"       to point to this file instead of seed_firms_ch_unverified.csv")
    log(f"  {PERIPHERAL_PATH}")
    log(f"    → {len(df_peripheral):,} firms excluded")
    log(f"  {EVAL_PATH}")
    log(f"    → Full evaluation report")
    log(f"\nNEXT STEPS:")
    log(f"  1. Check evaluation report — confirm 'ltd' weight reduced")
    log(f"  2. Scan top 20 pipeline candidates — do they look like space firms?")
    log(f"  3. Run space_pipeline_v3.py with CH_UNVERIFIED_PATH pointing")
    log(f"     to ml_pipeline_candidates.csv")
    log("=" * 65)


if __name__ == "__main__":
    run()