"""Create the learning guide from the completed, measured ML evaluation."""
import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Render the learning guide from an aggregate evaluation report.')
parser.add_argument('--report', type=Path, default=ROOT / 'ml/reports/disease_evaluation.json')
args = parser.parse_args()
REPORT = json.loads(args.report.read_text(encoding='utf-8-sig'))
if REPORT.get('task') != 'disease':
    parser.error('Choose a disease evaluation report; blood-pressure prediction has been removed.')
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

section(1, 'Machine learning in MedyLink')
add('A plain-English guide to the current disease prediction and grouping features, with terms for your viva.')
callout('<b>The project question:</b> Which of ten diseases best matches the measurements and symptoms recorded at a visit?')
add('The system learns from synthetic visits with known primary diseases. It compares four classifiers, then uses the selected model for aggregate estimates. The labels are Dengue, Influenza, Hypertension, Type 2 diabetes, Asthma, Anemia, Gastroenteritis, Hypothyroidism, Osteoarthritis and Malaria.')
table(['Simple explanation', 'ML terminology', 'Where used'], [
    ('Learn disease categories from examples', 'Supervised multiclass classification', 'Disease prediction'),
    ('Compare four learning methods', 'Logistic Regression, Decision Tree, Random Forest and KNN', 'Saved model comparison'),
    ('Group similar measurements', 'K-Means clustering', 'Aggregate patient profiles'),
    ('Find nearby recorded case groups', 'DBSCAN clustering', 'Station-area concentrations'),
    ('Display many measurements on two axes', 'Principal Component Analysis', 'Aggregate group centres'),
    ('Test with different patients', 'Patient-level holdout and stratified cross-validation', 'Model evaluation'),
], [60, 67, 47])
add('Current project scope', 'h2')
add('The future blood-pressure prediction task and its training have been removed. Recorded BP readings remain in clinical reports and charts and can still be inputs to disease classification and measurement grouping. The health score and adherence are arithmetic calculations, not trained prediction models.')
add('Only administrators can access ML insights. Patient and provider access rules remain enforced. Predictions support decisions and are not a diagnosis.', 'small')

section(2, 'How the data flows')
table(['Step', 'What happens'], [
    ('1. Read visits', 'Use authorized synthetic observations with a supported primary disease. Keep names, contact details, passwords and doctor identities out of the model.'),
    ('2. Build inputs', 'Use age, gender, station, visit month, vitals, blood tests and eight symptom flags. The primary disease is the answer to learn, never a feature.'),
    ('3. Check timing', 'Reject values unavailable at the visit. Missing inputs remain missing until fold-specific preprocessing. Diagnosis text and prescriptions are not features.'),
    ('4. Separate people', 'Reserve 20% of patients for the final test. Keep every visit from one patient together. Use five shared stratified CV folds within the other 80%.'),
    ('5. Compare and check', 'Choose the model with highest average CV macro-F1. Inspect its held-out results only after selection. Enable estimates only if the fixed checks pass.'),
    ('6. Display aggregates', 'Use each selected patient\'s latest eligible record. Return disease counts and group summaries, with counts of one to four hidden.'),
], [33, 141])
add('Filters and saved results', 'h2')
add('<b>All history</b> includes all recorded dates. Condition search supports partial names and multiple selections; date, line and station filters narrow the view. Counts, charts, groups and estimates reflect the applied cohort. Saved test scores and feature bars keep their training selection until retraining.')
callout('A recorded Influenza filter selects visits labelled Influenza. The model may estimate another disease for some of those visits. Those are model disagreements within the selected records, not additional confirmed cases.')
add('An older date selection is a retrospective view with the saved model, not an out-of-time backtest. The model may have been trained with later records.', 'small')

section(3, 'The four disease algorithms')
table(['Algorithm', 'Simple explanation', 'Technical explanation'], [
    ('Logistic Regression', 'Finds a scoring pattern across measurements and symptoms.', 'A multiclass linear classifier with regularization; a useful comparatively simple baseline.'),
    ('Decision Tree', 'Asks a sequence of learned questions.', 'Partitions feature space into branches. Depth and minimum leaf size limit overfitting.'),
    ('Random Forest', 'Lets many different trees vote together.', 'Uses bootstrap samples and randomized features to reduce dependence on one tree.'),
    ('KNN', 'Looks at the most similar past examples.', 'A distance-based classifier. Scaling keeps large-unit measurements from dominating distance.'),
], [36, 63, 75])
add('Fair preprocessing', 'h2')
add('Imputation handles missing inputs using only training data. Scaling places numeric features on comparable scales. Encoding represents categories numerically. A scikit-learn Pipeline fits preprocessing inside each fold to avoid leaking validation or test information.')
add('What the metrics mean', 'h2')
table(['Metric', 'Meaning'], [
    ('Accuracy', 'The share of disease predictions that were correct overall.'),
    ('Recall for a disease', 'Of visits that actually had that primary disease, how many the model found.'),
    ('Macro-F1', 'Average disease-specific F1, balancing precision and recall across all ten classes. This selects the winner in CV.'),
    ('Confusion matrix', 'Rows are recorded diseases; columns are predicted diseases. Off-diagonal cells are disagreements.'),
], [43, 131])
add('Percentage metrics give each patient equal total weight. Confusion-matrix cells count raw visits, so they need not reproduce the weighted percentages. The held-out test never chooses the winning model.', 'small')

