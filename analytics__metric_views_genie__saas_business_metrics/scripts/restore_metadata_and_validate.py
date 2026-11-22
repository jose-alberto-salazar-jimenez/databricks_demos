"""Daily refresh, task 3 of 3 (serverless): restore metadata and validate.

Re-applies column comments (sql/08) and tags (sql/05), then fails the job if MRR
reconciliation breaks (monthly and daily), the last complete month or yesterday is missing, or cohorts are incomplete.
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


VALIDATION = """
WITH mm AS (
  SELECT month, SUM(opening_mrr) o, SUM(new_mrr) n, SUM(expansion_mrr) e, SUM(contraction_mrr) c,
         SUM(churned_mrr) ch, SUM(closing_mrr) cl
  FROM saas_demo.gold.customer_mrr_monthly GROUP BY month),
chk AS (SELECT *, LAG(cl) OVER (ORDER BY month) prev_cl FROM mm)
SELECT
  (SELECT count(*) FROM saas_demo.gold.customer_mrr_monthly
    WHERE closing_mrr <> opening_mrr + new_mrr + expansion_mrr - contraction_mrr - churned_mrr) AS row_breaks,
  (SELECT count_if(cl <> o + n + e - c - ch) FROM chk) AS month_breaks,
  (SELECT count_if(prev_cl IS NOT NULL AND o <> prev_cl) FROM chk) AS opening_breaks,
  (SELECT (SELECT cl FROM chk ORDER BY month DESC LIMIT 1)
        - (SELECT SUM(mrr_after - mrr_before) FROM saas_demo.silver.mrr_events WHERE event_date < trunc(current_date(), 'MM'))) AS events_diff,
  (SELECT (SELECT SUM(closing_mrr) FROM saas_demo.gold.customer_mrr_daily WHERE date = date_sub(current_date(), 1))
        - (SELECT SUM(mrr_after - mrr_before) FROM saas_demo.silver.mrr_events)) AS daily_events_diff,
  (SELECT max(date) FROM saas_demo.gold.customer_mrr_daily) AS last_day,
  date_sub(current_date(), 1) AS expected_last_day,
  (SELECT max(month) FROM saas_demo.gold.customer_mrr_monthly) AS last_month,
  add_months(trunc(current_date(), 'MM'), -1) AS expected_last_month,
  (SELECT count(*) FROM saas_demo.gold.signup_cohort_retention_monthly) AS cohort_rows
"""


def validate():
    checks = spark.sql(VALIDATION).collect()[0].asDict()
    print(checks)
    problems = [k for k in ["row_breaks", "month_breaks", "opening_breaks", "events_diff", "daily_events_diff"] if checks[k] != 0]
    if checks["last_day"] != checks["expected_last_day"]:
        problems.append("last_day")
    if checks["last_month"] != checks["expected_last_month"]:
        problems.append("last_month")
    if checks["cohort_rows"] != 300:
        problems.append("cohort_rows")
    if problems:
        raise RuntimeError(f"Validation failed: {problems} -> {checks}")


if __name__ == "__main__":
    root = demo_root()
    run_file(root, "08_column_comments.sql")
    run_file(root, "05_governance_tags.sql")
    validate()
    print("Daily refresh OK")
