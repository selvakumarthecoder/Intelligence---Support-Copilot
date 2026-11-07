# Intelligence & Support Copilot

## Overview

The Intelligence & Support Copilot is a customer intelligence and support automation project built using Python, SQL, machine learning, Retrieval-Augmented Generation (RAG), and an LLM-based refund agent.

The project is divided into four parts:

- **Part A – Data Foundation:** Data cleaning, validation, SQLite database creation, and SQL analysis.
- **Part B – Customer Segments and Lapse Prediction:** RFM analysis, customer segmentation, and lapse prediction.
- **Part C – Support Ticket Triage:** Ticket classification, priority assignment, routing, and token-budget handling.
- **Part D – Policy QA and Refund Agent:** Policy question answering, refund decisions, tool execution, checkpointing, and recovery.

## Reproduce

Run the following commands from the project root directory.

### 1. Create a virtual environment

```powershell
python -m venv .venv
```

### 2. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Generate the input data

```powershell
python generate_data.py
```

### 5. Run the complete project

```powershell
python run_project.py --run-all
```

This command executes Parts A, B, C, and D.

**Important:** The full pipeline regenerates project outputs. Part D runs the seven refund scenarios again, replaces `outputs/agent_runs.jsonl`, appends entries to `outputs/refund_ledger.jsonl`, and creates or updates checkpoint files in `state/`. Do not run this command over an existing submission/evidence copy unless you intend to regenerate those artifacts. For a fresh reproduction, use a separate working copy and retain the original verified outputs.

### 6. Check the existing artifacts

```powershell
python run_project.py --check-only
```

This checks required artifact presence and the scenario/run record counts. It does not rerun the pipeline or validate every artifact's contents.

### 7. Validate Part A data

```powershell
python src/validate_data.py
```

The validation script checks the cleaned datasets and SQLite database.

### 8. Check Python syntax

```powershell
python -m py_compile run_project.py
```

The notebooks in `notebooks/` provide the step-by-step implementation and analysis for each project part. Do not rerun notebook cells that regenerate data or outputs over the verified submission artifacts unless regeneration is intended.

## Part A – Data Foundation

Part A prepares the raw Instamart data for analysis and creates a SQLite database.

### Data cleaning and validation

| Dataset | Cleaned records |
|---|---:|
| Customers | 1,200 |
| Products | 40 |
| Orders | 12,309 |

The raw orders dataset contained 13,084 rows. Duplicate order records were removed during cleaning.

Final order status counts:

| Status | Records |
|---|---:|
| Completed | 11,110 |
| Cancelled | 1,199 |
| Pending | 0 |

### Database

The SQLite database `data/instamart.db` contains three tables:

- `customers`
- `products`
- `orders`

### SQL analysis

Seven SQL queries were implemented using filtering, joins, subqueries, CTEs, window functions, and cumulative revenue calculations.

| Query | Description | Result rows |
|---|---|---:|
| Q1 | WHERE and HAVING | 30 |
| Q2 | Three-table JOIN | 30 |
| Q3 | Scalar subquery | 11 |
| Q4 | LEFT JOIN | 25 |
| Q5 | CTE | 550 |
| Q6 | Ranking window functions | 1,175 |
| Q7 | Daily and cumulative revenue | 183 |

**Completed order revenue:** INR 2,998,668.80

The Part A validation script completed successfully with all checkpoints passed.

## Part B – Customer Segments and Lapse Prediction

Part B uses customer purchase history to calculate RFM metrics, identify customer segments, and predict customer lapse.

### RFM analysis

The RFM snapshot date is 1 October 2025.

| Metric | Result |
|---|---:|
| Customers | 1,175 |
| Average frequency | 9.46 |
| Average monetary value | INR 2,552.06 |
| Median recency | 19 days |

### Customer segmentation

K-Means clustering was evaluated for K values from 2 to 8. Four clusters were selected using the elbow method, silhouette score, and business interpretability.

| Segment ID | Segment name | Customers |
|---:|---|---:|
| 0 | Regular Low-Value | 436 |
| 1 | Premium | 138 |
| 2 | Loyal Active | 419 |
| 3 | At-Risk | 182 |
| | **Total** | **1,175** |

PCA explained approximately 63.4% and 21.8% of the variance in the first two components.

### Lapse prediction

The lapse prediction task uses a 1 September 2025 cutoff.

| Metric | Result |
|---|---:|
| Eligible customer cohort | 1,156 |
| Lapsed customers | 443 |
| Lapse rate | 38.32% |
| Training records | 924 |
| Testing records | 232 |
| Baseline accuracy | 61.6% |

The modelling workflow includes preprocessing pipelines, Logistic Regression, and Random Forest model selection.

The saved model and retention list are:

- `outputs/lapse_model.joblib`
- `outputs/retention_list.csv`

The retention list contains the ten highest predicted lapse probabilities.

