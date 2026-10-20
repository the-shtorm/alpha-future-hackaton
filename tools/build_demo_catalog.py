"""Regenerate the demo-only Flyway catalog from the reviewed synthetic products."""
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "docs/reference/products-demo.json"
catalog = json.loads(source.read_text(encoding="utf-8-sig"))

def sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"

def json_sql(value):
    return sql(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) + "::jsonb"

lines = ["-- SYNTHETIC DEMO_BANK catalog. Not real bank offers or statutory thresholds.",
         "SET search_path TO credit, public;", ""]
for product in catalog["products"]:
    pid = str(uuid5(NAMESPACE_URL, "credit-cabinet/product/" + product["id"]))
    vid = str(uuid5(NAMESPACE_URL, "credit-cabinet/product/" + product["id"] + "/" + product["version"]))
    lines += [
        "INSERT INTO credit_product(id,code,provider_code,name,is_synthetic) VALUES ("
        + ",".join(map(sql, [pid, product["id"], product["provider_id"], product["name"]])) + ",true) ON CONFLICT (id) DO NOTHING;",
        "INSERT INTO credit_product_version(id,product_id,version_code,currency,facility_kind,min_amount,max_amount,"
        "min_term_months,max_term_months,annual_rate_pct,allowed_borrower_kinds,allowed_purposes,policy) VALUES ("
        + ",".join(map(sql, [vid, pid, product["version"], product["currency"], product["facility_kind"],
            product["amount_rub"]["min"], product["amount_rub"]["max"], product["facility_term_months"]["min"],
            product["facility_term_months"]["max"], product["pricing"].get("annual_rate_pct")]))
        + "," + json_sql(product["borrower_forms"]) + "," + json_sql(product["purposes"])
        + "," + json_sql({**product, "common_policy": catalog["common_policy"]}) + ") ON CONFLICT (id) DO NOTHING;", ""
    ]
target = ROOT / "backend/src/main/resources/db/demo/R__synthetic_product_catalog.sql"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("\n".join(lines), encoding="utf-8")
print(f"Generated {len(catalog['products'])} demo products: {target.relative_to(ROOT)}")
