import httpx, json, sys

filepath = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\VHK6FSM\Personal\CodeReviewAgent\samples\python\buggy_ecommerce.py"
code = open(filepath).read()
r = httpx.post(
    "http://127.0.0.1:19280/api/review",
    json={"code": code, "filename": filepath.split("\\")[-1], "language": "python"},
    timeout=180,
)
d = r.json()
for f in d["findings"]:
    agent = f["agent"]
    sev = f["severity"]
    conf = f["confidence"]
    line = f["line_start"]
    title = f["title"][:65]
    print(f"{agent:20s} | {sev:8s} | conf={conf:.2f} | L{line:3d} | {title}")
print(f"\nTotal: {len(d['findings'])} findings")
print(f"Score: {d['summary']['overall_quality_score']}")
print(f"Partial: {d.get('partial_review', False)}")
print(f"Failed agents: {d.get('failed_agents', [])}")
