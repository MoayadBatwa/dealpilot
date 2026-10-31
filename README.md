# DealPilot AI

A B2B presales platform for HUMAIN AI Builder Hackathon, Challenge 3: Autonomous Enterprise, with deterministic commercial controls and an optional live LangGraph workflow with Groq or OpenAI. **The current CRM, customer data, products and manager roles are simulated. The project does not yet connect to production customer systems.** The primary sales workflow uses real AI analysis when configured. Admin test scenarios require no API key. AI mode sends submitted inquiry data to the selected provider only when explicitly executed; there are no external CRM, email or payment integrations.

## macOS setup

Python 3.11+ is recommended; this milestone also runs on the available macOS Python 3.9.6. From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501). The virtual environment already exists in the delivered workspace. No editable install is required: pytest uses `src` via `pyproject.toml`, and `app.py` loads the local package.

Optional database override:

```bash
export DEALPILOT_DB=/tmp/dealpilot-demo.sqlite3
python -m streamlit run app.py
```

The dashboard reads the local `.env` automatically; shell variables take precedence. A shareable environment template is not required. SQLite files and `.env` are ignored by Git. The database has no credentials. Do not put real customer data in this demo. First launch seeds the database; subsequent launches safely replay existing seed requests. Use a new database path for an isolated fresh demo without deleting files.

## Sales workspace: the live demo journey

The app has four business pages in the sidebar. All data is fictional and clearly labeled; no external CRM updates, emails or contractual commitments are made.

1. **Dashboard** shows saved deals, offers ready, pending approvals and finalized offer value in SAR. These metrics use persisted records, include sample data and historical revisions, and are not revenue. Recent deals have a **View deal** action. Click **New Opportunity** to start a separate inquiry.
2. **New Opportunity** asks for company name, sector and the customer's natural-language inquiry. Include user count, supported features, budget including VAT, a natural-language delivery target and discount. Click **Analyze opportunity** to run the existing real Groq/LangGraph workflow. A quiet connection indicator identifies the configured provider. If no provider is configured, the action is disabled with a clear explanation; no AI output is invented.
3. Progress reports actual node attempts as processed. The saved deal timeline separately checks evidence for: understanding the inquiry, recommending a solution, checking terms, preparing a proposal, saving the deal and checking records. Steps that have not executed remain **Not reached**. The result gives a business status and a next action. Missing information, scope issues, infeasible delivery and budget shortfalls are shown as review states rather than successful offers.
4. **Deals** combines persisted AI inquiries (including those that stopped before a CRM opportunity existed) and CRM opportunities without counting the same AI run and opportunity twice. Search by company or filter by status/source, then use **Open a deal**. Review requirements, recommended solution, itemized SAR quote, discount, VAT, delivery window, policy findings, proposal and CRM activity. Raw IDs, JSON, verification findings and the real node trace are in **Advanced Details**.
5. **Approvals** shows customer, requested discount, amount including VAT, discount amount, reason and risk. Select the demo **Manager** role to **Approve** or **Reject**. Sales representatives cannot decide. Approval applies to the exact quote and never finalizes the offer by itself. Click **Resume Workflow** after approval: AI deals use the existing saved-state resume path; structured samples use the existing CRM finalization guard. Both revalidate commercial terms. The finalized canonical proposal is then visible in Deals. Rejected offers remain drafts and need revised terms.
6. To change an existing AI inquiry, open the deal and click **Revise inquiry**. The form is prefilled. Changed details increment the revision; unchanged resubmissions reuse the same request. Earlier revisions remain in the database. **Retry saved inquiry** continues failed or interrupted runs using the existing stable request keys, without inventing a new deal. **New Opportunity** starts a separate form.

For a presentation, use a fictional inquiry such as:

> We need CRM integration and Arabic / English support for 10 users. Our budget is SAR 100,000 including VAT. Please deliver within 60 calendar days. We request a 15% discount.

This should reach management review when supported extraction and validation succeed; model or provider failures remain explicit. Review the draft, approve as Manager, resume and inspect the finalized offer. Never describe a draft or failed analysis as approved.

