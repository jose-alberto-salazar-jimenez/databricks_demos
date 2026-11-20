"""Create governed tags, Genie Agents, the AI/BI dashboard and their tags for the SaaS metrics demo.

Run after sql/01..06 in a Databricks notebook or with a configured Databricks CLI profile.
Discover domains and Pages are created in the UI (see README, "Discover setup").
Genie Agents and the dashboard are created in PARENT_PATH and are NOT shared with anyone.
The dashboard is created as a draft (publish it after review).
"""
import json, pathlib
from databricks.sdk import WorkspaceClient

WAREHOUSE_ID = "<SERVERLESS_SQL_WAREHOUSE_ID>"          # must be a serverless SQL warehouse
PARENT_PATH = "/Workspace/Users/<YOUR_USER>/analytics__metric_views_genie__saas_business_metrics"
REPO = pathlib.Path(__file__).resolve().parent.parent

w = WorkspaceClient()

def api(method, path, body=None):
    return w.api_client.do(method, path, body=body)

def tag(entity_type, entity_id, tags):
    """Attach governed tags; a value of None means a key-only tag."""
    for key, value in tags:
        body = {"entity_type": entity_type, "entity_id": entity_id, "tag_key": key}
        if value:
            body["tag_value"] = value
        api("POST", "/api/2.0/entity-tag-assignments", body)

CERTIFIED = ("system.certification_status", "certified")

# 1) Governed tags (account level). Requires permission to create governed tags.
TAGS = {
    "Revenue": "Domain for subscription revenue and customer metrics (synthetic SaaS demo).",
    "Revenue/RecurringRevenue": "Subdomain for MRR, ARR, churn and net revenue retention metrics.",
    "Revenue/CustomerHealth": "Subdomain for customer base, tenure and cohort retention metrics.",
}
for key, desc in TAGS.items():
    try:
        api("POST", "/api/2.1/tag-policies", {"tag_key": key, "description": desc})
        print("created tag", key)
    except Exception as e:  # already exists
        print("tag", key, "->", str(e)[:120])

# 2) Genie Agents from the exported configuration
AGENTS = [("revenue_and_retention.json", "Revenue/RecurringRevenue"),
          ("customer_success.json", "Revenue/CustomerHealth")]
agent_ids = {}
for fname, domain_tag in AGENTS:
    doc = json.loads((REPO / "genie" / fname).read_text())
    space = api("POST", "/api/2.0/genie/spaces", {
        "title": doc["title"], "description": doc["description"],
        "warehouse_id": WAREHOUSE_ID, "parent_path": PARENT_PATH,
        "serialized_space": json.dumps(doc["serialized_space"]),
    })
    sid = space["space_id"]
    agent_ids[fname] = sid
    print("created Genie Agent", doc["title"], sid)
    # 3) Domain tag + certification (certify only after the example queries run)
    tag("geniespaces", sid, [(domain_tag, None), CERTIFIED])

# 4) AI/BI dashboard "SaaS Revenue Cockpit" from the exported file
#    Ask Genie must point to the Revenue and Retention Genie Agent created above: the exported
#    file holds the id from the source workspace. The dashboard spans both subdomains.
dash = json.loads((REPO / "dashboards" / "SaaS Revenue Cockpit.lvdash.json").read_text())
dash.setdefault("uiSettings", {}).setdefault("genieSpace", {}).update(
    {"overrideId": agent_ids["revenue_and_retention.json"], "enablementMode": "ENABLED"})
db = api("POST", "/api/2.0/lakeview/dashboards", {
    "display_name": "SaaS Revenue Cockpit", "parent_path": PARENT_PATH,
    "warehouse_id": WAREHOUSE_ID, "serialized_dashboard": json.dumps(dash),
})
print("created dashboard", db["display_name"], db["dashboard_id"])
tag("dashboards", db["dashboard_id"],
    [("Revenue/RecurringRevenue", None), ("Revenue/CustomerHealth", None), CERTIFIED])
