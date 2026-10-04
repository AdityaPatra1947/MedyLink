"""Create the learning guide from the completed, measured ML evaluation."""
import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Render the learning guide from an aggregate evaluation report.')
parser.add_argument('--report', type=Path, default=ROOT / 'ml/reports/evaluation.json')
args = parser.parse_args()
REPORT = json.loads(args.report.read_text(encoding='utf-8-sig'))
OUT = ROOT / 'output/pdf/MedyLink_ML_Explained.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
FONT = Path('C:/Windows/Fonts')
pdfmetrics.registerFont(TTFont('Guide', str(FONT / 'segoeui.ttf')))
pdfmetrics.registerFont(TTFont('GuideBold', str(FONT / 'segoeuib.ttf')))
pdfmetrics.registerFontFamily('Guide', normal='Guide', bold='GuideBold', italic='Guide', boldItalic='GuideBold')
TEAL = colors.HexColor('#126B5B')
INK = colors.HexColor('#163A3A')
MUTED = colors.HexColor('#526767')
PALE = colors.HexColor('#EFF6F2')
GOLD = colors.HexColor('#AD6A18')
styles = {
    'eyebrow': ParagraphStyle('eyebrow', fontName='GuideBold', fontSize=9, leading=13, textColor=TEAL, spaceAfter=8),
    'title': ParagraphStyle('title', fontName='GuideBold', fontSize=29, leading=35, textColor=INK, spaceAfter=12),
    'h1': ParagraphStyle('h1', fontName='GuideBold', fontSize=21, leading=27, textColor=INK, spaceAfter=12),
    'h2': ParagraphStyle('h2', fontName='GuideBold', fontSize=12, leading=17, textColor=TEAL, spaceBefore=12, spaceAfter=5),
    'body': ParagraphStyle('body', fontName='Guide', fontSize=10, leading=15, textColor=INK, spaceAfter=8),
    'small': ParagraphStyle('small', fontName='Guide', fontSize=8.5, leading=12, textColor=MUTED, spaceAfter=5),
    'cell': ParagraphStyle('cell', fontName='Guide', fontSize=9, leading=13, textColor=INK),
    'head': ParagraphStyle('head', fontName='GuideBold', fontSize=9, leading=13, textColor=colors.white),
    'code': ParagraphStyle('code', fontName='Courier', fontSize=8, leading=12, textColor=INK, backColor=PALE, borderPadding=8, spaceAfter=10),
}
story = []

def p(text, style='body'):
    return Paragraph(text, styles[style])

def add(text, style='body'):
    story.append(p(text, style))

def section(number, title):
    if story:
        story.append(PageBreak())
    add(f'MEDYLINK / LEARNING GUIDE / {number:02}', 'eyebrow')
    add(title, 'h1')

def table(headers, rows, widths):
    cells = [[p(escape(str(x)), 'head') for x in headers]] + [[p(str(x), 'cell') for x in row] for row in rows]
    result = Table(cells, colWidths=[v * mm for v in widths], repeatRows=1, hAlign='LEFT')
    result.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TEAL), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [PALE, colors.white]),
        ('LINEBELOW', (0, -1), (-1, -1), .5, colors.HexColor('#CCDCD6')),
    ]))
    story.append(result)
    story.append(Spacer(1, 5 * mm))

def callout(text):
    box = Table([[p(text)]], colWidths=[174 * mm])
    box.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PALE), ('BOX', (0, 0), (-1, -1), .6, colors.HexColor('#BCD6CA')), ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12), ('TOPPADDING', (0, 0), (-1, -1), 10)]))
    story.append(box)
    story.append(Spacer(1, 4 * mm))

def pct(value):
    return 'Unavailable' if value is None else f'{100 * value:.1f}%'

def count(value):
    return 'Hidden / unavailable' if value is None else f'{value:,}'

