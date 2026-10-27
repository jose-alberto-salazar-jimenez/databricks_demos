# Demo talk track: CI/CD for a data engineering pipeline with Declarative Automation Bundles

About 35 minutes. Shows a supply chain lakehouse (simulated Salesforce, Excel, ERP, logistics and plant IoT sources
-> Lakeflow Spark Declarative Pipeline bronze/silver/gold -> Lakeflow Job) promoted from a dev workspace to a prod
workspace with GitHub Actions.

| Environment | Workspace | Catalog | Deployed by |
| --- | --- | --- | --- |
| dev | https://dbc-3fb58c7d-ac94.cloud.databricks.com | `dev_demo` | you (Cursor) and `jasj-demo-sp-cicd-dev` (CI) |
| prod | https://dbc-df52510d-0fb6.cloud.databricks.com | `prod_demo` | `jasj-demo-sp-cicd-prd` (CD, after approval) |

---

## Before the demo (about 15 minutes)

- [ ] In Cursor: `git checkout main && git pull --prune`, then `cd cicd_dabs__data_eng__supply_chain`
- [ ] `databricks auth login --host https://dbc-3fb58c7d-ac94.cloud.databricks.com --profile dev`
      and check it with `databricks current-user me -p dev`
- [ ] Pre-deploy your personal dev copy once so the live deploy is fast: `databricks bundle deploy -t dev -p dev`
- [ ] Confirm `main` is at the baseline (reset with Act 8 if a previous demo left changes):
  - `databricks.yml`, prod target: `job_schedule_cron: "0 0 6 * * ?"`
  - `gold_delivery_performance` has no `late_shipments` / `avg_freight_cost` columns
- [ ] Optional: prepare a local branch `demo/broken-reference` (do not push yet) for Act 4b
- [ ] Browser tabs: GitHub repo + Actions tab; dev workspace (Jobs, Catalog `dev_demo`);
      prod workspace (Jobs, Catalog `prod_demo`)
- [ ] Make sure prod has data: the daily schedule has run at least once, or trigger the prod job manually
- [ ] Check GitHub settings: `protect-main` ruleset active; `prod` environment has Required reviewers ticked

---

## Act 1: The problem and the setup (2 min)

**Say:**
- "Data teams often promote pipelines by hand: export from dev, click around in prod, hope nothing drifts.
  Today everything (tables, pipeline, job, permissions) lives in Git and is promoted by CI/CD."
- "Two workspaces, dev and prod. Each catalog is bound to its own workspace, so dev can't even see prod data."
- "Deploys run as service principals, not people: one for dev, one for prod."

**Show:** the root README or one slide.

## Act 2: A tour of the bundle (4 min)

**Show in Cursor:**
1. `databricks.yml`: one bundle, two targets.
   - `dev`: `mode: development`, so names get your prefix and schedules are paused.
   - `prod`: `mode: production`, its own catalog, the deploying service principal gets `CAN_MANAGE`.
2. `resources/`: the schema, volume, pipeline and job are declared as YAML. Nothing is clicked together in the UI.
3. `src/pipeline/transformations/`:
   - Bronze: Auto Loader reads Salesforce JSON, Excel workbooks, ERP CSVs, logistics and IoT files.
   - Silver: types, de-duplicates and applies data quality rules (`@dp.expect_or_drop`).
   - Gold: sales vs. target, on-time delivery, inventory days of cover, machine OEE.
4. `src/supply_chain_sim/` + `tests/`: "The plain-Python logic is unit tested in CI without a cluster."

## Act 3: Inner loop, a developer in their own sandbox (5 min)

**Run in the Cursor terminal:**
```bash
pytest -v
databricks bundle validate -t dev -p dev
databricks bundle deploy -t dev -p dev
databricks bundle run supply_chain_job -t dev -p dev
```

**Say while it runs:** "This is my own copy. Look at the names: `[dev <me>] cicd_dabs__data_eng__supply_chain_job`
and the schema `dev_<me>_supply_chain`. CI has its own copy next to mine, and we can't break each other."

**Show in the dev workspace:**
- The job run graph: generate source data -> refresh pipeline -> validate gold.
- The pipeline graph and the data quality results on the silver tables.

## Act 4: Live change in Cursor: prod schedule + two gold KPIs (8 min)

**Create a feature branch:**
```bash
git checkout main && git pull --prune
git checkout -b feature/prod-schedule-and-delivery-kpis
```

**Change 1: prod job schedule** (`databricks.yml`, `prod` target only)

```yaml
    variables:
      catalog: prod_demo
      job_schedule_cron: "0 0 6 * * ?" # daily at 06:00 UTC
```
change the last line to:
```yaml
      job_schedule_cron: "0 0 7,19 * * ?" # twice a day at 07:00 and 19:00 UTC
```
**Say:** "The schedule is a bundle variable. I only override it for prod; dev keeps the default and stays
paused because of development mode. Same code, environment-specific settings."

**Change 2: two new metrics on a gold table** (`src/pipeline/transformations/gold.py`, function
`gold_delivery_performance`). Add two lines inside `.agg(...)`, for example right after `on_time_rate` and
after `total_freight_cost`:
```python
            F.sum(F.when(F.col("is_delivered") & ~F.col("is_on_time"), 1).otherwise(0)).alias("late_shipments"),
            F.round(F.avg("freight_cost"), 2).alias("avg_freight_cost"),
```
**Say:** "`late_shipments` counts delivered shipments that missed their promised date; `avg_freight_cost` is the
mean freight cost per carrier, warehouse and month. The gold table is a materialized view, so the pipeline
recomputes it with the new columns. No migration script."

