"""Executable design reference only. NOT Android, PHP, provider or production functionality."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

OUTCOMES=set("OK PARTIAL NO_MATCH NO_JOURNEY COVERAGE_MISSING PROVIDER_UNAVAILABLE TIMEOUT RATE_LIMITED INPUT_INVALID".split())
REALTIME=set("SCHEDULED_ONLY PREDICTED OBSERVED_FRESH LAST_KNOWN UNAVAILABLE".split())
SERVICE=set("SCHEDULED_UNVERIFIED OPERATING_REPORTED DELAYED VERIFIED_CANCELLED DIVERTED UNKNOWN".split())
JOBS=set("RUNNING CANCELLED_LOCALLY STOPPING STOPPED UNKNOWN".split())
REQUIRED=set("requestId generation operationId taskType snapshotId schemaVersion outcome reasonCode coverage provenance timeBasis validUntil results warnings nextActions realtimeStatus serviceStatus remoteJobStatus".split())

def envelope_ok(x):
    if not REQUIRED.issubset(x) or x["outcome"] not in OUTCOMES or x["realtimeStatus"] not in REALTIME or x["serviceStatus"] not in SERVICE or x["remoteJobStatus"] not in JOBS: return False
    if x["taskType"] not in ("JOURNEY","SERVICE","DEPARTURES","EXPLORE") or not x["requestId"] or not x["snapshotId"] or not isinstance(x["results"],list):return False
    try: return datetime.fromisoformat(x["validUntil"]).tzinfo is not None
    except (TypeError, ValueError): return False

def location(explicit=None,pin=None,viewport=None,gps=None,opt_in=False):
    for name,v in (("explicit",explicit),("pin",pin),("viewport",viewport)):
        if v is not None:return name,v
    return ("gps",gps) if opt_in and gps is not None else ("none",None)

def identity(provider,kind,source_id):
    if not provider or not kind or not source_id:raise ValueError("missing canonical namespace")
    return ":".join([provider,kind,source_id])

def coverage(manifest,area,mode,date,capability):
    return (manifest.get("quality")=="VALIDATED" and manifest.get("licence") and manifest.get("snapshot")
      and area in manifest.get("areas",[]) and mode in manifest.get("modes",[])
      and manifest.get("from","9999")<=date<=manifest.get("to","0000")
      and capability in manifest.get("capabilities",[]))

def outcome(data,service,today,feasible):
    if not data:return "COVERAGE_MISSING"
    if not service:return "NO_MATCH"
    return "OK" if today and feasible else "NO_JOURNEY"

def eligible(j,snapshot,accessible=False):
    return (j.get("snapshot")==snapshot and j.get("calendar") and j.get("complete")
      and j.get("walk_ok") and j.get("transfer_ok") and not j.get("cancelled")
      and (not accessible or j.get("accessible") is True))

def service_selectable(scheduled,live,cancelled):
    return bool(scheduled and not cancelled)

def live_state(age_seconds,trip_matched):
    if age_seconds is None or age_seconds<0 or age_seconds>900:return "UNAVAILABLE"
    if not trip_matched or age_seconds>180:return "LAST_KNOWN"
    return "OBSERVED_FRESH"

def x_action(foreground=False,guidance=False,result=False,dirty=False):
    if dirty:return "CONFIRM_DISCARD"
    if foreground:return "CANCEL_FOREGROUND"
    if guidance:return "CONFIRM_STOP_GUIDANCE"
    return "CLOSE_RESULT" if result else "DISABLED"

@dataclass
class Task:
    request_id: str
    snapshot: str
    generation: int=0
    cancelled: bool=False
    def cancel(self):
        self.cancelled=True
        self.generation+=1
    def accept(self,rid,gen,snapshot):
        return not self.cancelled and rid==self.request_id and gen==self.generation and snapshot==self.snapshot

@dataclass
class Registry:
    ttl: timedelta=timedelta(minutes=30)
    tombstones: dict=field(default_factory=dict)
    def cancel(self,owner,rid,now):
        self.tombstones[(owner,rid)]=now+self.ttl
    def admit(self,owner,rid,now):
        return self.tombstones.get((owner,rid),datetime.min.replace(tzinfo=timezone.utc))<=now

@dataclass
class Shared:
    subscribers: set=field(default_factory=set)
    active: bool=True
    def detach(self,rid):
        self.subscribers.discard(rid)
        # Shared work remains active for other subscribers.

def release_gate(required,passed,scope_ok,security_ok,resources_ok):
    return scope_ok and security_ok and resources_ok and set(required).issubset(set(passed))
