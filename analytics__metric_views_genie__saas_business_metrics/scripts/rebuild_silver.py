"""Monthly refresh, task 1 of 3 (serverless): rebuild the synthetic silver layer.

Runs sql/02_silver.sql in one Spark session (it uses a temporary function and views).
Deterministic: within one calendar month the rebuild produces identical data.
Task 2 (sql/09_refresh_gold.sql) must run on the SQL warehouse, because the gold
materialized views were created there and cannot be refreshed from serverless compute.
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


if __name__ == "__main__":
    run_file(demo_root(), "02_silver.sql")
    print("Silver rebuilt")
