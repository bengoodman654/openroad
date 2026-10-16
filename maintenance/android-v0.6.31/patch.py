#!/usr/bin/env python3
"""Conservative live-bus cache UX patch for OpenRoad 0.6.31; no network calls."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
def edit(path, before, after):
    p=root/path
    s=p.read_text(encoding="utf-8")
    count=s.count(before)
    if count!=1:
        raise SystemExit(f"Expected one match, got {count} in {path}: {before[:100]!r}")
    p.write_text(s.replace(before,after,1),encoding="utf-8")
js="app/src/main/assets/app.js"
java="app/src/main/java/uk/co/bengoodman/clearroute/TransitClient.java"
edit(js, "  function requestBusLive(){", """  // Stop repeated taps from exhausting the shared server's hourly BODS allowance.
  const busLiveAttemptTimes=new Map();
  let busLiveGlobalRetryUntil=0;
  function requestBusLive(){""")
edit(js, "    const id=++busLiveRequestId,btn=el('loadBusLiveBtn');",
"""    const stamp=Date.now();
    if(stamp<busLiveGlobalRetryUntil){toast('The live-bus hourly allowance is exhausted. Please try later.');return;}
    const areaKey=`${String(data.line).toLowerCase()}|${Math.floor(ref.lat*20)}|${Math.floor(ref.lon*20)}`;
    if(stamp-(busLiveAttemptTimes.get(areaKey)||0)<120000){
      toast('Recently checked this service and area. Try again in about two minutes.');return;
    }
    busLiveAttemptTimes.set(areaKey,stamp);
    if(busLiveAttemptTimes.size>40)busLiveAttemptTimes.clear();
    const id=++busLiveRequestId,btn=el('loadBusLiveBtn');""")
edit(js, "show('busServiceLiveBadge',vehicles.length>0);const btn=el('loadBusLiveBtn');",
"""const badge=el('busServiceLiveBadge');
    if(badge)badge.textContent=vehicles.length&&vehicles.every(v=>v.lastKnown===true)?'Last known':'Live';
    show('busServiceLiveBadge',vehicles.length>0);const btn=el('loadBusLiveBtn');""")
edit(js, "node.className='bus-live-marker';node.textContent='🚌';node.title=`Live bus",
"""node.className='bus-live-marker';if(v.lastKnown===true)node.style.opacity='.55';node.textContent='🚌';node.title=`${v.lastKnown===true?'Last known':'Live'} bus""")
edit(js, "if(busServiceData){busServiceData.vehicles=Array.isArray(data?.vehicles)?data.vehicles:[];busServiceData.liveSource=data?.source||'BODS';",
"""if(busServiceData){busServiceData.vehicles=Array.isArray(data?.vehicles)?data.vehicles:[];busServiceData.liveStale=data?.coverage==='last-known-vehicles';busServiceData.liveSource=data?.source||'BODS';""")
edit(js,"}toast(message||'Live bus positions are unavailable.');},",
"""}if(/hourly request limit reached|hourly request budget reached/i.test(String(message||''))){
        const m=String(message||'').match(/(\\d+) minutes/i);
        busLiveGlobalRetryUntil=Date.now()+Math.max(1,m?Number(m[1]):10)*60000;
      }
      toast(message||'Live bus positions are unavailable.');},""")
edit(java,"    private static final long BODS_FRESH_MS = 3L * 60L * 1000L;",
"""    private static final long BODS_FRESH_MS = 3L * 60L * 1000L;
    private static final long BODS_LAST_KNOWN_MS = 15L * 60L * 1000L;""")
p=root/java
s=p.read_text(encoding="utf-8")
begin=s.index("    private static String parseBodsBusVehicles(String xml, String line) throws Exception {")
end=s.index("    // -----------------------------------------------------------------------------------------",begin)
replacement="""    private static String parseBodsBusVehicles(String xml, String line) throws Exception {
        XmlPullParser parser = XmlPullParserFactory.newInstance().newPullParser();
        parser.setInput(new StringReader(xml));
        JSONArray vehicles = new JSONArray();
        String tag = "", recorded = "", lineRef = "", published = "", destination = "", vehicleRef = "";
        double vLat = Double.NaN, vLon = Double.NaN, bearing = Double.NaN;
        boolean matchedService = false, hasFresh = false;
        int event = parser.getEventType();
        while (event != XmlPullParser.END_DOCUMENT) {
            if (event == XmlPullParser.START_TAG) tag = parser.getName();
            else if (event == XmlPullParser.TEXT) {
                String text = parser.getText() == null ? "" : parser.getText().trim();
                if (!text.isEmpty()) {
                    if ("RecordedAtTime".equals(tag)) recorded = text;
                    else if ("LineRef".equals(tag)) lineRef = text;
                    else if ("PublishedLineName".equals(tag)) published = text;
                    else if ("DestinationName".equals(tag)) destination = text;
                    else if ("VehicleRef".equals(tag)) vehicleRef = text;
                    else if ("Latitude".equals(tag)) try { vLat = Double.parseDouble(text); } catch (Exception ignored) {}
                    else if ("Longitude".equals(tag)) try { vLon = Double.parseDouble(text); } catch (Exception ignored) {}
                    else if ("Bearing".equals(tag)) try { bearing = Double.parseDouble(text); } catch (Exception ignored) {}
                }
            } else if (event == XmlPullParser.END_TAG && "VehicleActivity".equals(parser.getName())) {
                if ((line.equalsIgnoreCase(lineRef) || line.equalsIgnoreCase(published)) && Double.isFinite(vLat) && Double.isFinite(vLon)) {
                    matchedService = true;
                    long age = ageMs(recorded);
                    if (age >= 0 && age <= BODS_LAST_KNOWN_MS) {
                        boolean fresh = age <= BODS_FRESH_MS;
                        hasFresh |= fresh;
                        vehicles.put(new JSONObject().put("lat", vLat).put("lon", vLon)
                            .put("recordedAt", recorded).put("destination", destination)
                            .put("vehicleRef", vehicleRef).put("bearing", bearing)
                            .put("lastKnown", !fresh).put("ageMinutes", Math.round(age / 60000.0)));
                    }
                }
                recorded=lineRef=published=destination=vehicleRef=""; vLat=vLon=bearing=Double.NaN;
            }
            event = parser.next();
        }
        if (vehicles.length() == 0) {
            if (matchedService) throw new Exception("Only older BODS positions exist for this service here; no recent vehicle is available.");
            throw new Exception("No tracked bus " + line + " was reported in this map area. Try another section of its route.");
        }
        return new JSONObject().put("line", line).put("source", "BODS")
            .put("coverage", hasFresh ? "live-vehicles" : "last-known-vehicles")
            .put("vehicles", vehicles)
            .put("message", hasFresh ? "Fresh official bus positions; older markers are dimmed."
                : "Last-known positions only (up to 15 minutes old). These are not live locations.")
            .toString();
    }

"""
s=s[:begin]+replacement+s[end:]
p.write_text(s,encoding="utf-8")
edit("app/build.gradle","versionCode 90","versionCode 91")
p=root/"app/build.gradle"
txt=p.read_text(encoding="utf-8")
if txt.count("0.6.30")!=2: raise SystemExit("Unexpected Android build.gradle version count")
p.write_text(txt.replace("0.6.30","0.6.31"),encoding="utf-8")
def update_version(path):
    p=root/path
    text=p.read_text(encoding="utf-8")
    if "0.6.30" not in text: raise SystemExit(f"Unexpected version in {path}")
    p.write_text(text.replace("0.6.30","0.6.31"),encoding="utf-8")
update_version("app/src/main/assets/index.html")
update_version("app/src/main/java/uk/co/bengoodman/clearroute/ApiClient.java")
update_version("validate.sh")
edit("validate.sh","versionCode 90","versionCode 91")
print("OpenRoad 0.6.31 patch: rate-aware button, labelled last-known vehicles, diagnostics")