section(1, 'Machine learning in your project')
add('A plain-English guide, with the technical terms you can use in your viva.', 'body')
callout('<b>The project question:</b> Given an earlier patient visit, can the recorded measurements help estimate whether the next recorded visit will contain an elevated blood-pressure reading?')
add('The target is a measurement flag: systolic at least 140 mmHg <b>or</b> diastolic at least 90 mmHg at the next visit. It is not a diagnosis of hypertension. Visit intervals vary, so it is not a 30-day forecast. [1]')
table(['In simple words', 'ML terminology', 'Used for'], [
    ('Learn from examples with known later results', 'Supervised binary classification', 'Predict the next-visit BP category.'),
    ('Compare four different ways of learning', 'Logistic Regression; Decision Tree; Random Forest; Gradient Boosting', 'Measure which method works best on the same data.'),
    ('Group patients with similar measurements', 'K-Means clustering', 'Describe aggregate health profiles.'),
    ('Find concentrations of nearby recorded cases', 'DBSCAN clustering', 'Show geographic groups on a station-area map.'),
    ('Make a two-dimensional picture of many measurements', 'Principal Component Analysis (PCA)', 'Display aggregate group centres, not individual patients.'),
    ('Check performance on people excluded from training', 'Grouped cross-validation and holdout evaluation', 'Reduce optimistic results caused by repeat visits.'),
], [62, 59, 53])
add('What stays separate', 'h2')
add('The existing patient and doctor dashboards, clinical records and doctor-access rules are preserved. ML lives in its own Python package and admin-only APIs. Current patient health-score and adherence formulas remain calculations; they are not trained ML models.')
add('Synthetic research demonstration. Predictions support decisions and are not a diagnosis.', 'small')

section(2, 'How data and date filters work')
add('Records are read from the current application database. The 60 later-uploaded monthly PDFs contribute to current summaries and grouping. They were not available at their historical measurement dates, so they cannot become earlier training inputs. New training does not replace source records.')
table(['Stage', 'What happens'], [
    ('1. Read', 'Collect dated consultations, supported report measurements, lab values, conditions and medicine logs; retain private source links only while preparing data.'),
    ('2. Check', 'Validate numeric values and units, resolve consultation corrections, avoid counting a linked report and visit twice, and report missing data.'),
    ('3. Build an example', 'Earlier-visit fields are the inputs (X). The immediately next recorded visit supplies the BP category (y). A missing intervening BP cannot be skipped to make an easier example.'),
    ('4. Protect chronology', 'Later reports, future lab results, subsequent corrections and future dose logs must not become inputs for an earlier prediction.'),
    ('5. Separate people', 'Every visit from one patient stays in one training/validation/test group. Names, emails, passwords and doctor identity are not predictors.'),
], [35, 139])
add('All history and custom dates', 'h2')
add('<b>All history</b> removes the date restriction. A custom start/end range changes the clinical cohort, its summaries, grouping and aggregate model estimates. A narrow range may contain enough data to display counts but too few consecutive visits to train.')
add('<b>Retrain with new data</b> trains on the currently selected data. The comparison card displays that model run\'s training window. Changing the page filter does not secretly retrain a model or change its recorded evaluation scores.')
callout('<b>Historical view is not a backtest.</b> Selecting an older range displays retrospective estimates using the saved model. The model may have been trained with later data. Test performance is reported separately on held-out patients.')
add('A disease filter applies to the earlier visit. The outcome is still the next actual visit, even if that visit has a different recorded condition. Missing coordinates exclude geographic grouping only; eligible measurements can still support other analyses.')

section(3, 'The four prediction algorithms')
table(['Algorithm', 'Simple explanation', 'Technical explanation'], [
    ('Logistic Regression', 'Combines measurements into a score and converts it into a two-category estimate.', 'A linear decision function followed by a sigmoid: p = 1 / (1 + exp(-z)). Despite its name, this use is classification, not linear regression.'),
    ('Decision Tree', 'Asks a sequence of questions, such as whether an earlier BP measurement exceeds a learned split.', 'Recursively partitions feature space. Depth and minimum leaf size constrain overfitting.'),
    ('Random Forest', 'Consults many different trees and combines their answers.', 'An ensemble trained with bootstrap sampling and randomized feature selection. Reduces variance relative to a single tree.'),
    ('Gradient Boosting', 'Builds a small tree, then adds trees that improve the earlier model\'s errors.', 'Sequential weak learners minimize classification loss. Learning rate and tree complexity control the update size and capacity.'),
], [36, 63, 75])
add('What each model receives', 'h2')
add('Eligible earlier measurements include age, systolic/diastolic BP, pulse, temperature, BMI where available, glucose and its test context, recorded condition count, medicine-taking logs and recorded gender. Missing values are handled explicitly; a missing test is not a normal result.')
add('Preprocessing', 'h2')
add('<b>Imputation</b> fills missing numeric inputs with medians learned from the training fold. <b>Scaling</b> puts measurements on comparable scales. <b>One-hot encoding</b> represents allowed categories as numeric indicators. A scikit-learn Pipeline keeps these steps inside training to avoid data leakage. [2]')
add('During fitting, each training fold also balances the two outcome classes. Evaluation keeps equal total patient weights. The test set never determines these training weights.', 'small')
callout('The best model is selected by mean validation <b>macro-F1</b>, with elevated-reading recall breaking ties. The final test set is not used to pick a winner. A model is not guaranteed to outperform a simple baseline.')

