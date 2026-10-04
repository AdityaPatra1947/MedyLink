# Free health datasets for MedyLink

Research checked: **29 September 2026**. This is a source shortlist, not an imported dataset. No external patient data or large archives were downloaded.

**Recommendation:** retain the existing, explicitly synthetic Mumbai station data for the current patient-level, distance-based DBSCAN demonstration. For an observed Mumbai extension, start with ward-level BMC/Praja counts and build a separate aggregate map and trend view. I did not find a verified freely open dataset combining Mumbai railway-station areas, individual patients, disease episodes, dates, and usable patient coordinates in the sources checked. This is a search finding, not a claim that no such dataset exists.

## 1. Mumbai ward disease counts — Praja, using BMC RTI data

- **Source/download:** [Mumbai Health White Paper 2022, PDF](https://www.praja.org/praja_docs/praja_downloads/Mumbai%20Health%20White%20Paper%202022_Final.pdf).
- **Coverage:** all 24 BMC wards; annual counts for 2012–2021. Tables 18, 21, 25, 28, 31, 36, 39 and 42 contain malaria, dengue, TB, HIV, diarrhoea, typhoid, diabetes and hypertension counts registered in BMC dispensaries. These are registered service counts, not a complete census of residents with disease.
- **Useful columns:** ward, year, disease, case count; some tables include totals and population-based summaries. PDF extraction and manual checks are needed; preserve missing symbols separately from zero.
- **Access:** publicly readable PDF without login. No explicit open redistribution licence was verified; do not label it CC0 or CC BY without further permission evidence.
- **Fit:** strongest verified local starting point for ward trends, disease-profile clustering and choropleths. Annual ward totals cannot validate patient-level 500-metre clusters, and a treating dispensary's ward should not automatically be treated as the patient's home ward.

The [2024 report](https://www.praja.org/praja_docs/praja_downloads/Mumbai%20Health%20White%20Paper%202024.pdf) has newer city-level disease totals through 2023. It should not be assumed to offer the same ward-level time series.

## 2. IDSP weekly outbreak reports — Government of India

- **Source:** [official weekly report index](https://www.idsp.mohfw.gov.in/index4.php?lang=1&level=0&lid=3689&linkid=406). The indexed catalogue includes 2023–2025 weekly reports and 2026 reports; completeness must be checked for the chosen period.
- **Direct example:** [2026 report containing Nagpur and Satara outbreak rows](https://idsp.mohfw.gov.in/WriteReadData/l892s/84687716011771571627.pdf). The official PDF was search-indexed, but the browser's direct PDF fetch failed during this review.
- **Useful fields:** outbreak reference, state, district, disease, cases, deaths, dates, status, and a narrative that can identify village/sub-district/locality. The sample includes Maharashtra events starting in January 2026.
- **Access:** free public PDFs; no registration gate observed. A specific reuse licence was not verified.
- **Fit:** promising for an **outbreak-event** spatial/temporal extension across Maharashtra, after extraction and validated locality geocoding. No individual patient coordinates. Store geocoding precision and deduplicate outbreak references across reports; repeated updates must not become new outbreaks. Reported outbreaks are not the same as all disease cases or population incidence.

## 3. Maharashtra district-month HMIS — data.gov.in

- **Source:** [Maharashtra item-wise monthly HMIS catalogue, government mirror](https://jk.data.gov.in/catalog/item-wise-monthly-hmis-report-district-level-maharashtra); [canonical catalogue](https://data.gov.in/catalog/item-wise-monthly-hmis-report-district-level-maharashtra).
- **Owner/granularity:** Ministry of Health and Family Welfare, district-level monthly indicator aggregates. Listed indicators include malaria, fever, diarrhoeal disease, tuberculosis, hypertension and respiratory infection, alongside many service indicators.
- **Freshness:** catalogue published 23 December 2020 and updated 17 February 2021. Exact resource month/year coverage was **not verified**; those dates describe the catalogue, not every observation. This is not evidence of a current surveillance feed.
- **Access:** catalogue states release under NDSAP and displays API and ZIP controls. The mirror was readable, but the ZIP control did not resolve to a downloadable archive in this review. Verify resource files and API/key conditions before scheduling implementation.
- **Fit:** an acquisition candidate for monthly district comparisons. District totals are too coarse for railway-station DBSCAN; do not represent district centroids as observed patient locations.

## 4. Synthea / SyntheticMass — MITRE

- **Source/download:** [official samples](https://synthetichealth.github.io/downloads.html), including a 100-patient CSV sample (about 7 MB) and older 1,000-patient CSV samples (about 9 MB; listed under 2019–2021). Use these small samples rather than the multi-gigabyte bulk archive.
- **Schema:** [official CSV dictionary](https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary) documents patient IDs, address latitude/longitude, condition start/stop dates and codes, encounters, medications, observations and related tables. Coordinates are optional fields, so check missingness.
- **Access:** downloadable synthetic records without credentialed clinical-data approval. The owner explicitly permits secondary use without restriction and requests citation.
- **Fit:** best ready-made patient-shaped alternative for application integration and synthetic cohort experiments. SyntheticMass models US/Massachusetts records, not observed Mumbai patients. Moving these records to Mumbai station coordinates creates a new synthetic scenario; it does not establish local disease rates or genuine geographic clusters. Pin the sample/generator version and inspect actual date coverage before import.

## 5. UCI Diabetes 130-US Hospitals, 1999–2008

- **Source/download:** [UCI dataset 296](https://archive.ics.uci.edu/dataset/296/diabetes%2B130-us%2Bhospitals%2Bfor%2Byears%2B1999-2008), with a public Download button (about 3 MB compressed), `diabetic_data.csv` and `IDS_mapping.csv`.
- **Coverage/fields:** 101,766 US hospital encounter records from 1999–2008; patient and encounter IDs, age bands, diagnoses, medications, laboratory-related measures, hospital stay duration and readmission outcome. UCI lists 47 features and notes missing values.
- **Access:** free, no credentialed-access process; **CC BY 4.0**, requiring attribution.
- **Fit:** useful real tabular data for comorbidity groups, utilisation profiles and readmission research. It does not provide the patient latitude/longitude and calendar dates needed by the current spatial pipeline. For predictive experiments, split by patient ID so repeated encounters do not leak across training and test sets. Demographics and hospital selection differ substantially from Mumbai primary care.

## 6. PhysioNet MIMIC-IV clinical demo

- **Source/download:** [MIMIC-IV Demo v2.2](https://physionet.org/content/mimic-iv-demo/2.2/); its Files section provides a 15.4 MB ZIP and individual CSV files. [Hospital table listing](https://physionet.org/content/mimic-iv-demo/2.2/hosp/) includes admissions, diagnoses, labs, pharmacy and prescriptions.
- **Coverage:** 100 deidentified patients from Beth Israel Deaconess Medical Center, Boston. Published 31 January 2023. Selection uses anchor-year groups 2011–2013 and 2014–2016; dates are shifted, removing real seasonality and calendar alignment. Free-text notes are excluded.
- **Access:** demo files are open access under **Open Data Commons ODbL 1.0**. The separate [full MIMIC-IV v3.1](https://physionet.org/content/mimiciv/3.1/) requires credentialing, CITI training and a signed data-use agreement; it is not unrestricted open data.
- **Fit:** real clinical relational-data practice, limited by a small demo and hospital/ICU selection. It supplies no Mumbai residential coordinates and is unsuitable for geographic disease hotspot claims or real-world seasonal analysis from shifted dates.

## Applying the shortlist

1. Keep synthetic demonstrations and observed surveillance in separate dataset IDs, with visible provenance and unit of observation.
2. For Mumbai reality-based work, extract the Praja ward/year tables first, validate totals against the PDF, and preserve the source table/page. Use ward geography that matches the reporting period.
3. If dated spatial records are essential, scope an IDSP event-level pilot with a documented geocoding method. Evaluate event density, not patient prevalence; distance thresholds must match coordinate precision.
4. Do not distribute aggregate counts among invented station points and present them as observed patient data. Disease counts alone also do not supply a DBSCAN ground-truth cluster label.

OpenCity was also checked. Its [health catalogue](https://data.opencity.in/dataset/?_organization_limit=0&q=OpenCity.in&res_format=CSV&sort=score+desc%2C+metadata_modified+desc&tags=Health) includes Mumbai public-health facility locations and reports. Facility coordinates can support reference maps, but they are not patient residence or disease-episode coordinates. No verified station-level patient disease download was identified there during this review.
