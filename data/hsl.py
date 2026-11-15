"""
hsl.py – HSL data from Digitransit Routing API v2 (GraphQL).

Supports two modes:
1) Stop/station departure boards (preferred for the family dashboard)
2) Legacy journey-planner connections (kept for backwards compatibility)

Stop/station config example:

hsl:
  api_key: "your-subscription-key"
  stops:
    - name: "Bussipysäkki"
      stop_id: "A1291112"
      type: "stop"
      departures: 3
    - name: "Juna Helsinkiin"
      stop_id: "A1000204"
      type: "station"
      mode: "RAIL"
      headsign_contains: "Helsinki"
      departures: 3

The leading A used by some HSL/Reittiopas identifiers is accepted. Digitransit
GTFS ids themselves are normally HSL:<numeric-id>, so e.g. A1000204 is tried as
HSL:1000204 first.
"""

import json
from datetime import datetime
from pathlib import Path

import requests

CACHE_FILE = Path("cache/hsl.json")
DEFAULT_TTL_MIN = 10
API_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"

STOP_QUERY_TEMPLATE = """
query StopDepartures($id: String!, $startTime: Long!, $n: Int!) {
  SOURCE(id: $id) {
    gtfsId
    name
    code
    stoptimesWithoutPatterns(
      startTime: $startTime
      timeRange: 86400
      numberOfDepartures: $n
      omitCanceled: true
      omitNonPickups: true
    ) {
      serviceDay
      scheduledDeparture
      realtimeDeparture
      realtime
      realtimeState
      headsign
      trip {
        route {
          shortName
          mode
        }
      }
    }
  }
}
"""

ROUTE_QUERY = """
query NextTrips($fromLat: CoordinateValue!, $fromLon: CoordinateValue!, $toLat: CoordinateValue!, $toLon: CoordinateValue!, $when: OffsetDateTime!, $n: Int!) {
  planConnection(
    origin: {
      location: { coordinate: { latitude: $fromLat, longitude: $fromLon } }
    }
    destination: {
      location: { coordinate: { latitude: $toLat, longitude: $toLon } }
    }
    first: $n
    dateTime: { earliestDeparture: $when }
    modes: {
      transit: {
        transit: [
          { mode: BUS }
          { mode: TRAM }
          { mode: RAIL }
          { mode: SUBWAY }
          { mode: FERRY }
        ]
      }
    }
  ) {
    edges {
      node {
        startTime
        endTime
        legs {
          startTime
          mode
          route { shortName }
          from { name }
        }
      }
    }
  }
}
"""


class DataFetchError(Exception):
    pass


def _cache_is_fresh(ttl_minutes: int) -> bool:
    if not CACHE_FILE.exists():
        return False
    age = datetime.now().timestamp() - CACHE_FILE.stat().st_mtime
    return age < ttl_minutes * 60


def _load_cache() -> dict | None:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(data: dict):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _within_active_hours(active_hours: list) -> bool:
    if not active_hours or len(active_hours) < 2:
        return True
    hour = datetime.now().hour
    return active_hours[0] <= hour <= active_hours[1]


def _headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "digitransit-subscription-key": api_key,
    }


def _post_graphql(query: str, variables: dict, api_key: str) -> dict:
    try:
        resp = requests.post(
            API_URL,
            json={"query": query, "variables": variables},
            headers=_headers(api_key),
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as e:
        raise DataFetchError(f"HSL fetch failed: {e}") from e
    except ValueError as e:
        raise DataFetchError(f"HSL response was not valid JSON: {e}") from e

    errors = raw.get("errors")
    if errors:
        raise DataFetchError(
            f"HSL GraphQL error: {errors[0].get('message', errors)}"
        )
    return raw.get("data", {})


def _gtfs_id_candidates(value: str) -> list[str]:
    """Return likely Digitransit GTFS ids for a configured HSL identifier.

    Digitransit uses ids such as HSL:1000204. Some HSL/Reittiopas identifiers
    are encountered with an extra leading A (e.g. A1000204), so accept that
    notation too. We try the stripped form first and the literal form second.
    """
    value = str(value).strip()
    if not value:
        return []
    if ":" in value:
        return [value]

    candidates = []
    if len(value) > 1 and value[0].upper() == "A" and value[1:].isdigit():
        candidates.append(f"HSL:{value[1:]}")
    candidates.append(f"HSL:{value}")

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(candidates))


def _minutes_until(ts: int, now_ts: float) -> int:
    return max(0, int((ts - now_ts) / 60))


def _find_source(
    query: str,
    source_type: str,
    raw_id: str,
    start_time: int,
    n: int,
    api_key: str,
) -> tuple[dict | None, str | None]:
    """Try the plausible GTFS id forms and return the first matching source."""
    tried = []
    for gtfs_id in _gtfs_id_candidates(raw_id):
        tried.append(gtfs_id)
        data = _post_graphql(
            query,
            {"id": gtfs_id, "startTime": start_time, "n": n},
            api_key,
        )
        source = data.get(source_type)
        if source:
            return source, gtfs_id

    raise DataFetchError(
        f"HSL {source_type} '{raw_id}' was not found. Tried: {', '.join(tried)}"
    )


