import time

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from company_recommender import LOCAL_RADIUS_MILES
from openings_scout import scan_openings_for_user
from shortlist_agent import build_replacement, build_shortlist, get_supabase_client, reject_candidate

app = FastAPI(title="AI Job Scout — Company Matcher")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(authorization: str = Header(None)) -> dict | None:
    """Validates a bearer token against Supabase's Auth server directly
    (supabase-py's auth.get_user) rather than adding a JWT-decoding
    dependency -- fine at this traffic level. Returns None (not an error)
    when no/invalid Authorization is given.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        resp = get_supabase_client().auth.get_user(token)
    except Exception:
        return None
    if not resp or not resp.user:
        return None
    return {"id": resp.user.id, "email": resp.user.email}


def require_user(user: dict | None = Depends(get_current_user)) -> dict:
    """Phase 5 of the real-per-user-accounts rollout: Authorization is now
    required on the customer-facing endpoints below -- the Phase 2 dual-path
    fallback (unauthenticated requests keyed by a client-supplied email) is
    gone."""
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


# --- Per-user throttle -------------------------------------------------------
# The costly endpoints (/shortlist runs Claude+Exa; /scan-openings hits ATS
# boards) are now identity-gated, so we can rate-limit per user. This is a
# deliberately simple in-process limiter: a min gap between calls (stops
# double-clicks and hammering) plus a generous daily cap (stops a runaway
# loop from burning the API budget). State lives in memory, so it resets on
# deploy/cold-start -- acceptable as a first line of defense at this traffic
# level; a shared store (Redis/Postgres) is the upgrade path if it ever needs
# to be exact across workers.
_MIN_SECONDS_BETWEEN = {"shortlist": 60, "scan": 30}
_MAX_PER_DAY = {"shortlist": 25, "scan": 50}
_last_call: dict = {}   # (action, user_id) -> monotonic timestamp
_day_count: dict = {}   # (action, user_id, yyyy-mm-dd) -> count


def enforce_throttle(action: str, user_id: str) -> None:
    """Raise HTTP 429 if this user is calling `action` too fast or too often
    today; otherwise record the call and return."""
    now = time.monotonic()
    last = _last_call.get((action, user_id))
    min_gap = _MIN_SECONDS_BETWEEN[action]
    if last is not None and now - last < min_gap:
        wait = int(min_gap - (now - last)) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {wait}s before trying that again.",
        )

    today = time.strftime("%Y-%m-%d", time.gmtime())
    day_key = (action, user_id, today)
    if _day_count.get(day_key, 0) >= _MAX_PER_DAY[action]:
        raise HTTPException(
            status_code=429,
            detail="Daily limit reached for this action — try again tomorrow.",
        )

    _last_call[(action, user_id)] = now
    _day_count[day_key] = _day_count.get(day_key, 0) + 1


class ShortlistRequest(BaseModel):
    resume: str
    role: str
    location: str
    company_size: str
    include_remote: bool
    radius_miles: int = LOCAL_RADIUS_MILES
    prioritize_growth: bool = True
    prioritize_stability: bool = True
    email: str = None  # legacy fallback only -- signed-in requests carry no email, see /shortlist


def _run_shortlist_job(
    resume: str,
    role: str,
    location: str,
    company_size: str,
    include_remote: bool,
    radius_miles: int,
    prioritize_growth: bool,
    prioritize_stability: bool,
    email: str,
    user_id: str = None,
) -> None:
    """Runs in the background after /shortlist responds. Errors are logged
    server-side (visible in Render logs) rather than raised — the client
    already got its "started" response, and a failure here just means the
    digest email won't arrive."""
    try:
        build_shortlist(
            resume, role, location, company_size, include_remote,
            radius_miles, prioritize_growth, prioritize_stability,
            recipient_email=email, user_id=user_id,
        )
    except Exception as e:
        print(f"[/shortlist background job] failed: {e}", flush=True)


@app.post("/shortlist")
def shortlist(request: ShortlistRequest, background_tasks: BackgroundTasks, user: dict = Depends(require_user)):
    enforce_throttle("shortlist", user["id"])
    recipient_email = user["email"]
    background_tasks.add_task(
        _run_shortlist_job,
        request.resume,
        request.role,
        request.location,
        request.company_size,
        request.include_remote,
        request.radius_miles,
        request.prioritize_growth,
        request.prioritize_stability,
        recipient_email,
        user["id"],
    )
    return {
        "status": "started",
        "message": f"Shortlist search started — this takes about 5-10 minutes. Results will be emailed to {recipient_email} when it's done, or refresh this page.",
    }


@app.get("/candidates")
def candidates(
    role: str = None,
    location: str = None,
    company_size: str = None,
    include_remote: bool = None,
    radius_miles: int = None,
    prioritize_growth: bool = None,
    prioritize_stability: bool = None,
    user: dict = Depends(require_user),
):
    supabase = get_supabase_client()
    query = supabase.table("candidates").select("*").eq("user_id", user["id"])
    if role is not None:
        query = query.eq("role", role)
    if location is not None:
        query = query.eq("location", location)
    if company_size is not None:
        query = query.eq("company_size", company_size)
    if include_remote is not None:
        query = query.eq("include_remote", include_remote)
    if radius_miles is not None:
        query = query.eq("radius_miles", radius_miles)
    if prioritize_growth is not None:
        query = query.eq("prioritize_growth", prioritize_growth)
    if prioritize_stability is not None:
        query = query.eq("prioritize_stability", prioritize_stability)
    response = query.order("role").order("location").order("rank").execute()
    return response.data or []


class RejectRequest(BaseModel):
    candidate_id: str


@app.post("/reject")
def reject(request: RejectRequest, background_tasks: BackgroundTasks, user: dict = Depends(require_user)):
    try:
        row = reject_candidate(request.candidate_id, user_id=user["id"])
    except ValueError as e:
        status_code = 404 if str(e) == "Company not found." else 403
        raise HTTPException(status_code=status_code, detail=str(e))
    background_tasks.add_task(build_replacement, row)
    return {
        "status": "rejected",
        "message": "Rejected. Finding a replacement — check back in a minute or two.",
    }


@app.post("/scan-openings")
def scan_openings(user: dict = Depends(require_user)):
    """Phase A of the Openings automation: read the ATS boards of the user's
    current target companies (from My Companies) and add any role-matching
    live postings to their My Openings board as 'scout' cards. Runs inline --
    ATS lookups are fast and free, unlike the multi-minute /shortlist job --
    so the response carries the actual result the page shows."""
    enforce_throttle("scan", user["id"])
    try:
        summary = scan_openings_for_user(user["id"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    added = summary["openings_added"]
    scanned = summary["companies_scanned"]
    if scanned == 0:
        message = "No target companies to scan yet — run a company search first."
    elif added == 0:
        message = (
            f"Scanned {scanned} companies — no new matching openings found on "
            "their job boards right now."
        )
    else:
        message = (
            f"Found {added} new opening{'s' if added != 1 else ''} across "
            f"{scanned} companies — added to your board."
        )
    return {"status": "ok", "message": message, **summary}