**Change 3 (optional): protect the new metrics with checks** (`src/quality/validate_gold.py`, add to `CHECKS`):
```python
    "late_shipments never exceed delivered": f"SELECT COUNT_IF(late_shipments > delivered) = 0 FROM {fqn}.gold_delivery_performance",
    "avg_freight_cost is positive": f"SELECT COUNT_IF(avg_freight_cost <= 0) = 0 FROM {fqn}.gold_delivery_performance",
```

**Verify in your sandbox before anyone reviews it:**
```bash
pytest -v
databricks bundle validate -t dev -p dev
databricks bundle deploy -t dev -p dev
databricks bundle run supply_chain_job -t dev -p dev
```
In the dev workspace SQL editor (replace `<me>` with your prefix, shown by `databricks bundle summary -t dev -p dev`):
```sql
SELECT carrier, warehouse_id, ship_month, delivered, late_shipments, on_time_rate, avg_freight_cost
FROM dev_demo.dev_<me>_supply_chain.gold_delivery_performance
ORDER BY ship_month DESC, carrier;
```

**Commit, push and open the pull request:**
```bash
git add -A
git commit -m "prod schedule twice a day; gold: late_shipments and avg_freight_cost"
git push -u origin feature/prod-schedule-and-delivery-kpis
```
Open the PR in GitHub. CI starts on its own: `Unit tests` and `Validate bundle (dev)`.
**Say:** "`main` is protected. I can't push to it, and I can't merge until both checks pass."
Point at the PR diff: one line of YAML for the schedule, two lines of PySpark for the metrics.

### Act 4b (optional): CI catches a mistake (2 min)

- Push `demo/broken-reference`, for example `${resources.pipelines.supply_chain_pipline.id}` (typo) in the job YAML.
- `Validate bundle (dev)` fails and the Merge button stays locked.
- "The mistake never reached a workspace." Close that pull request and delete the branch.

## Act 5: Merge, which deploys to dev automatically (5 min)

**Show:**
- Merge the pull request. The CD workflow starts:
  `Unit tests` -> `Deploy and run in dev` (`bundle deploy` + `bundle run` as `jasj-demo-sp-cicd-dev`).
- "It doesn't just deploy. It runs the whole job, and the gold checks act as a smoke test.
  If the data is wrong, the run fails and prod is never touched."
- In the dev workspace: the service principal's job run, and the new columns in
  `dev_demo.dev_jasj_demo_sp_cicd_dev_supply_chain.gold_delivery_performance`.
- Point out the dev job schedule is still paused: development mode.

## Act 6: Approve the move to prod (4 min)

**Show:**
- `Deploy to prod` is waiting: **Review deployments** -> `prod` -> **Approve and deploy**.
- "This is the change-control step: a named reviewer, with an audit trail in GitHub."
- In the prod workspace:
  - Jobs -> `cicd_dabs__data_eng__supply_chain_job` -> **Schedules & Triggers**: now 07:00 and 19:00 UTC.
    "Nobody clicked that. It came from one line in Git." Edit mode is locked: nobody hand-edits prod.
  - After the CD run finishes: the new columns in `prod_demo.supply_chain.gold_delivery_performance`.

## Act 7: Wrap-up and governance (2 min)

- "The same code went to both environments; only settings changed: catalog, mode and identity."
- "Rolling back is just reverting the commit. CD redeploys the previous state."
- "Least privilege: each service principal has only workspace access and catalog grants;
  secrets live in GitHub environments."
- Possible next steps: secretless GitHub sign-in (workload identity federation), a staging target,
  data quality monitoring, automatic dev -> main promotion.

---

## Act 8: Reset for the next demo (after the session, about 10 min)

The goal is to put `main`, dev and prod back to the baseline, through the same CI/CD path.

**Option A: GitHub Revert button (recommended; also a nice rollback story)**
1. Open the merged PR -> **Revert**. GitHub creates a revert branch and opens a new PR.
2. Wait for CI, merge it. CD redeploys the baseline to dev; approve the prod deployment.
3. Result: prod schedule back to daily 06:00 UTC, `late_shipments` / `avg_freight_cost` gone
   (the materialized view is recomputed without them).

**Option B: from Cursor**
```bash
git checkout main && git pull --prune
git log --oneline --merges -5            # find the merge commit of your demo PR
git checkout -b chore/reset-demo
git revert -m 1 <merge-commit-sha>       # replace <merge-commit-sha>, brackets included
git push -u origin chore/reset-demo      # open the PR, wait for CI, merge, approve prod
```

**Then reset your personal dev copy:**
```bash
git checkout main && git pull
databricks bundle deploy -t dev -p dev   # or: databricks bundle destroy -t dev -p dev
```

**Check the baseline is back:** prod job schedule shows 06:00 UTC daily, and in `databricks.yml` the prod target
has `job_schedule_cron: "0 0 6 * * ?"`.

---

## Q&A backup answers

- **Why not Gitflow?** Trunk-based development with short-lived branches is simpler, and environments are
  bundle targets, not branches. A `dev` branch flow can be added if a customer needs it.
- **What if two developers deploy at once?** Development mode prefixes everyone's resources, so copies stay separate.
- **Can deletes happen by accident?** Removing a resource from the bundle deletes it on the next deploy.
  That's why prod requires approval and `main` is protected.

## If something breaks live

| Symptom | Fix |
| --- | --- |
| Auth error in Cursor | `databricks auth login --host https://dbc-3fb58c7d-ac94.cloud.databricks.com --profile dev` |
| CD feels slow | Narrate over the Actions log; the dev run takes about 2.5 minutes |
| Prod approval not showing | Check the `prod` environment still has Required reviewers ticked |
| `Scopes 'all-apis' are not assigned` | The service principal's OAuth secret is scoped; generate an unscoped one |
