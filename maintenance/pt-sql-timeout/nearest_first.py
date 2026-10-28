#!/usr/bin/env python3
"""Guarantee full-phase nearest-stop widening does not discard 10-stop options."""
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text(encoding="utf8")
start=s.index("    $stopLimit=$phase==='fast'?10:24;")
end=s.index("    $stage['transfer_search']=or_route_elapsed_ms($started);or_route_check_budget();",start)
old=s[start:end]
assert "$candidates=[];$directRows=" in old
assert "if(count($candidates)<1)" in old
assert "if(!$origList||!$destList)throw new RuntimeException(" in old
body=old.replace("$candidates=[];$directRows=","$directRows=",1)
body=body.replace("$stopLimit=$phase==='fast'?10:24;","",1)
body=body.replace("if(!$origList||!$destList)throw new RuntimeException('No suitable bus stops were found within the walking limit.');",
                  "if(!$origList||!$destList)continue;",1)
wrapped=(
"    // Check the NEAREST ten stops first. A broader search has a limited\n"
"    // candidate budget and must not erase a valid near-stop connection.\n"
"    $candidates=[];$origList=[];$destList=[];\n"
"    foreach(($phase==='fast'?[10]:[10,24]) as $stopLimit){\n"
+"".join("    "+line+"\n" for line in body.rstrip().splitlines())
+"        if($candidates)break;\n"
+"    }\n"
"    if(!$origList||!$destList)throw new RuntimeException('No suitable bus stops were found within the walking limit.');\n"
)
if "$stopLimit=10;" in wrapped:raise RuntimeError("Wrong patch")
s=s[:start]+wrapped+s[end:]
p.write_text(s,encoding="utf8")
print("Nearest-first monotonic candidate widening installed")
