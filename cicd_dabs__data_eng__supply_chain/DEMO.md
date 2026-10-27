# Demo talk track: CI/CD for a data engineering pipeline with Declarative Automation Bundles

About 30 minutes. Shows a supply chain lakehouse (simulated Salesforce, Excel, ERP, logistics and plant IoT sources
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
- [ ] Prepare two local branches (do not push yet):
  - `feature/late-shipments-kpi`: the real change for Act 4
  - `demo/broken-reference`: an intentionally broken change for Act 4b (optional)
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

## Act 4: Make a change and open a pull request (5 min)

**Change:** add a `late_shipments` column to `gold_delivery_performance`, plus a check for it in
`src/quality/validate_gold.py`.

```bash
git checkout -b feature/late-shipments-kpi      # or switch to the prepared branch
# edit gold.py and validate_gold.py
pytest -v && databricks bundle validate -t dev -p dev
git commit -am "gold: add late_shipments KPI"
git push -u origin feature/late-shipments-kpi
```

**Show in GitHub:**
- Open the pull request. CI starts on its own: `Unit tests` and `Validate bundle (dev)`.
- "`main` is protected. I can't push to it, and I can't merge until both checks pass."

### Act 4b (optional): CI catches a mistake (2 min)

- Push `demo/broken-reference`, for example `${resources.pipelines.supply_chain_pipline.id}` (typo).
- `Validate bundle (dev)` fails and the Merge button stays locked.
- "The mistake never reached a workspace." Close that pull request.

## Act 5: Merge, which deploys to dev automatically (5 min)

**Show:**
- Merge the real pull request. The CD workflow starts:
  `Unit tests` -> `Deploy and run in dev` (`bundle deploy` + `bundle run` as `jasj-demo-sp-cicd-dev`).
- "It doesn't just deploy. It runs the whole job, and the gold checks act as a smoke test.
  If the data is wrong, the run fails and prod is never touched."
- In the dev workspace, open the service principal's job run and point to the new `late_shipments` column.

## Act 6: Approve the move to prod (3 min)

**Show:**
- `Deploy to prod` is waiting: **Review deployments** -> `prod` -> **Approve and deploy**.
- "This is the change-control step: a named reviewer, with an audit trail in GitHub."
- In the prod workspace:
  - The job owned by `jasj-demo-sp-cicd-prd`, schedule active, edit mode locked: "Nobody hand-edits prod."
  - `prod_demo.supply_chain`, with no `dev_` prefix.

## Act 7: Wrap-up and governance (2 min)

- "The same code went to both environments; only settings changed: catalog, mode and identity."
- "Rolling back is just reverting the commit. CD redeploys the previous state."
- "Least privilege: each service principal has only workspace access and catalog grants;
  secrets live in GitHub environments."
- Possible next steps: secretless GitHub sign-in (workload identity federation), a staging target,
  data quality monitoring, automatic dev -> main promotion.

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