**Admin / Developer Tools** is a collapsed sidebar section containing Catalog, Company Policies, Audit Log, Verification and Test Scenarios. The 11 deterministic cases cover normal lead, missing/insufficient budget, unapproved discount, infeasible timeline, unsupported scope, revised requirements, duplicate inquiry, CRM outage, injection text and price-floor violation. These are simulations, separate from the primary real-provider workflow. Run them from this section; no API key is needed. All existing audit records and SQLite data are retained.

## Commercial rules

- Currency SAR; all commercial arithmetic uses `Decimal`, with two-decimal half-up rounding. UI budget/discount fields accept decimal strings, never binary floats.
- Seven fictional catalog entries include CRM, REST integration, Arabic/English, analytics, customer service, migration and regulated-workflow configuration.
- Annual software prices are per user where specified; implementation services are one-time. Quote subtotal is before discount; discount is rounded once on subtotal; the simulated 15% VAT assumption is applied to net. Budget is compared with VAT-inclusive total. This is a demo tax assumption, not a tax compliance engine.
- Dependencies are added automatically, then sector eligibility, maximum users, exclusions, price floors and delivery are validated. Delivery adds selected lead times sequentially, including dependencies.
- Policy `2026-10-31.v1`: above 10% requires management approval for the exact quote. Floors cannot be overridden by approval. Missing budget and unsupported requirements stop offer generation and create follow-up tasks.
- Finalization recomputes from persisted inquiry/catalog data, checks the stored quote and the exact management approval, and only then writes FINAL records. User notes are untrusted stored data; they are excluded from proposals and never executed.

## Code map

| File | Responsibility |
| --- | --- |
| `src/dealpilot/models.py` | Pydantic domain schemas |
| `database.py` | SQLite records, atomic per-write audit and idempotency ledger |
| `catalog.py` | Explicit fictional products and constraints |
| `policies.py` | Versioned commercial rules |
| `qualification.py` | Structured requirement matching and dependencies |
| `pricing.py` | Exact quote arithmetic and stable quote fingerprints |
| `crm.py` | Simulated CRM tools, approval decisions and finalization |
| `proposal.py` | Validated-data-only proposal template |
| `verification.py` | Read-only persisted record reconciliation |
| `simulation.py` | Seed scenarios and deterministic orchestration |
| `app.py` | Four-page navigation and enterprise theme |
| `ui_pages.py`, `ui_components.py` | Business pages, readable quotations and secondary admin tools |
| `ui_data.py` | Read-only joins of AI runs, CRM records and current approval/offer state |
| `agent_ui.py` | Primary natural-language intake, actual progress and revision controls |
| `tests/` | Pricing, policy, persistence, idempotency, tampering and UI checks |

All mutations use stable keys. A SQLite transaction commits the record, its operation ledger entry and audit event together. Reusing a key with a different payload raises an error. A workflow spans multiple transactions: interruption can leave partial progress, which the verifier identifies for offer-related records; this is not a distributed transaction system. Audit timestamps are UTC. Decimal amounts serialize as strings to preserve precision.

## Live AI setup (optional)

The installed environment is Python 3.9.6. LangGraph `0.6.11`, LangChain Core `0.3.86`, and OpenAI SDK `1.109.1` are pinned to keep that environment compatible. Python 3.11+ is recommended for new environments, but only the installed 3.9.6 interpreter has been exercised here. `requirements.lock.txt` captures the tested resolved environment. No LangChain OpenAI adapter is needed: graph specialists use the OpenAI-compatible SDK with a fixed provider endpoint. Groq requests go to Groq, not OpenAI.

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The dashboard automatically reads the ignored project `.env` without modifying shell environment variables. Configure it locally (never put credentials in `.env.example`):

```dotenv
DEALPILOT_LLM_PROVIDER=groq
GROQ_API_KEY=<your-local-key>
GROQ_MODEL=openai/gpt-oss-120b
```

Your existing Groq configuration is sufficient: when `DEALPILOT_LLM_PROVIDER` is absent or blank, a configured Groq key selects Groq; otherwise OpenAI is selected. To explicitly use OpenAI, set `DEALPILOT_LLM_PROVIDER=openai`, `OPENAI_API_KEY` and optionally `OPENAI_MODEL`. Environment variables override `.env`. Provider failures never silently switch providers. `DEALPILOT_ENV_FILE` can select another local configuration file. Programmatic services use shell configuration by default, or accept `get_provider(load_local_env=True)` explicitly.