def _fetch_stop_boards(hsl_cfg: dict, api_key: str) -> dict:
    configured = hsl_cfg.get("stops") or []
    if not configured:
        raise DataFetchError("hsl.stops is empty")

    now_ts = datetime.now().timestamp()
    result = []

    for stop_cfg in configured:
        raw_id = str(stop_cfg.get("stop_id") or stop_cfg.get("id") or "").strip()
        if not raw_id:
            continue

        source_type = str(stop_cfg.get("type", "stop")).lower()
        if source_type not in ("stop", "station"):
            raise DataFetchError(
                f"Unknown HSL source type '{source_type}'. Use 'stop' or 'station'."
            )

        requested_n = max(1, int(stop_cfg.get("departures", 3)))
        # Fetch extra rows because local mode/headsign filters may remove some.
        fetch_n = min(50, max(requested_n * 6, 15))
        query = STOP_QUERY_TEMPLATE.replace("SOURCE", source_type)
        source, matched_gtfs_id = _find_source(
            query=query,
            source_type=source_type,
            raw_id=raw_id,
            start_time=int(now_ts),
            n=fetch_n,
            api_key=api_key,
        )

        wanted_mode = str(stop_cfg.get("mode", "")).upper().strip()
        wanted_headsign = (
            str(stop_cfg.get("headsign_contains", "")).strip().casefold()
        )
        wanted_lines = {
            str(v).casefold()
            for v in (stop_cfg.get("lines") or [])
            if str(v).strip()
        }

        departures = []
        for st in source.get("stoptimesWithoutPatterns") or []:
            if st.get("realtimeState") == "CANCELED":
                continue

            route = ((st.get("trip") or {}).get("route") or {})
            route_name = str(route.get("shortName") or "")
            mode = str(route.get("mode") or "")
            headsign = str(st.get("headsign") or "")

            if wanted_mode and mode.upper() != wanted_mode:
                continue
            if wanted_headsign and wanted_headsign not in headsign.casefold():
                continue
            if wanted_lines and route_name.casefold() not in wanted_lines:
                continue

            service_day = st.get("serviceDay")
            scheduled = st.get("scheduledDeparture")
            realtime = st.get("realtimeDeparture")
            if service_day is None or scheduled is None:
                continue

            seconds = (
                realtime
                if st.get("realtime") and realtime is not None
                else scheduled
            )
            try:
                dep_ts = int(service_day) + int(seconds)
            except (TypeError, ValueError):
                continue
            if dep_ts < now_ts:
                continue

            dep_dt = datetime.fromtimestamp(dep_ts)
            departures.append(
                {
                    "line": route_name or "?",
                    "headsign": headsign,
                    "departure": dep_dt.strftime("%H:%M"),
                    "minutes_until": _minutes_until(dep_ts, now_ts),
                    "realtime": bool(st.get("realtime")),
                    "mode": mode,
                }
            )

            if len(departures) >= requested_n:
                break

        result.append(
            {
                "name": str(stop_cfg.get("name") or source.get("name") or raw_id),
                "stop_id": raw_id,
                "gtfs_id": source.get("gtfsId") or matched_gtfs_id,
                "source_name": source.get("name") or "",
                "code": source.get("code") or "",
                "type": source_type,
                "departures": departures,
            }
        )

    if not result:
        raise DataFetchError("No usable HSL stops/stations were configured")

    return {
        "mode": "stops",
        "stops": result,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def _fetch_route_plan(config: dict, hsl_cfg: dict, api_key: str) -> dict:
    """Legacy point-to-point journey planning mode."""
    to_name = hsl_cfg.get("to_name", "")
    to_lat = hsl_cfg.get("to_lat")
    to_lon = hsl_cfg.get("to_lon")
    n = int(hsl_cfg.get("num_results", 3))

    if to_lat is None or to_lon is None:
        raise DataFetchError("hsl.to_lat and hsl.to_lon are required in config.yaml")

    loc = config.get("location", {})
    from_lat = loc.get("latitude")
    from_lon = loc.get("longitude")
    if from_lat is None or from_lon is None:
        raise DataFetchError(
            "location.latitude and location.longitude are required in config.yaml"
        )

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    data = _post_graphql(
        ROUTE_QUERY,
        {
            "fromLat": float(from_lat),
            "fromLon": float(from_lon),
            "toLat": float(to_lat),
            "toLon": float(to_lon),
            "when": now_iso,
            "n": n,
        },
        api_key,
    )

    min_walk_bus = int(hsl_cfg.get("min_walk_bus", 3))
    min_walk_rail = int(hsl_cfg.get("min_walk_rail", 15))
    edges = data.get("planConnection", {}).get("edges", [])
    now_ts = datetime.now().timestamp()
    connections = []

    for edge in edges:
        node = edge.get("node", {})
        start_iso = node.get("startTime")
        end_iso = node.get("endTime")
        legs = node.get("legs", [])
        if not start_iso:
            continue

        try:
            depart_dt = datetime.fromtimestamp(int(start_iso) / 1000)
            arrive_dt = (
                datetime.fromtimestamp(int(end_iso) / 1000) if end_iso else None
            )
        except (ValueError, TypeError):
            continue

        transit_legs = [leg for leg in legs if leg.get("mode") != "WALK"]
        lines_str = " -> ".join(
            leg.get("route", {}).get("shortName", "?") for leg in transit_legs
        )

        first_transit_minutes = None
        first_mode = transit_legs[0].get("mode", "") if transit_legs else ""
        first_stop = (
            transit_legs[0].get("from", {}).get("name", "")
            if transit_legs
            else ""
        )
        first_depart_str = ""
        if transit_legs:
            try:
                first_ts = int(transit_legs[0].get("startTime", 0)) / 1000
                first_transit_minutes = int((first_ts - now_ts) / 60)
                first_depart_str = datetime.fromtimestamp(first_ts).strftime("%H:%M")
            except (ValueError, TypeError):
                pass

        min_needed = (
            min_walk_rail if first_mode in ("RAIL", "SUBWAY") else min_walk_bus
        )
        if first_transit_minutes is not None and first_transit_minutes < min_needed:
            continue

        walk_minutes = 0
        if transit_legs:
            try:
                walk_minutes = max(
                    0,
                    int(
                        (
                            float(transit_legs[0].get("startTime", 0)) / 1000
                            - depart_dt.timestamp()
                        )
                        / 60
                    ),
                )
            except (ValueError, TypeError):
                pass

        connections.append(
            {
                "departure": depart_dt.strftime("%H:%M"),
                "arrival": arrive_dt.strftime("%H:%M") if arrive_dt else "",
                "minutes_until": int((depart_dt.timestamp() - now_ts) / 60),
                "lines": lines_str,
                "to": to_name,
                "walk_minutes": walk_minutes,
                "first_mode": first_mode,
                "first_stop": first_stop,
                "first_depart": first_depart_str,
            }
        )

    return {
        "mode": "route",
        "connections": connections,
        "to_name": to_name,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def drop_past_departures(hsl: dict | None) -> dict | None:
    """Age cached minute counters between API fetches for partial refreshes."""
    if not hsl:
        return hsl
    try:
        fetched_at = datetime.fromisoformat(hsl["fetched_at"])
    except (KeyError, ValueError):
        return hsl

    elapsed_min = (datetime.now() - fetched_at).total_seconds() / 60

    if hsl.get("mode") == "stops" or hsl.get("stops"):
        updated_stops = []
        for stop in hsl.get("stops", []):
            deps = []
            for dep in stop.get("departures", []):
                cur = dep.get("minutes_until", 0) - elapsed_min
                if cur >= 0:
                    deps.append({**dep, "minutes_until": int(cur)})
            updated_stops.append({**stop, "departures": deps})
        return {**hsl, "stops": updated_stops}

    updated = []
    for conn in hsl.get("connections", []):
        cur = conn.get("minutes_until", 0) - elapsed_min
        if cur > 0:
            updated.append({**conn, "minutes_until": int(cur)})
    return {**hsl, "connections": updated}


def fetch(config: dict, use_cache: bool = True) -> dict:
    cache_cfg = config.get("cache", {})
    ttl = int(cache_cfg.get("hsl_ttl_minutes", DEFAULT_TTL_MIN))
    active_hours = cache_cfg.get("hsl_active_hours", [])
    hsl_cfg = config.get("hsl", {})
    stop_mode = bool(hsl_cfg.get("stops"))

    if use_cache and _cache_is_fresh(ttl):
        cached = _load_cache()
        if cached:
            if stop_mode and (cached.get("mode") == "stops" or cached.get("stops")):
                return cached
            if (
                not stop_mode
                and cached.get("mode") != "stops"
                and not cached.get("stops")
            ):
                return cached

    if not _within_active_hours(active_hours):
        cached = _load_cache() if use_cache else None
        if cached:
            cached["_stale"] = True
            return cached
        return {
            "mode": "stops" if stop_mode else "route",
            "stops": [] if stop_mode else None,
            "connections": [] if not stop_mode else None,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }

    api_key = str(hsl_cfg.get("api_key", "")).strip()
    if not api_key:
        raise DataFetchError(
            "HSL API key missing. Register at https://portal-api.digitransit.fi/ "
            "and add hsl.api_key to config.yaml."
        )

    try:
        data = (
            _fetch_stop_boards(hsl_cfg, api_key)
            if stop_mode
            else _fetch_route_plan(config, hsl_cfg, api_key)
        )
    except DataFetchError:
        # Normal dashboard runs may fall back to the last known data. However,
        # --no-cache is explicitly a diagnostic/forced-refresh mode, so surface
        # the real error instead of hiding it behind stale cache data.
        if use_cache:
            cached = _load_cache()
            if cached:
                cached["_stale"] = True
                return cached
        raise

    _save_cache(data)
    return data
