# Business insights

> **Simulated data.** The numbers below come from a seeded generator whose behaviour (retention curve, tutorial effect, country quality, CPI) I defined — they demonstrate the *analysis method*, not real market facts. Reproduce: `make demo` (seed 42).

Dashboards: [Game performance](img/dashboard_1_game_performance.png) · [Retention](img/dashboard_2_retention.png) · [Funnel](img/dashboard_3_funnel.png) · [Marketing](img/dashboard_4_marketing.png)

## 1. How many players come back? (retention)
| | D1 | D7 | D30 |
|---|---|---|---|
| All players | 51.7 % | 26.4 % | 3.7 % |
| Tutorial completed | 57.9 % | 31.1 % | 4.2 % |
| Tutorial not completed | 36.1 % | 14.7 % | 2.5 % |

* Tutorial completers retain ~2.1× better at D7. **Caveat:** correlation — players who finish a tutorial are already more engaged; an A/B test of a shorter tutorial is needed before claiming causation.
* D7 by country: JP 32.8 % · US 31.1 % · DE 30.6 % · GB 29.8 % · FR 27.8 % · BR 22.6 % · TR 21.6 % · IN 18.7 %.
* Android vs iOS D1 is flat (51.5 % vs 52.0 %) → platform is not the retention lever.
* **Action:** invest in tutorial friction reduction first; re-check D7 for BR/TR/IN onboarding (localisation, device performance).

## 2. Where do players drop? (funnel, order-aware, per user)
`app_open 49,997 → tutorial_started 49,135 (98.3 %) → tutorial_completed 35,097 (70.2 %) → level_1_completed 30,029 (60.1 %) → purchase 1,270 (2.5 %)`

* Biggest single leak: **tutorial start → completion loses 14,038 players (28.6 % of starters).**
* Only 4.2 % of level-1 finishers ever purchase → monetisation hinges on a small payer base; test an earlier first-purchase offer.

## 3. Which levels lose players?
Completion rate falls from 87 % (L1) → 72 % (L10) → 60 % (L20). Players who *stopped at* a level peak at **levels 7–11 (≈ 2.5 k each)**, the same range where fail rate stays ≈ 46 % — a difficulty wall.
* **Action:** ease or add a hint/booster around levels 7–11, then re-measure `mart_level_dropoff.churned_users`.

## 4. Is the DAU drop real? (monitoring story)
* DAU peaks mid-September then decays because the simulated installs stop on 15 Oct → a *real* audience decline. Stickiness falls from ~16 % to ~4 %.
* **21 Oct: DAU −22 % in one day (2,389 → 1,872) while events fall −77 % (19,048 → 4,401)** — flagged `pipeline_issue` (events collapse faster than users). Treat as an ingestion outage, not churn.
* **1–12 Oct (v1.4.2):** level completion rate reads 0 % and average session length drops ~5.5 → ~4.9 min. Both are *tracking artefacts*: the version never sends `level_completed`, and session end is derived from the last event. `version_event_coverage` flags it.
* **Lesson for stakeholders:** do not read KPI dips as player behaviour until the DQ gate is green.

## 5. Marketing: where is the money going?
Within the 60-day window **every campaign has ROAS < 1** (simulated LTV is only partly realised), so the comparison is relative:
| | Spend | CPI | Cost / payer | ROAS |
|---|---|---|---|---|
| Best: camp_IN_1 | $431 | $0.19 | $14.4 | 0.72 |
| Best: camp_IN_2 | $480 | $0.21 | $17.8 | 0.64 |
| Worst: camp_US_1 | $12,657 | $2.89 | $50.2 | 0.13 |
| Worst: camp_US_2 | $9,994 | $2.28 | $38.4 | 0.17 |

* Low-CPI markets (IN, TR, BR) convert payers 3× more cheaply even though their retention is weaker; the two US campaigns absorb ~48 % of total spend at the lowest ROAS.
* **Action:** shift budget from US/GB/DE toward IN/TR/BR until marginal ROAS equalises; extend the horizon to D90 LTV before declaring any campaign unprofitable.