section(4, 'The measured disease results')
data = REPORT.get('data', {})
selection = REPORT.get('selection') or {}
split = REPORT.get('split') or {}
add(f"Saved run: {escape(REPORT.get('created_at', 'Unavailable'))}", 'small')
add(f"The report uses <b>{count(data.get('eligible_patients'))} patients</b> and <b>{count(data.get('eligible_rows'))} eligible visits</b>. Development: {count(split.get('training_patients'))} patients. Final test: {count(split.get('holdout_patients'))} patients. No patient appears in both sets.")
rows = []
for item in REPORT.get('models', []):
    test = item.get('holdout', {})
    rows.append((escape(item['name']), pct(item['cv']['mean']['macro_f1']), pct(test.get('accuracy')), pct(test.get('macro_f1'))))
table(['Method', 'CV macro-F1', 'Test accuracy', 'Test macro-F1'], rows, [60, 38, 38, 38])

add(f"<b>Selected model:</b> {escape(selection.get('model_name', 'No model selected'))}. The highest mean CV macro-F1 chose the winner; final-test accuracy did not choose it.")
gate_status = 'passes' if selection.get('prediction_enabled') else 'does not pass'
callout(f"Aggregate predictions require at least <b>75% test accuracy</b> and <b>70% test macro-F1</b>. The saved {escape(selection.get('model_name', 'model'))} result {gate_status} these simulation thresholds. It is not clinical validation.")
add('What helped the selected model', 'h2')
table(['Input', 'Test macro-F1 decrease when shuffled'], [(escape(row['label']), f"{row['importance'] * 100:.2f} points") for row in REPORT.get('feature_importance', [])[:5]], [100, 74])
add('Permutation importance shuffles one input and measures the decrease in test macro-F1. A larger drop suggests dependence by this saved model. It is not a disease probability or evidence of medical causation. Correlated features can share information.')
add('Training and evaluation come from a simulated population with deliberately learnable patterns, overlap, label noise and missing values. The numbers describe this experiment, not accuracy in a hospital.', 'small')

section(5, 'Grouping and using the dashboard')
table(['Topic', 'What the administrator sees'], [
    ('K-Means', 'Groups with similar standardized measurements; group counts and summaries, without individual members.'),
    ('PCA', 'Aggregate group centres on two summary axes. These axes are not BP units, disease severity or a health score.'),
    ('DBSCAN', 'Concentrations of nearby synthetic recorded cases. A group is not proof of an outbreak or transmission.'),
], [32, 142])
add('Retrain disease models', 'h2')
add('Apply your date, condition and area filters, then use <b>Retrain disease models</b>. The server repeats the four-model comparison and saves a new report and private model bundle. It uses the selected records; it does not alter clinical data. A narrow selection without adequate examples of all ten diseases keeps the previous successful model.')
add('Run from the project root', 'h2')
add('npm run synthetic:manage -- run_ml_training --dry-run<br/>npm run synthetic:manage -- run_ml_training --sync', 'code')
add('Disease is the only supported training task and the default. The synthetic database must be configured first. Optional dates: --date-from YYYY-MM-DD --date-to YYYY-MM-DD. Failed runs preserve the previous model; training uses a local background worker.', 'small')
add('Viva answers', 'h2')
table(['Question', 'Answer'], [
    ('Why four models?', 'Different decision rules are compared fairly on identical data and patient splits.'),
    ('Why keep patients separate?', 'Repeated visits share traits; mixing a person across train and test exaggerates generalization.'),
    ('Why use macro-F1?', 'It gives each disease equal importance when class counts differ.'),
    ('Can it diagnose a patient?', 'No. It is an aggregate synthetic demonstration without independent clinical validation.'),
], [60, 114])
add('Sources: ml/disease_pipeline.py; ml/pipeline.py; ml/reports/disease_evaluation.json. Setup and viva notes: docs/ML_INSIGHTS.md and ml/DISEASE_TASK.md.', 'small')


def footer(canvas, doc):
    width, height = doc.pagesize
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#C9DAD3'))
    canvas.line(18 * mm, 16 * mm, width - 18 * mm, 16 * mm)
    canvas.setFont('Guide', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 11 * mm, 'MedyLink | Synthetic ML learning guide | 4 October 2026')
    canvas.drawRightString(width - 18 * mm, 11 * mm, f'{doc.page}')
    canvas.restoreState()

doc = SimpleDocTemplate(str(OUT), pagesize=(210 * mm, 297 * mm), rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=23 * mm, title='MedyLink - Machine Learning Explained', author='MedyLink')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