section(4, 'Grouping patients and areas')
table(['Topic', 'What it means here', 'What it does not mean'], [
    ('K-Means', 'Groups the latest selected patient measurements after scaling; describes each group with aggregate measurement summaries.', 'Members do not necessarily have the same disease or need the same treatment.'),
    ('DBSCAN', 'Finds groups of nearby coordinate-bearing observations using a distance radius and minimum group size. Geographic distance uses the haversine metric.', 'A dense group is not proof of transmission, an outbreak or a population disease rate.'),
    ('PCA', 'Compresses several standardized measurements into two dimensions to position aggregate K-Means group centres.', 'Its axes are not blood-pressure units, disease severity or a health score.'),
], [28, 84, 62])
add('K-Means: the idea', 'h2')
add('Choose a small number of groups. Assign each patient profile to its nearest centre, recompute the centres, and repeat. Scaling matters: glucose values and ages use different units and should not dominate simply because one has larger numbers. [4]')
add('DBSCAN: the idea', 'h2')
add('Points in a sufficiently dense neighbourhood form a group. Nearby dense neighbourhoods can connect. Sparse observations may stay ungrouped; this is called <b>noise</b> in ML and is not a patient-risk label. The radius does not limit the total size of a connected group. [4]')
add('Safe and understandable output', 'h2')
add('The admin receives aggregate groups and a station-area chart/map. No list of individual patients, private report contents or individual coordinates is returned. Groups too small for display are hidden. Repeated overlapping filters are not a formal guarantee of anonymity.')
callout('The project uses structured measurements and a limited mapping of recorded condition names. It does not add general medical PDF OCR, free-text NLP, treatment recommendations or outbreak forecasting.')
add('Which measurements matter to the model?', 'h2')
add('<b>Permutation importance:</b> after selection is frozen, shuffle each measurement five times in the held-out data and measure the change in macro-F1. A larger drop suggests the model relied on that input. Zero or negative change shows no demonstrated contribution. This neither proves a medical cause nor chooses the model.')

section(5, 'How model evaluation works')
add('A patient-separated holdout of approximately 20% is reserved. The remaining patients are compared using three shared cross-validation folds. All four algorithms receive the same examples and folds. Each patient has equal total weight so a long history does not dominate. [3]')
table(['Term', 'Plain meaning', 'Formula / interpretation'], [
    ('Accuracy', 'How often the predicted category was correct overall.', '(TP + TN) / all examples. Can look high when one category is common.'),
    ('Precision', 'Of the visits flagged elevated, how many actually were elevated?', 'TP / (TP + FP). Measures how often a flag is correct.'),
    ('Recall', 'Of the actual elevated readings, how many were detected?', 'TP / (TP + FN). Low recall means many elevated readings were missed.'),
    ('F1', 'Balances correct flags and missed elevated readings.', '2 x precision x recall / (precision + recall). Not a probability of being medically correct.'),
    ('Macro-F1', 'Balances performance across both categories.', 'Average of each category\'s F1. Used for model selection.'),
    ('Confusion matrix', 'A table of correct and incorrect answers.', 'TP: elevated correctly flagged; TN: below threshold correctly identified; FP: false flag; FN: missed elevated reading.'),
], [31, 70, 73])
add('Why the baseline matters', 'h2')
add('When most readings are below the chosen threshold, always choosing that category can produce high accuracy while detecting no elevated readings. The project compares each model with this majority baseline and with simply repeating the current BP category.')
add('The percentage metrics use equal total patient weights. The confusion matrix shows actual, unweighted visit-pair counts, so its arithmetic need not exactly reproduce the weighted percentages. Historical adherence uses immutable reports available at that visit; editable medicine logs cannot reconstruct earlier knowledge.')
callout('A high score on this synthetic dataset does not establish real-world medical accuracy. No percentage is renamed "clinical reliability." Missing or insufficient evaluation data is shown as unavailable.')

section(6, 'Your actual training results')
data = REPORT.get('data', {})
selection = REPORT.get('selection') or {}
split = REPORT.get('split') or {}
add(f"Training run: {escape(REPORT.get('created_at', 'Unavailable'))}", 'small')
add(f"The evaluated snapshot contained <b>{count(data.get('eligible_patients'))} eligible patients</b> and <b>{count(data.get('eligible_pairs'))} consecutive-visit examples</b>. Holdout: {count(split.get('holdout_patients'))} patients / {count(split.get('holdout_examples'))} examples.")
rows = []
for item in REPORT.get('models', []):
    test = item.get('holdout', {})
    rows.append((escape(item['name']), pct(item['cv']['mean']['macro_f1']), pct(test.get('accuracy')), pct(test.get('precision')), pct(test.get('recall')), pct(test.get('macro_f1'))))
