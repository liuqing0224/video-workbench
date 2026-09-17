"""Validate real document handoffs without treating unfinished templates as production data."""

import json
from apps.server.core import safe


def validate_handoff(work):
    documents = {}
    for path in (work / "documents").rglob("*.json"):
        documents[path.name] = json.loads(path.read_text())
    assets = documents.get("assets-manifest.json", {}).get("assets", [])
    ids = [item["asset_id"] for item in assets]
    if len(ids) != len(set(ids)):
        raise ValueError("素材编号重复")
    for asset in assets:
        if asset.get("status") == "available":
            path = asset.get("path")
            if not path or not safe(work, path).is_file():
                raise ValueError(f"可用素材不存在：{asset['asset_id']}")
    for name, collection in [
        ("claims-map.json", "claims"),
        ("components-map.json", "shots"),
    ]:
        doc = documents.get(name, {})
        if doc.get("status") == "template":
            continue
        for item in doc.get(collection, []):
            for ref in item.get("asset_ids", []):
                if ref not in ids:
                    raise ValueError(f"{name} 引用了不存在的素材 {ref}")
    return {"json_files": len(documents), "assets": len(assets)}