## Part C – Support Ticket Triage

Part C classifies incoming support tickets and assigns priorities and routing destinations.

The implementation includes:

- PII redaction for email addresses, phone numbers, and order IDs.
- Ticket classification using structured LLM output and keyword fallback.
- Invalid-output and long-input handling.
- Priority assignment and support routing.
- Token-budget controls and retry handling.

### Ticket processing results

A total of 164 tickets were processed.

| Status | Tickets |
|---|---:|
| Classified JSON | 135 |
| Classified keyword | 12 |
| Flagged invalid output | 9 |
| Skipped empty | 4 |
| Flagged long | 4 |

### Routing results

| Route | Tickets |
|---|---:|
| Support queue | 102 |
| Security team | 34 |
| Human review | 17 |
| Premium desk | 11 |

### Classification performance

| Method | Classified tickets | Accuracy |
|---|---:|---:|
| Zero-shot | 147 | 85.7% |
| Few-shot | 147 | 100% |

The project also includes a budget demonstration in `outputs/triage_budget_demo.csv`.

**Budget limitation:** The budget demonstration used 6,038 tokens against a nominal 6,000-token budget. The implementation checks the budget before a model call, so the final call can cause a small overshoot.

## Part D – Policy RAG and Refund Agent

Part D combines policy retrieval, question answering, and an agent that uses tools to handle refund requests.

### Policy RAG

The policy assistant uses five policy documents divided into 15 chunks, with a chunk size of 40 words and an overlap of 10 words.

The evaluation included 14 policy questions.

| Evaluation | Expected facts found | Unanswerable fallback |
|---|---:|---:|
| With overlap | 12/12 | 2/2 |
| Without overlap | 10/12 | 2/2 |

Chunk overlap improved retrieval where important policy information crossed chunk boundaries.

### Seven-scenario refund agent evaluation

The agent was tested against seven predefined scenarios.

| Scenario | Expected outcome | Actual outcome | LLM calls | Tokens used | Result |
|---|---|---|---:|---:|---|
| S1 | REFUND | REFUND | 5 | 1,277 | PASS |
| S2 | REFUND | REFUND | 5 | 1,277 | PASS |
| S3 | ESCALATE | ESCALATE | 5 | 1,264 | PASS |
| S4 | DENIED | DENIED | 4 | 909 | PASS |
| S5 | DENIED | DENIED | 3 | 565 | PASS |
| S6 | NOT_FOUND | NOT_FOUND | 2 | 224 | PASS |
| S7 | FALLBACK_MAX_ITERATIONS | FALLBACK_MAX_ITERATIONS | 6 | 3,456 | PASS |

**Seven-scenario acceptance result: 7/7 passed.**

### Stop-safely demonstrations

| Demonstration | Result | Details |
|---|---|---|
| Token limit | FALLBACK_TOKEN_LIMIT | Stopped after 2 model calls; `get_order` was the executed tool |
| Timeout | FALLBACK_TIMEOUT | Stopped with 0 model calls and no tools executed |

### Crash-and-resume demonstration

The agent was deliberately interrupted after its second tool execution.

The checkpoint was saved, and the agent resumed successfully using `resume_agent()`.

The resumed execution completed the refund workflow with a final result:

`REFUND: INR 128.25 issued.`

Tools executed during the crash-and-resume run:

1. `get_order`
2. `search_policy`
3. `calculate_refund`
4. `issue_refund`

The final resumed execution used five model calls.

### Agent tools

The refund agent uses the following tools:

- `get_order`
- `search_policy`
- `calculate_refund`
- `issue_refund`
- `escalate_to_human`

### Part D output files

- `outputs/agent_runs.jsonl`
- `outputs/refund_ledger.jsonl`
- `data/raw/agent_scenarios.csv`
- `state/` – saved agent checkpoints

## Limitations and Next Steps

### Current limitations

1. **Lapse prediction:** Model performance is limited by the available historical data and the selected prediction cutoff.
2. **Classification budget:** Token usage can slightly exceed the nominal budget because the budget is checked before each model call.
3. **Refund ledger:** The ledger is append-only and does not currently enforce idempotency. Repeated execution can create duplicate ledger entries.
4. **Token-limit handling:** The token-limit demonstration exceeded its nominal 200-token limit by 54 tokens before stopping.
5. **RAG retrieval:** Policy retrieval can miss facts that cross chunk boundaries when overlap is disabled.
6. **LLM dependency:** Classification and agent decisions depend on model responses and require appropriate error handling and human review.

### Next steps

- Improve lapse prediction using additional customer behaviour features.
- Introduce stricter token-budget enforcement.
- Add idempotency protection to refund execution.
- Improve policy retrieval using more advanced chunking and retrieval methods.
- Expand testing with additional support scenarios.
- Strengthen monitoring, logging, and human escalation workflows.
