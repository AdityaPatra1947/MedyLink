# Mumbai station-area reference

Reference date: **29 September 2026**. The companion `mumbai_stations.json` contains **34 unique real station areas** represented by **35 source points**. It is a small geographic reference for synthetic patient data, not an exhaustive network map or a live timetable.

## Coordinate provenance

- Dataset: [Mumbai Suburban Network 2025](https://data.opencity.in/dataset/mumbai-suburban-network-2025).
- Resource: [Suburban Line Stations](https://data.opencity.in/dataset/mumbai-suburban-network-2025/resource/142fbd25-9ceb-41b2-900d-72479cdc179e).
- [Exact KML download](https://data.opencity.in/dataset/50851056-1954-459f-a747-09366dcd416d/resource/142fbd25-9ceb-41b2-900d-72479cdc179e/download/5baa7e83-2855-4d17-86a9-9954b044ec08.kml) and [CKAN metadata](https://data.opencity.in/api/3/action/resource_show?id=142fbd25-9ceb-41b2-900d-72479cdc179e).
- The publisher metadata records source **BMC**, credit **OpenCity.in**, license ID **Public Domain**, last modified **2025-11-25T15:23:31.863053**. This is the catalog attribution, not an independent survey certification.
- Downloaded KML: **55,061 bytes**, **106 point features**. The complete source KML is not redistributed with this subset.
- Raw KML SHA-256: `5e7ee5a97bcc5db017fe11f246521c32cc0c21ed309a616c95c84875b61ff30a`.

KML points encode longitude before latitude. The JSON uses separate named fields in decimal degrees and rounds to six decimal places. These are approximate station anchors; the number of digits does not certify physical accuracy. There are no household coordinates. A generator must keep any simulated patient coordinates separate and identify them as synthetic.

## Official line references

- [central_system_map_2019](https://cr.indianrailways.gov.in/cris/uploads/files/1561376559029-all_div_merged.pdf): Central Railway Mumbai Division system map, page 1, effective 2019-04-01; station topology and interchange cross-check, not current timetable.
- [western_timetable_2023](https://wr.indianrailways.gov.in/cris/uploads/files/1680671491866-DN%20AC%20TIME%20TABLE%2005.04.2023.pdf): Western Railway official suburban station sequence, dated 2023-04-05; includes Churchgate, Dadar, Bandra, Andheri, Goregaon and Borivali.
- [pib_harbour_operation_2018](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1537441&lang=2&reg=48): Ministry of Railways/PIB 2018-07-03 release refers to Harbour lines at Andheri-Vile Parle and Goregaon-CSMT service.
- [pib_projects_2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2245194&lang=2&reg=48): Ministry of Railways/PIB 2026-03-25 project list includes the sanctioned Goregaon-Borivali Harbour extension; this reference does not establish operation to Borivali.

The KML `N_REGION` attribute is a single category, not a complete list of services: for example, Mahim is tagged HARBOUR and Kurla CENTRAL. Membership arrays therefore use the curated Central/Western/Harbour classification supported by the official references. They intentionally exclude Trans-Harbour, Uran, Metro and non-suburban services. The older references establish station topology; no current train timing is inferred from them.

## Normalization and interchange rules

- **Dadar:** source `existing_suburban_stations.9` (WESTERN) and `.30` (CENTRAL) become one `DADAR` area. Its anchor is the arithmetic mean of the two source latitudes and longitudes, rounded once to six decimal places. Both source IDs remain attached. Dadar has Central and Western membership; it has no Harbour membership.
- **CSMT:** one area with Central and Harbour membership. Full current name Chhatrapati Shivaji Maharaj Terminus and legacy CST/CSTM/VT/Victoria Terminus names are aliases, not additional stations.
- **Sandhurst Road and Kurla:** each remains one area with Central and Harbour memberships.
- **Mahim, Bandra, Andheri and Goregaon:** each remains one area with Western and Harbour memberships. Malad, Kandivali and Borivali are Western-only here; a sanctioned extension is not treated as an operational line.
- **Thane:** Central in the requested three-corridor classification. Its Navi Mumbai connection is Trans-Harbour, which is a separate corridor.
- **Matunga:** use Central source feature `.31`. Do not merge it with Western Matunga Road `.10`. Bandra suburban station is likewise distinct from Bandra Terminus.
- Source spelling **Dombivili** is normalized to **Dombivli**. **CBD Belapur** uses ID `BELAPUR`; **Mahim Junction** uses `MAHIM`. Wadala/Vadala spellings are retained as aliases.
- `source_name` is the original KML feature label; `source_feature_ids` contains the complete Placemark IDs. `aliases` are lookup aids, not alternate areas.
- City fields are broad urban-region labels, not statutory municipal assignments. The Navi Mumbai label includes Panvel station area; Kalyan and Dombivli use Kalyan-Dombivli.

## Selected areas

Each row is unique. Line-filter totals can overlap at interchanges and must not be summed as a count of distinct patients.

| Station ID | Area | Lines | Latitude | Longitude | Source feature suffixes |
| --- | --- | --- | ---: | ---: | --- |
| `CSMT` | CSMT | Central, Harbour | 18.940272 | 72.835706 | 23 |
| `SANDHURST_ROAD` | Sandhurst Road | Central, Harbour | 18.960879 | 72.839579 | 25 |
| `BYCULLA` | Byculla | Central | 18.976693 | 72.832769 | 26 |
| `DADAR` | Dadar | Central, Western | 19.018852 | 72.843385 | 9, 30 |
| `MATUNGA` | Matunga | Central | 19.027496 | 72.850208 | 31 |
| `SION` | Sion | Central | 19.047710 | 72.864004 | 32 |
| `KURLA` | Kurla | Central, Harbour | 19.065477 | 72.879354 | 33 |
| `GHATKOPAR` | Ghatkopar | Central | 19.085989 | 72.908466 | 35 |
| `VIKHROLI` | Vikhroli | Central | 19.111918 | 72.928145 | 36 |
| `BHANDUP` | Bhandup | Central | 19.142435 | 72.937651 | 38 |
| `MULUND` | Mulund | Central | 19.171866 | 72.956553 | 40 |
| `THANE` | Thane | Central | 19.186115 | 72.975934 | 74 |
| `DOMBIVLI` | Dombivli | Central | 19.218286 | 73.086843 | 79 |
| `KALYAN` | Kalyan | Central | 19.235191 | 73.129971 | 81 |
| `CHURCHGATE` | Churchgate | Western | 18.935296 | 72.827192 | 1 |
| `MARINE_LINES` | Marine Lines | Western | 18.945788 | 72.823814 | 2 |
| `MUMBAI_CENTRAL` | Mumbai Central | Western | 18.969893 | 72.818799 | 5 |
| `LOWER_PAREL` | Lower Parel | Western | 18.995319 | 72.830172 | 7 |
| `MAHIM` | Mahim | Western, Harbour | 19.040717 | 72.846918 | 11 |
| `BANDRA` | Bandra | Western, Harbour | 19.055589 | 72.840328 | 12 |
| `ANDHERI` | Andheri | Western, Harbour | 19.117175 | 72.846504 | 16 |
| `GOREGAON` | Goregaon | Western, Harbour | 19.164870 | 72.849628 | 18 |
| `MALAD` | Malad | Western | 19.186834 | 72.848936 | 19 |
| `KANDIVALI` | Kandivali | Western | 19.204532 | 72.852051 | 20 |
| `BORIVALI` | Borivali | Western | 19.229063 | 72.856649 | 21 |
| `WADALA_ROAD` | Wadala Road | Harbour | 19.016006 | 72.858942 | 45 |
| `SEWRI` | Sewri | Harbour | 18.998931 | 72.854579 | 44 |
| `CHEMBUR` | Chembur | Harbour | 19.062598 | 72.901244 | 49 |
| `GOVANDI` | Govandi | Harbour | 19.055093 | 72.915394 | 50 |
| `MANKHURD` | Mankhurd | Harbour | 19.048165 | 72.931724 | 51 |
| `VASHI` | Vashi | Harbour | 19.063117 | 72.998897 | 59 |
| `NERUL` | Nerul | Harbour | 19.033471 | 73.018211 | 62 |
| `BELAPUR` | CBD Belapur | Harbour | 19.019046 | 73.039087 | 64 |
| `PANVEL` | Panvel | Harbour | 18.990570 | 73.121341 | 68 |

## Validation and limits

- Checked all selected coordinates are finite and within latitude 18.9–19.3 N and longitude 72.8–73.2 E. This is a regional bounds check, not a land-use or address validation.
- Checked 34 unique area IDs, 34 unique canonical names, and 35 distinct source features; the only merged pair is Dadar.
- Checked required scenario anchors KURLA, ANDHERI, VASHI, GHATKOPAR, BORIVALI and NERUL exist.
- Checked Dadar/Thane have no Harbour membership, Borivali is Western-only, and Matunga uses the Central feature.
- These area selections and any synthetic patient counts do not estimate population, station ridership, disease incidence, real travel patterns or exposure.