Groq defaults to `openai/gpt-oss-120b`, which supports strict structured outputs. Despite the model's `openai/` prefix, requests go to Groq's endpoint. Missing selected-provider credentials disable AI execution while deterministic simulation remains available. The UI never displays or persists credentials, and SDK errors are sanitized. Live requests transmit submitted fictional inquiry data to the selected provider.

### AI walkthrough

Use the four-page sales journey above: **New Opportunity → Deals → Approvals → Resume Workflow → Deals**. AI drafts remain drafts and are stored separately from the canonical CRM proposal. Only the existing guarded finalization path can produce a final demo offer. Advanced Details keeps the actual graph trace available to hackathon judges without placing it in a salesperson's primary flow.

### Graph architecture and safety boundaries

`AgentWorkflow.graph` is a real compiled LangGraph `StateGraph`. A deterministic supervisor selects conditional edges, tracks a maximum of 12 supervisor visits and stops on explicit statuses. LangGraph also has a recursion limit of 32. The three model nodes allow at most two attempts each; OpenAI SDK automatic retries are disabled and requests have a 30-second timeout and a 2,500 completion-token ceiling. CRM failures require an explicit safe retry.

| Node | Work and authority |
| --- | --- |
| Intake / qualification | Live structured extraction with strict Pydantic schemas. Missing facts remain null. Numeric values must match exact numeric source substrings; requirements require verbatim source evidence. |
| Supervisor | Routes by phase, missing facts, findings and failures; it cannot approve or set prices. |
| Solution advisor | Retrieves the small catalog and proposes product IDs and requirement-to-capability matches. Code rejects unknown IDs, missing dependencies, extra products and unsupported matches. |
| Commercial | Existing eligibility, delivery, price-floor, budget and Decimal pricing services; no model arithmetic. |
| Proposal | Live model organizes immutable validated fact blocks into professional sections. Every block must appear exactly once; no arbitrary promises or amounts are accepted. This is constrained extractive composition, not unrestricted copy generation. |
| Execution | Calls the existing `simulation.run` orchestration and its guarded CRM tools with stable keys. It rechecks that the graph quote has not changed. AI drafts use a separate audited record type. |
| Verification | Existing read-only reconciler reads persisted CRM/approval records, plus current-run linkage checks. It does not trust model assertions of success. |
| Resume | Loads the saved run, checks exact management approval, calls `CRM.finalize`, then verifies persisted results. No model participates. |

Checkpoints are application-managed JSON snapshots in the existing audited SQLite record store (`agent_run`), saved after every node attempt. This is not LangGraph's native checkpointer/interrupt API: a pending workflow ends cleanly, and a new graph invocation loads its durable state on resume. The existing database/schema and seed records are preserved; new `agent_run` and `agent_proposal` record kinds are additive. Partial CRM writes can be safely replayed through existing idempotency keys. This is not transactional execution across an entire graph.

Trace events contain actual node name, input summary, attempted tool names, outcome/error, attempt number and measured elapsed milliseconds. Composite CRM execution is honestly labeled `simulation.run (guarded CRM tools)`; it does not invent individual model/tool reasoning steps. No chain-of-thought, raw SDK errors or credentials are recorded. The UI constructs a real `GroqProvider` or `OpenAIProvider`; deterministic test doubles exist exclusively under `tests/`.

### Testing

Recorded submission validation snapshot: **164 passed, 1 warning**. The warning is an upstream LangChain serializer pending deprecation.

```bash
python -m pytest -q
python -m pytest tests/test_agents.py -q
python -m pip check
```

Graph evaluation uses an explicitly labeled scripted TEST DOUBLE, not real AI. It covers normal and blocked routing, strict parsing, missing credentials, source evidence, unsupported products, injection text, proposal commitments, approval gates, persisted resume, quote tampering, duplicate execution, bounded retries and provider/tool failures. One HTTP transport test exercises actual OpenAI SDK schema parsing without network calls. AppTest checks that missing-key AI mode is disabled and deterministic simulation still works.

