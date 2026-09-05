# JalPulse analysis summary

_Generated 2026-09-05T15:55:06+00:00Z by `src/report.py`._

## Coverage
- 9,498 Goa accommodation properties scored (source: Goa Dept. of Tourism registry) `[P]`
- Registry-wide parse coverage vs. max serial number: see `data/raw/goa_hotels_raw.csv` log output

## Tier distribution (by value_score)
- **Priority**: 481 properties (5.1%)
- **Watch**: 2,763 properties (29.1%)
- **Long-tail**: 6,254 properties (65.8%)

## Priority-tier geographic concentration
- Bardez alone accounts for 81.7% of the 481 Priority-tier properties `[D]`
- Top talukas in the Priority tier:

| Taluka | Priority-tier properties |
|---|---|
| Bardez | 393 |
| Salcete | 47 |
| Tiswadi | 20 |
| Mormugao | 9 |
| Pernem | 8 |
| Canacona | 2 |
| Ponda | 1 |
| Dharbandora | 1 |

## The value-vs-winnability caveat
- Without a decision-fit adjustment, **30 of the top 100 properties by raw value_score** are above 120 rooms -- i.e. likely branded/chain-managed, corporate-procured accounts that do not match EPBL's Persona 1 (independent owner/GM personally approves). `[D]` derived from this pipeline; do not present raw value_score as a sales-readiness ranking.

## The headline account list: worth winning AND winnable
- **428 properties** are both Priority-tier by value_score *and* inside the 20-120-room decision-fit band. `[D]` derived by intersecting the two cuts above.
- Bardez alone accounts for 85.5% of this list (366 of 428).
- This is the pipeline's answer to "which accounts should Year 1 actually call" -- see `data/processed/jalpulse_priority_and_winnable.csv` for the full list.

## Phase-1 shortlist (owner/GM decision-fit band: 20-120 rooms)
- 805 properties fall inside the fit band `[A]` (see config.py for the room-band assumption)

| Taluka | Phase-1 fit-band properties |
|---|---|
| Bardez | 449 |
| Salcete | 116 |
| Pernem | 104 |
| Tiswadi | 71 |
| Mormugao | 30 |
| Canacona | 17 |
| Ponda | 11 |
| Sanguem | 3 |

### Top 15 Phase-1 shortlist properties (by value_score within the fit band)
_Names with `name_confidence=low` are parsing artifacts -- verify against the source PDF before using in outreach or on a slide._

| Name | Confidence | Taluka | Rooms | Value score | Fit | Phase-1 score |
|---|---|---|---|---|---|---|
| Adamo The Bellus | high | Bardez | 117 | 0.907 | 1.00 | 0.907 |
| 116 | low | Bardez | 116 | 0.906 | 1.00 | 0.906 |
| 115 | low | Bardez | 115 | 0.906 | 1.00 | 0.906 |
| Holiday Inn Goa Candolim | high | Bardez | 110 | 0.903 | 1.00 | 0.903 |
| W Goa | high | Bardez | 109 | 0.902 | 1.00 | 0.902 |
| Royale Assagao | high | Bardez | 106 | 0.901 | 1.00 | 0.901 |
| Whispering Palms Beach | high | Bardez | 106 | 0.901 | 1.00 | 0.901 |
| 104 | low | Bardez | 104 | 0.899 | 1.00 | 0.899 |
| Ximer, Arpora, Bardez, North Goa | high | Bardez | 104 | 0.899 | 1.00 | 0.899 |
| Nazri Resort | high | Bardez | 104 | 0.899 | 1.00 | 0.899 |
| Fortune Select Candolim | high | Bardez | 103 | 0.899 | 1.00 | 0.899 |
| Fortune Acron Regina | high | Bardez | 102 | 0.898 | 1.00 | 0.898 |
| 102 | low | Bardez | 102 | 0.898 | 1.00 | 0.898 |
| 100 | low | Bardez | 100 | 0.897 | 1.00 | 0.897 |
| Hyatt Place | high | Bardez | 97 | 0.895 | 1.00 | 0.895 |

## Top 15 properties by raw value_score (unfiltered -- includes low-fit large chains)
| Name | Confidence | Taluka | Rooms | Value score | Tier |
|---|---|---|---|---|---|
| Ginger Candolim | high | Bardez | 282 | 0.963 | Priority |
| Club Mahindra Assonora | high | Bardez | 244 | 0.954 | Priority |
| Resorte Marinha Dourada | high | Bardez | 203 | 0.942 | Priority |
| Ibis Styles | high | Bardez | 197 | 0.940 | Priority |
| The Westin Goa, Anjuna | high | Bardez | 171 | 0.931 | Priority |
| Fairfield By Marriott | high | Bardez | 169 | 0.930 | Priority |
| Hyatt Centric | high | Bardez | 168 | 0.930 | Priority |
| Jw Marriott Goa Vagator | high | Bardez | 151 | 0.923 | Priority |
| Novotel Goa Candolim | high | Bardez | 149 | 0.922 | Priority |
| 146 | low | Bardez | 146 | 0.921 | Priority |
| Primo Bom Terra Verde | high | Bardez | 143 | 0.920 | Priority |
| Neelams The Grand | high | Bardez | 143 | 0.920 | Priority |
| Sinquerim, Candolim, Bardez, North Goa- 403515 | high | Bardez | 143 | 0.920 | Priority |
| Ibis Styles Goa Vagator | high | Bardez | 142 | 0.919 | Priority |
| Dando, Candolim, Bardez, North Goa- 403515 | high | Bardez | 142 | 0.919 | Priority |

## Methodology, in one paragraph
JalPulse combines three signals per property: commercial value (log-scaled room count, `[P]` real per-property data), regulatory urgency (GSPCB Consent-to-Operate size-band classification, `[P]` real policy applied categorically), and serviceability (taluka cluster density, `[P,D]` derived from the registry's own concentration). These are weighted into `value_score`. A separate `decision_fit` factor (room-count band as a proxy for independent ownership, `[A]` a stated modelling assumption) discounts `value_score` into `phase1_score`, so the Phase-1 shortlist reflects who EPBL can actually sell to in Year 1, not just who has the most wastewater. Full formula and every constant: `config.py`.
