"""Monthly refresh for the SaaS business metrics demo.

The synthetic data covers the 24 complete months before current_date(), and many demo questions ask for
"the last complete month". This script rolls the window forward:
  1. rebuild silver (sql/02, deterministic per calendar month)
  2. refresh the gold materialized views
  3. rebuild the deprecated legacy table (sql/06)
  4. re-apply column comments (sql/08) and tags (sql/05), which CREATE OR REPLACE drops
  5. validate: reconciliation checks must be 0 and the last complete month must have data

Run as a Lakeflow Job python file task on serverless (git_source = this repo, branch main),
or interactively from a Databricks notebook / serverless session.
"""
import os
import sys

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()


def demo_root():
    for cand in [globals().get("__file__"), sys.argv[0] if sys.argv else None]:
        if cand and cand.endswith(".py"):
            return os.path.dirname(os.path.dirname(os.path.abspath(cand)))
    raise RuntimeError("Cannot locate the demo folder; run this file as a script.")


def statements(path):
    """Split a SQL file on ';' and drop comment-only lines (comments in these files contain no ';')."""
    out = []
    for chunk in open(path).read().split(";"):
        body = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--")).strip()
        if body:
            out.append(body)
    return out


def run_file(root, name):
    stmts = statements(os.path.join(root, "sql", name))
    for s in stmts:
        spark.sql(s)
    print(f"{name}: {len(stmts)} statements")


def main():
    root = demo_root()
    run_file(root, "02_silver.sql")
    for mv in ["mrr_monthly", "customer_snapshot", "cohort_retention"]:  # order matters
        spark.sql(f"REFRESH MATERIALIZED VIEW saas_demo.gold.{mv}")
        print(f"refreshed gold.{mv}")
    run_file(root, "06_legacy_mrr_report_v1.sql")
    run_file(root, "08_column_comments.sql")
    run_file(root, "05_governance_tags.sql")

    checks = spark.sql("""
        WITH mm AS (
          SELECT month, SUM(opening_mrr) o, SUM(new_mrr) n, SUM(expansion_mrr) e, SUM(contraction_mrr) c,
                 SUM(churned_mrr) ch, SUM(closing_mrr) cl
          FROM saas_demo.gold.mrr_monthly GROUP BY month),
        chk AS (SELECT *, LAG(cl) OVER (ORDER BY month) prev_cl FROM mm)
        SELECT
          (SELECT count(*) FROM saas_demo.gold.mrr_monthly
            WHERE closing_mrr <> opening_mrr + new_mrr + expansion_mrr - contraction_mrr - churned_mrr) AS row_breaks,
          (SELECT count_if(cl <> o + n + e - c - ch) FROM chk) AS month_breaks,
          (SELECT count_if(prev_cl IS NOT NULL AND o <> prev_cl) FROM chk) AS opening_breaks,
          (SELECT (SELECT cl FROM chk ORDER BY month DESC LIMIT 1)
                - (SELECT SUM(mrr_after - mrr_before) FROM saas_demo.silver.mrr_events)) AS events_diff,
          (SELECT max(month) FROM saas_demo.gold.mrr_monthly) AS last_month,
          add_months(trunc(current_date(), 'MM'), -1) AS expected_last_month,
          (SELECT count(*) FROM saas_demo.gold.cohort_retention) AS cohort_rows
    """).collect()[0].asDict()
    print(checks)
    problems = [k for k in ["row_breaks", "month_breaks", "opening_breaks"] if checks[k] != 0]
    if checks["events_diff"] != 0:
        problems.append("events_diff")
    if checks["last_month"] != checks["expected_last_month"]:
        problems.append("last_month")
    if checks["cohort_rows"] != 300:
        problems.append("cohort_rows")
    if problems:
        raise RuntimeError(f"Validation failed: {problems} -> {checks}")
    print("Monthly refresh OK")


if __name__ == "__main__":
    main()