table(['Method', 'CV macro-F1', 'Test accuracy', 'Test precision', 'Test recall', 'Test macro-F1'], rows, [40, 29, 26, 26, 26, 27])
add(f"<b>Selected method:</b> {escape(selection.get('model_name', 'No model selected'))}. Selection used validation results, not the largest test accuracy.")
callout(escape(selection.get('message', REPORT.get('reason', 'No completed evaluation is available.'))))
table(['Baseline', 'Test accuracy', 'Test recall', 'Test macro-F1'], [(escape(item['name']), pct(item['holdout']['accuracy']), pct(item['holdout']['recall']), pct(item['holdout']['macro_f1'])) for item in REPORT.get('baselines', [])], [87, 29, 29, 29])
winner = next((item for item in REPORT.get('models', []) if item['id'] == selection.get('model_id')), None)
if winner:
    cm = winner['holdout']['confusion_matrix']
    if cm:
        table(['Actual / predicted', 'Predicted below threshold', 'Predicted elevated'], [('Actual below threshold', count(cm[0][0]), count(cm[0][1])), ('Actual elevated', count(cm[1][0]), count(cm[1][1]))], [70, 52, 52])
    else:
        add('Confusion matrix hidden because some result groups are too small.', 'small')
add('The demo display gate requires a macro-F1 improvement of 0.01 over both baselines in validation and holdout, recall of at least 50%, and at least 10 independent test patients with elevated outcomes. These fixed checks are not clinical approval criteria. A failed gate keeps the comparison visible.', 'small')

section(7, 'Use it, explain it, and know the limits')
add('Using the admin page', 'h2')
add('1. Sign in to the synthetic app as an administrator and open <b>ML insights</b>.<br/>2. Keep <b>All history</b>, or choose dates, condition and area.<br/>3. Apply filters and read coverage, groups and any prediction limitation.<br/>4. Choose <b>Retrain with new data</b> to create a new comparison using the selected data.<br/>5. Check the training window, selected method and measured results. A failed or insufficient run preserves the previous model.')
add('Training from the project directory', 'h2')
add('node scripts/synthetic.mjs manage run_ml_training --dry-run<br/>node scripts/synthetic.mjs manage run_ml_training --sync', 'code')
add('Optional range: add --date-from YYYY-MM-DD --date-to YYYY-MM-DD. Leave both dates out for all history. Model artifacts are private and separated by database; the application exposes aggregate results only.', 'small')
table(['Viva question', 'Short answer'], [
    ('Why classification?', 'The target has two categories: next recorded BP above or below the specified threshold.'),
    ('Why four models?', 'They offer different decision structures and allow a fair empirical comparison on identical data.'),
    ('Why keep patient visits together?', 'Repeated visits share patient characteristics; mixing the same person into training and testing makes evaluation too optimistic.'),
    ('Is this a diagnostic system?', 'No. It is a synthetic research demonstration predicting a later recorded measurement.'),
    ('Why not use every field?', 'Names and IDs are irrelevant identifiers; future values leak the answer; unsupported text has no validated structured meaning.'),
], [61, 113])
add('References and implementation notes', 'h2')
for text in [
    '[1] WHO, Hypertension: https://www.who.int/news-room/fact-sheets/detail/hypertension',
    '[2] scikit-learn, Common pitfalls: https://scikit-learn.org/stable/common_pitfalls.html',
    '[3] scikit-learn, Cross-validation: https://scikit-learn.org/stable/modules/cross_validation.html',
    '[4] scikit-learn, Clustering: https://scikit-learn.org/stable/modules/clustering.html',
    'Source code: ml/pipeline.py; backend/analytics/ml_*.py; frontend/components/admin-ml.tsx. Run instructions and limitations: docs/ML_INSIGHTS.md.',
]:
    add(escape(text), 'small')

def footer(canvas, doc):
    width, height = doc.pagesize
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#C9DAD3'))
    canvas.line(18 * mm, 16 * mm, width - 18 * mm, 16 * mm)
    canvas.setFont('Guide', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 11 * mm, 'MedyLink | Synthetic ML learning guide | 3 October 2026')
    canvas.drawRightString(width - 18 * mm, 11 * mm, f'{doc.page}')
    canvas.restoreState()

doc = SimpleDocTemplate(str(OUT), pagesize=(210 * mm, 297 * mm), rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=23 * mm, title='MedyLink - Machine Learning Explained', author='MedyLink')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
