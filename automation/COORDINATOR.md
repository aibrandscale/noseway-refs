# Noseway coordinator — every 30 minutes

The user authorized: 10 NEW adult nose-strip images every 48 hours, Meta refresh
every 30 minutes, automatic Rework with the exact feedback, date-filtered metrics
and collapsible batches in the existing BOFU Sheet. No Meta creation, activation,
budget changes or ad edits. Do not run the legacy generator/topup or other routines.

Read automation/RULES.md and scripts/pipeline.py. The repository is
aibrandscale/noseway-refs, branch main. Start with git pull --rebase. Never overwrite
the whole repository from an older snapshot. Stage exact changed paths, never
git add -A. Never read, copy or print a kie.ai key: GitHub Actions already has it.
The cloud cannot reach kie.ai; image jobs run in .github/workflows/generate-queue.yml.

## 1. Read the real Sheet and update Meta data

Use the Google Drive connector to read spreadsheet
15qFvJLrxhoc5S38Dr1fFQS0Tc9RbpYpr9ZldLFUMjOM, tab BOFU, including the selected period
in B2 and the columns Реклама, Одобрение and Корекции. Locate the header by labels
(legacy row 2, new row 4). Ignore Batch/Meta section rows. Approval values are
For Review, Approved, Rework, Rejected. Read hidden key column L if available;
otherwise match exact current name AND image link against sheet.json. Never guess
between duplicate names. Always use current feedback; an empty Rework instruction
requires attention and does not trigger speculative paid generation.

Facebook connector: account 988945020801127, ad level. Use available documented
tool parameters and pagination. Read maximum/lifetime metrics for ads whose
adset_name contains bofu (case-insensitive). Fields: id, name, adset_name,
campaign_name, effective_status, amount_spent, cost_per_result, results,
website_purchase_roas, cpc, impressions. Do NOT request purchase_roas or clicks.
Update ONLY the corresponding kind=meta rows in sheet.json, retaining creative
rows and their batch_id, qa, generation_id and other fields. This is the
Whole period view. Keep null for unavailable CPA/ROAS/CPC. Do not fabricate zero
when the query failed. Set updated_at only after a successful read.

Also query daily data with a custom time_range (since=until=YYYY-MM-DD) or the
connector's documented equivalent/insights tool, time_increment=1 when supported.
Fetch the account's actual timezone; dates refer to that timezone, not the laptop.
On first run backfill the last 7 completed days plus today. Subsequently refresh
today, yesterday and the selected date (B2: DD/MM[/YYYY], ISO, or Whole period).
Persist successful days in metrics_daily.json:
{"updated_at":"ISO","account_timezone":"actual IANA timezone","dates":{
"2026-09-08":{"complete":true,"updated_at":"ISO","rows":[
{"key":"ad id","results":0,"spend":0,"cpa":null,"roas":null,"cpc":null,"impressions":0}]}}}
Keep other dates. Only mark complete=true after the entire day's paginated query
succeeded. No activity on a confirmed day may be 0, failed/unavailable data may
not. Do not derive historical daily metrics by subtracting lifetime snapshots.
If the connector cannot query a date, record the limitation, preserve the previous
successful data and report it; do not claim date filtering is fully updated.

## 2. Enqueue exact Rework requests immediately

For each Rework with nonempty Корекции: inspect the current image and read its copy.
Create /tmp/rework-<key>.json with key, base_link (current link), feedback (exact
user text), title, prompt, copy, framework. Preserve the concept and copy except
where feedback or required packaging/offer rules require a change. The prompt
must specify one hero pouch and an exact list of ad text. Do not invent product
claims. Execute python scripts/pipeline.py rework /tmp/rework-<key>.json.
The request ID fingerprints key+image version+feedback, preventing duplicate
charges every 30 minutes. Existing Approved/Rejected/For Review rows are not
regenerated. Record Rejected in retired.json if not already recorded but retain
the row and its batch history; don't delete or replace it.

## 3. Create 10 genuinely new concepts when the 48-hour batch is due

Run python scripts/pipeline.py due. If due=true, author exactly 10 distinct
concepts, using automation/RULES.md. Read past jobs/requests and current creatives
to avoid recycling them. Do not reuse the old multi-pouch prompt library. New
batch means ADD 10 new creatives, not top up the sheet to 10 total. Write a JSON
array in /tmp/noseway-batch.json, each item {title,prompt,copy,framework}.
Keep each concept prompt below 3000 characters, with a concise exact text list.
Copy includes “Вземи 2 опаковки, третата е подарък” and ends with the nose PDP URL.
Run python scripts/pipeline.py batch /tmp/noseway-batch.json. This atomically
identifies the 48-hour batch and prevents duplicate batch creation. Preserve all
existing batches. No catch-up burst of missed batches.

Commit changed sheet.json, metrics_daily.json, retired.json and the exact newly
created jobs/requests and jobs/batches files. Pull --rebase and push main; if
someone edited the same shared JSON, resolve by reapplying only your field changes
to the fresh data, never reset away another writer's changes. The push starts the
image worker; explicitly dispatch generate-queue.yml via GitHub if push did not
start it. Never enable legacy topup.yml.

## 4. Inspect every candidate and publish only correct results

Inspect existing jobs/results immediately, including results from a previous run.
For requests submitted this run, wait for the GitHub worker to finish, up to 20
minutes; read compact run status periodically, then git pull --rebase. Do not mark
unfinished requests successful. The next 30-minute run resumes them. Never issue
a new paid request when a saved taskId is merely still pending.

For each generated candidate without an accepted/rejected matching review:
open the real packaging image AND the generated JPG at full size. Compare logo,
face, pack text, strip, number of pouches, every Bulgarian ad word and the offer.
For Rework also compare to the old creative and exact feedback. A text-only or
file-exists check is insufficient. Use available image-viewing tools.

Write /tmp/qa.json with {id,attempt,link,decision,feedback,checks}. decision is
accept/retry/reject; feedback is specific visual evidence. For accept, checks must
contain packaging,logo,one_pack,bulgarian_text,offer,feedback_applied, all true.
Run python scripts/pipeline.py review /tmp/qa.json. A retry must describe precisely
what the image model should fix; at most 3 attempts total. Persist the review and
push; it starts another worker attempt. Never accept a bad/uncertain image just
to reach 10. If quota or QA blocks a request, report the exact unmet count.

Immediately before publishing a Rework, re-read its live approval and feedback.
Publish only if it is still Rework, the feedback is identical, and the original
link/copy are unchanged. If the user changed/cancelled the request, retain the old
creative and report the candidate as superseded. For valid accepted candidates,
run python scripts/pipeline.py publish <id>. It replaces the SAME creative row for
Rework; new batch requests append. Every replacement has a unique new image URL.
Commit sheet.json and exact jobs/reviews / jobs/published paths, rebase and push.
The installed Apps Script sync changes the approval to For Review and clears old
corrections only when the new image/copy version arrives. Never set Approved for
the user. Do not alter the Sheet layout yourself; sheets/noseway.gs owns it.

## 5. Finish with truthful status

Check source readback. Record a concise private run result: Meta update time,
daily dates refreshed, new batch count (target 10), Rework received/completed,
QA retries/blocked requests, and any failure. Do not expose secrets. Stay quiet
when nothing changed; notify only about a new batch, completed Rework, exhausted
credits, failure, or needed user action. Do not notify ordinary unchanged metrics.
Stop within 25 minutes so the next scheduled run can continue safely.
