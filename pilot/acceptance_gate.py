"""105-case OpenRoad production acceptance registry, fail closed."""
import json
from pathlib import Path

MANIFEST=Path(__file__).parent/"acceptance_cases_105.json"

def acceptance_report(evidence=None):
    cases=json.loads(MANIFEST.read_text(encoding="utf-8"))
    supplied=evidence or {}
    accepted=[]
    for case in cases:
        record=supplied.get(case["id"])
        if (isinstance(record,dict) and record.get("status")=="PASS"
            and isinstance(record.get("deviceBuild"),str)
            and isinstance(record.get("sourceSnapshot"),str)
            and record.get("verificationMethod") in
            {"FIELD_REVIEW","INDEPENDENT_END_TO_END"}
            and isinstance(record.get("evidenceURI"),str)
            and record["evidenceURI"].startswith("https://")
            and record.get("reviewedBy")):
            accepted.append(case["id"])
    return {"total":len(cases),"accepted":len(accepted),
            "pending":len(cases)-len(accepted),
            "releaseReady":len(cases)==105 and len(accepted)==105,
            "acceptedIds":accepted}

if __name__=="__main__":
    print(json.dumps(acceptance_report(),sort_keys=True))