Implementation references: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).

## Groq provider integration

The dashboard uses `GROQ_API_KEY` and `GROQ_MODEL` from the local `.env`. `python-dotenv` is pinned to `1.1.1`; no Groq-specific SDK is necessary. Provider endpoint and schema behavior are covered by offline transport tests. Existing pricing and approval guards are unchanged.

A real Groq smoke check using `openai/gpt-oss-120b` successfully ran intake, solution selection, proposal composition, deterministic commercial checks, CRM execution and verification. The synthetic 15% discount case stopped at `APPROVAL_PENDING`, with no errors or verification discrepancies. No approval was granted. The check used an isolated temporary SQLite database and did not alter the demo CRM.

To explicitly repeat that live check (uses API quota and sends synthetic inquiry data):

```bash
python scripts/smoke_ai.py
```

The offline test suite does not run this script or the existing standalone `test_qroq.py`.

References: [Groq OpenAI-compatible API](https://console.groq.com/docs/openai), [Groq strict structured outputs](https://console.groq.com/docs/structured-outputs).

## Deal brief, decision evidence and approval resume

Every deal opens with a **Deal brief** showing the company, a descriptive opportunity title (the existing CRM has no separate opportunity-name field), industry, requirements, customer budget, requested timeline, requested discount and a business status. Product reasons cite the catalog capability that matches a recorded requirement or the dependency that requires that product. **Why this decision?** explains the actual VAT-inclusive total, budget fit, delivery window and sales discount threshold. Gaps and risks come from customer omissions, unsupported catalog needs and recorded policy findings; no model is asked to invent an explanation.

The business status uses saved evidence:

| Business status | Meaning |
| --- | --- |
| Needs Information | Customer data is incomplete; collect and revise it. |
| Analyzing | Qualification is in progress or an interrupted run needs continuation. |
| Ready for Review | A draft or final offer needs review; older final records without a matching saved check are not called completed. |
| Pending Approval | An exact-quote management request is pending. The offer remains a draft. |
| Approved | Management approved the exact quote, but finalization/resume is still required. |
| Rejected | The quote was rejected; revise terms before trying again. |
| Blocked | Scope, budget, delivery, configuration or record integrity prevents proceeding. |
| Completed | Valid final quote, proposal and CRM status exist, with a successful saved verification covering the current records and catalog/policy context. This is completion of the demo presales process, not a signed contract or won revenue. |
| Failed | A provider/tool operation or record check failed; investigate or retry safely. |

**Recommended Next Action** provides a working context-specific action: update customer details, review an approval, resume, retry the saved inquiry, check saved records, investigate record checks or download a verified final proposal. Completed actions retain the selected deal even if its status changes a list filter.

The visible **Workflow timeline** has eight stages: Inquiry received, Requirements analyzed, Solution matched, Quote validated, Approval requested, Proposal prepared, CRM updated and Verified. A successful node attempt alone is not proof of a successful business result. For example, unsupported scope does not complete Solution matched, a computed quote outside budget does not complete Quote validated, and creating an opportunity alone does not prove requirements analysis or a completed CRM update. Steps display Completed, Pending, Skipped, Blocked or Failed based on persisted evidence. Approval requested means the request was saved, not that approval was granted. The timeline groups business stages; the real graph may draft the proposal before requesting approval. Only timestamps available from actual audit records are shown; trace-only steps have no invented time. Advanced Details preserves the original execution order and technical evidence.

### Safety and persistence details

Approval decisions and finalization share the same read-only deterministic quote revalidation. Both Approve and Reject require the management role and an exact quotation linked to the persisted opportunity revision. Finalization additionally checks the approval's quote ID, record ID, opportunity and management decision. Cached completed resumes revalidate authorization and recheck changed records rather than returning an obsolete success.

Verification reports are additive records in the existing SQLite store; the schema and old data are not reset. A fingerprint binds each report to the opportunity, inquiry, quotation, canonical proposal, approval, catalog and policy version. Changes invalidate the current verification badge. Report revisions allow repaired records to be checked again; identical repeated checks are idempotent. The existing verifier reconciles the database globally, so a report may surface discrepancies from another saved deal. Raw discrepancy IDs remain in Advanced Details or Admin tools.

Resume continues from application-managed persisted graph state, **not** LangGraph's native checkpointer/interrupt API. This is the existing genuine resume mechanism: a new graph invocation runs only the resume and verification nodes. SQLite commits remain atomic per tool write, not across the entire graph. The management role selector remains a demo authorization control rather than production authentication. No new dependency, price rule, provider or external action was introduced for these improvements.

If a final offer's verification fails, **Recheck saved records** uses the saved run to execute verification only after the discrepancy has been resolved. It does not restart model nodes or replay CRM finalization. A fresh successful check can resolve an older failed-verification status; evidence of a failed provider or tool operation still requires its explicit retry path.

## Customer timeline normalization

Intake normalizes customer delivery timing **before** checking required fields. Clear expressions such as `six weeks` and `a six-week delivery timeline` become 42 calendar days while preserving the original phrase and precision. Groq still runs once for intake; an optional verbatim `timeline_source` helps preserve contextual wording. The model never computes authoritative deadlines. A null or inconsistent model interpretation cannot erase a clear deterministic parse. Contradictions or ambiguity in the actual customer wording still produce clarification and prevent CRM/quote execution.

Supported, bounded forms include:

- Positive whole English number durations (digits and words through hundreds), including `six weeks`, `6 weeks`, `six-weeks`, `forty-two days`, and days/weeks/months/years. Weeks are seven days.
- Arabic/Persian-Indic numerals, common unvowelled Arabic number words one through ten, and common day/week/month/year singular/plural/dual units: for example `خلال ٣ أسابيع`, `خلال ستة أسابيع`, `خلال شهرين`, `بعد سنة`.
- Explicit Gregorian ISO dates and English month-name dates with a year, such as `by December 15, 2026`; common Arabic Gregorian month names are also recognized.
- `next Friday` (and the other English weekdays), common Arabic next-weekday wording such as `الجمعة القادمة`, and `end of next month` / `نهاية الشهر القادم`. “Next weekday” means its next strictly future occurrence, including seven days ahead on that same weekday. The convention is saved as a note for review.
- `ASAP` / `as soon as possible` and common Arabic urgency wording are retained as urgency, **without inventing a date or requested_days**. Approximate or preferred targets (`approximately`, `ideally`, `تقريبا`, `يفضل`) retain their precision and ask for a firm target instead of silently hardening it. `within`, `by`, and `no later than` retain a latest-deadline constraint.

Each new run records a timezone-aware `received_at` once, converted to `Asia/Riyadh`. Retries/replays reuse it; a new revision records its own receipt time. Calendar months/years are added to that local date, clamping the destination day to month end where needed. Thus two months from 31 October 2026 is 31 December (61 days); two months from 31 January 2027 is 31 March (59 days). There is **no fixed 30-day month or 365-day year approximation**. Absolute/relative deadlines derive their positive integer day window from the recorded local inquiry date. The existing feasibility engine still consumes that inquiry-time window; approval does not create a contractual calendar-date promise.

Normalized metadata preserves the source/original phrase, kind, duration value/unit, Gregorian target date where derivable, precision, constraint, explicit-confirmation flag, reference timestamp/timezone, clarification questions and notes. Explicit confirmation is only recorded for recognized affirmative wording; an ordinary target or successful extraction is not human approval or confirmation. Metadata is saved in the existing run checkpoint and, when execution occurs, an audited `timeline` record keyed to the same persisted inquiry/revision. The existing `Inquiry` model and its quote hash format are unchanged. The Deal Brief keeps its layout and displays the source wording/precision beneath the requested timeline; specific clarification questions appear through existing findings and gaps views.

## What's Next?

The following priorities are planned future development, not implemented production capabilities:

- **Real CRM Integrations:** Salesforce, HubSpot, and secure enterprise CRM synchronization.
- **Enterprise Approval Management:** Authenticated roles, permissions, notifications, and auditability.
- **Multilingual AI Intelligence:** Improved Arabic/English timeline extraction, clarification workflows, and alternative catalog-grounded recommendations.
