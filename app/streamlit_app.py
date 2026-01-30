from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Fish Counter Review", layout="wide")

VIDEO_MAX_HEIGHT_PX = 280

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  ts TEXT,
  raw_dir TEXT,
  m1 INTEGER,
  m2 INTEGER,
  m3 INTEGER,
  video_abs TEXT,
  video_rel TEXT,
  has_video INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_status (
  event_id TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
  false_trigger INTEGER DEFAULT 0,
  notes TEXT,
  reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS counts (
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  species TEXT NOT NULL,
  movement TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (event_id, species, movement)
);
"""


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    # Streamlit app versions evolve over time. If a user already has an existing
    # SQLite file created by an older version, CREATE TABLE IF NOT EXISTS will
    # not add new columns. Apply lightweight migrations here.
    _migrate_schema(conn)
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, col_type: str
) -> None:
    cols = _table_columns(conn, table)
    if column in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Ensure the on-disk DB matches the current schema.

    SQLite does not support many ALTER TABLE operations, but adding columns is safe
    and sufficient for our version-to-version evolution.
    """
    # Ensure required columns exist on older DBs.
    required_events_cols = {
        "ts": "TEXT",
        "raw_dir": "TEXT",
        "m1": "INTEGER",
        "m2": "INTEGER",
        "m3": "INTEGER",
        "video_abs": "TEXT",
        "video_rel": "TEXT",
        "has_video": "INTEGER DEFAULT 0",
    }

    # If the table does not exist for some reason, SCHEMA_SQL will have created it.
    for col, typ in required_events_cols.items():
        _add_column_if_missing(conn, "events", col, typ)

    required_status_cols = {
        "false_trigger": "INTEGER DEFAULT 0",
        "notes": "TEXT",
        "reviewed_at": "TEXT",
    }
    for col, typ in required_status_cols.items():
        _add_column_if_missing(conn, "event_status", col, typ)

    conn.commit()


def upsert_events(conn: sqlite3.Connection, rows: List[Dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT INTO events(event_id, ts, raw_dir, m1, m2, m3, video_abs, video_rel, has_video)
        VALUES(:event_id, :ts, :raw_dir, :m1, :m2, :m3, :video_abs, :video_rel, :has_video)
        ON CONFLICT(event_id) DO UPDATE SET
          ts=excluded.ts,
          raw_dir=excluded.raw_dir,
          m1=excluded.m1,
          m2=excluded.m2,
          m3=excluded.m3,
          video_abs=excluded.video_abs,
          video_rel=excluded.video_rel,
          has_video=excluded.has_video
        """,
        rows,
    )
    conn.commit()


def find_first_log(project_root: Path) -> Optional[Path]:
    for p in project_root.glob("*.log"):
        return p
    for p in project_root.glob("*.LOG"):
        return p
    return None


def parse_log(log_path: Path) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    """Parse a Riverwatcher *.log export into event rows.

    This parser assumes a [data] section may contain one "folder stamp" row (YY MM DD HH MM)
    followed by event rows that look like:
      <id> <m1> <m2> <month> <day> <hour> <minute> <+/-> <m3>
    """
    diagnostics: Dict[str, object] = {
        "log_path": str(log_path),
        "events_parsed": 0,
        "folder_stamp": None,
    }

    rows: List[Dict[str, object]] = []
    in_data = False
    saw_data_marker = False
    base_year: Optional[int] = None
    fish_event_re = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?) - "
        r"Fish measurement received with ID (?P<event_id>\d+)\s*$"
    )

    with log_path.open("r", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(("#", ";")):
                continue
            if line.lower() == "[data]":
                in_data = True
                saw_data_marker = True
                continue
            if saw_data_marker and not in_data:
                continue

            if not saw_data_marker:
                match = fish_event_re.match(line)
                if match:
                    ts_raw = match.group("ts")
                    try:
                        ts_dt = datetime.fromisoformat(ts_raw)
                        ts = ts_dt.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        ts = ts_raw.split(".")[0]
                    rows.append(
                        {
                            "event_id": match.group("event_id"),
                            "ts": ts,
                            "raw_dir": "",
                            "m1": None,
                            "m2": None,
                            "m3": None,
                        }
                    )
                continue

            parts = line.split()
            # folder stamp line: YY MM DD HH MM
            if len(parts) == 5 and parts[0].isdigit() and base_year is None:
                yy = int(parts[0])
                base_year = 2000 + yy
                diagnostics["folder_stamp"] = " ".join(parts)
                continue

            if len(parts) < 9:
                continue

            event_id = parts[0]
            try:
                m1 = int(parts[1])
                m2 = int(parts[2])
            except Exception:
                m1 = None
                m2 = None

            try:
                month = int(parts[3])
                day = int(parts[4])
                hour = int(parts[5])
                minute = int(parts[6])
            except Exception:
                continue

            raw_dir = parts[7]
            try:
                m3 = int(parts[8])
            except Exception:
                m3 = None

            year = base_year if base_year is not None else datetime.now().year
            ts = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00"

            rows.append(
                {
                    "event_id": str(event_id).strip(),
                    "ts": ts,
                    "raw_dir": raw_dir,
                    "m1": m1,
                    "m2": m2,
                    "m3": m3,
                }
            )

    diagnostics["events_parsed"] = len(rows)
    return rows, diagnostics


def _normalize_event_id(event_id: str) -> str:
    cleaned = str(event_id).strip()
    if cleaned.isdigit():
        return cleaned.lstrip("0") or "0"
    return cleaned


def index_videos(video_index_root: Path) -> Dict[str, Path]:
    """Index mp4s by stem (event id)."""
    idx: Dict[str, Path] = {}
    for p in video_index_root.rglob("*.mp4"):
        stem = p.stem.strip()
        if not stem:
            continue
        idx.setdefault(stem, p)
        idx.setdefault(_normalize_event_id(stem), p)
    return idx


def build_event_rows(project_root: Path, video_library_root: Path, video_index_root: Path) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    log_file = find_first_log(project_root)
    if not log_file:
        raise FileNotFoundError("No .log file found in Project root.")

    parsed, diag = parse_log(log_file)
    if not parsed:
        raise ValueError(
            "No events were parsed from the .log file. Check that the log contains a [data] section "
            "with event rows and that the project root points to the correct folder."
        )
    vidx = index_videos(video_index_root)

    rows: List[Dict[str, object]] = []
    matched = 0
    for r in parsed:
        eid = str(r["event_id"])
        vpath = vidx.get(eid) or vidx.get(_normalize_event_id(eid))
        has_video = 1 if vpath else 0
        if has_video:
            matched += 1
        if vpath:
            try:
                rel = str(vpath.relative_to(video_library_root))
            except Exception:
                rel = str(vpath)
            vabs = str(vpath)
        else:
            rel = ""
            vabs = ""

        rows.append(
            {
                **r,
                "video_abs": vabs,
                "video_rel": rel,
                "has_video": has_video,
            }
        )

    diag["videos_indexed"] = len(vidx)
    diag["videos_matched"] = matched
    diag["project_root"] = str(project_root)
    diag["video_index_root"] = str(video_index_root)
    diag["video_library_root"] = str(video_library_root)
    return rows, diag


def get_unreviewed_event_ids(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT e.event_id
        FROM events e
        LEFT JOIN event_status s ON s.event_id = e.event_id
        WHERE s.reviewed_at IS NULL
        -- Process events in chronological order whenever possible.
        -- (ts is stored as an ISO string, so lexical sort works.)
        ORDER BY
          (e.ts IS NULL) ASC,
          e.ts ASC,
          CASE WHEN e.event_id GLOB '[0-9]*' THEN CAST(e.event_id AS INTEGER) END ASC,
          e.event_id ASC
        """
    ).fetchall()
    return [r[0] for r in rows]


def get_event(conn: sqlite3.Connection, event_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()


def load_counts(conn: sqlite3.Connection, event_id: str) -> Dict[Tuple[str, str], int]:
    rows = conn.execute(
        "SELECT species, movement, count FROM counts WHERE event_id=?",
        (event_id,),
    ).fetchall()
    return {(r[0], r[1]): int(r[2]) for r in rows}


def load_status(conn: sqlite3.Connection, event_id: str) -> Dict[str, object]:
    r = conn.execute(
        "SELECT false_trigger, notes, reviewed_at FROM event_status WHERE event_id=?",
        (event_id,),
    ).fetchone()
    if not r:
        return {"false_trigger": 0, "notes": "", "reviewed_at": None}
    return {"false_trigger": int(r[0] or 0), "notes": str(r[1] or ""), "reviewed_at": r[2]}


def save_event(
    conn: sqlite3.Connection,
    event_id: str,
    counts: Dict[Tuple[str, str], int],
    *,
    notes: str,
    false_trigger: int,
    reviewed_at: str,
) -> None:
    # Replace counts for event
    conn.execute("DELETE FROM counts WHERE event_id=?", (event_id,))
    rows = [
        {
            "event_id": event_id,
            "species": sp,
            "movement": mv,
            "count": int(ct),
        }
        for (sp, mv), ct in counts.items()
        if int(ct) > 0
    ]
    if rows:
        conn.executemany(
            """
            INSERT INTO counts(event_id, species, movement, count)
            VALUES(:event_id, :species, :movement, :count)
            """,
            rows,
        )

    conn.execute(
        """
        INSERT INTO event_status(event_id, false_trigger, notes, reviewed_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            false_trigger=excluded.false_trigger,
            notes=excluded.notes,
            reviewed_at=excluded.reviewed_at
        """,
        (event_id, int(false_trigger), notes, reviewed_at),
    )
    conn.commit()


def format_counts(counts: Dict[Tuple[str, str], int]) -> str:
    # e.g., "1 Chinook UP, 2 Rainbow DOWN"
    parts: List[str] = []
    for (sp, mv), ct in sorted(counts.items(), key=lambda x: (x[0][0], x[0][1])):
        if ct <= 0:
            continue
        mv_short = {"Up": "UP", "Down": "DOWN", "Stay": "STAY"}.get(mv, mv.upper())
        parts.append(f"{ct} {sp} {mv_short}")
    return ", ".join(parts) if parts else "(none)"


def get_events_summary(conn: sqlite3.Connection) -> Dict[str, int]:
    total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    with_video = conn.execute("SELECT COUNT(*) FROM events WHERE has_video=1").fetchone()[0]
    reviewed = conn.execute("SELECT COUNT(*) FROM event_status WHERE reviewed_at IS NOT NULL").fetchone()[0]
    return {"total_events": int(total), "with_video": int(with_video), "reviewed": int(reviewed)}


def get_events_overview(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT e.event_id, e.ts, e.video_rel, e.has_video,
               s.reviewed_at, s.false_trigger, s.notes
        FROM events e
        LEFT JOIN event_status s ON s.event_id = e.event_id
        ORDER BY
          (e.ts IS NULL) ASC,
          e.ts ASC,
          CASE WHEN e.event_id GLOB '[0-9]*' THEN CAST(e.event_id AS INTEGER) END ASC,
          e.event_id ASC
        """
    ).fetchall()


def _clean_path(s: str) -> str:
    return (s or "").strip().strip('"')


def init_state() -> None:
    defaults = {
        "project_root": "",
        "video_index_root": "",
        "video_library_root": "",
        "db_path": "",
        "diagnostics": {},
        "ready": False,
        "queue": [],
        "current_event_id": None,
        "selected_event_id": None,
        "categories": "Chinook,Rainbow,Atlantic,Brown,Coho,Unknown,Non fish",
        "movement": "Up",
        "notes": "",
        "_loaded_event_id": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# Sidebar
with st.sidebar:
    st.header("Project")
    st.text_input(
        "Project root (contains .log)",
        key="project_root",
        placeholder=r"C:\...\Ganaraska 2025\10312025-11282025",
    )
    st.text_input(
        "Video index root (MP4s live under here; usually same as Project root)",
        key="video_index_root",
        placeholder=r"C:\...\Ganaraska 2025\10312025-11282025",
    )
    st.text_input(
        "Video library root (for relative video paths)",
        key="video_library_root",
        placeholder=r"C:\...\Counter Videos 2025",
    )

    st.divider()
    st.subheader("Quick entry")
    st.text_input("Categories (comma-separated)", key="categories")

    st.divider()
    if st.button("Index / Reload project", type="primary"):
        pr = _clean_path(st.session_state.project_root)
        vir = _clean_path(st.session_state.video_index_root) or pr
        vlr = _clean_path(st.session_state.video_library_root) or vir

        if not pr:
            st.error("Please enter a Project root.")
            st.stop()

        project_root = Path(pr)
        video_index_root = Path(vir)
        video_library_root = Path(vlr)

        db_path = project_root / "fishcounter.sqlite"
        conn = connect_db(db_path)

        try:
            rows, diag = build_event_rows(project_root, video_library_root, video_index_root)
        except Exception as e:
            st.session_state.ready = False
            st.session_state.diagnostics = {"error": str(e)}
            st.error(str(e))
            st.stop()

        upsert_events(conn, rows)
        q = get_unreviewed_event_ids(conn)

        st.session_state.db_path = str(db_path)
        st.session_state.queue = q
        st.session_state.current_event_id = q[0] if q else None
        st.session_state.diagnostics = diag
        st.session_state.ready = True
        st.session_state._loaded_event_id = None

        st.success(f"Indexed {len(rows)} events. Unreviewed: {len(q)}")


st.title("Fish Counter Review")

if not st.session_state.ready:
    st.info("Enter a project root folder in the sidebar and click 'Index / Reload project'.")
    if st.session_state.diagnostics:
        with st.expander("Diagnostics", expanded=True):
            st.write(st.session_state.diagnostics)
    st.stop()

conn = connect_db(Path(st.session_state.db_path))
summary = get_events_summary(conn)
event_overview = get_events_overview(conn)

# Refresh queue
if not st.session_state.queue:
    st.session_state.queue = get_unreviewed_event_ids(conn)

# Ensure current
if st.session_state.current_event_id is None and st.session_state.queue:
    st.session_state.current_event_id = st.session_state.queue[0]

event_id = st.session_state.current_event_id
st.subheader("Event browser")
filter_label = st.radio(
    "Show",
    options=["All", "Unreviewed", "Reviewed"],
    horizontal=True,
    index=0,
)
overview_records: List[Dict[str, object]] = []
for row in event_overview:
    reviewed = bool(row["reviewed_at"])
    if filter_label == "Unreviewed" and reviewed:
        continue
    if filter_label == "Reviewed" and not reviewed:
        continue
    overview_records.append(
        {
            "Event #": row["event_id"],
            "Time stamp": row["ts"],
            "Video": row["video_rel"],
            "Reviewed": row["reviewed_at"] or "",
            "False trigger": int(row["false_trigger"] or 0),
            "Notes": row["notes"] or "",
        }
    )

overview_df = pd.DataFrame(
    overview_records,
    columns=["Event #", "Time stamp", "Video", "Reviewed", "False trigger", "Notes"],
)
if overview_df.empty:
    st.info("No events match the selected filter.")
else:
    browser = st.dataframe(
        overview_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
    )
    if browser.selection.rows:
        st.session_state.selected_event_id = overview_df.iloc[browser.selection.rows[0]]["Event #"]

    select_col, queue_col = st.columns([1, 1])
    with select_col:
        if st.button("Load selected event", use_container_width=True):
            if st.session_state.selected_event_id:
                st.session_state.current_event_id = str(st.session_state.selected_event_id)
                st.session_state._loaded_event_id = None
                st.rerun()
    with queue_col:
        if st.button("Resume next unreviewed", use_container_width=True):
            st.session_state.current_event_id = st.session_state.queue[0] if st.session_state.queue else None
            st.session_state._loaded_event_id = None
            st.rerun()

if event_id is None:
    st.success("All events reviewed. Select an event above to review again.")

if event_id is not None:
    cur = get_event(conn, event_id)
    if not cur:
        st.error("Current event not found in database. Re-index the project.")
        st.stop()

    # Load existing counts/status once per event change
    if st.session_state._loaded_event_id != event_id:
        st.session_state._counts = load_counts(conn, event_id)
        st.session_state._actions = []  # list of (species, movement)
        st.session_state._status = load_status(conn, event_id)
        st.session_state.notes = st.session_state._status.get("notes", "")
        st.session_state._loaded_event_id = event_id

    counts: Dict[Tuple[str, str], int] = st.session_state._counts
    status = st.session_state._status

    # Main layout
    left, right = st.columns([2.2, 1.0], gap="large")

    with left:
        st.subheader(f"Event {cur['event_id']}")
        st.caption(f"Timestamp: {cur['ts']}  |  Video: {cur['video_rel'] or '(not found)'}")
        if cur["has_video"] and cur["video_abs"]:
            st.markdown(
                f"""
                <style>
                .fish-video video {{
                    max-height: {VIDEO_MAX_HEIGHT_PX}px;
                    width: 100%;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="fish-video">', unsafe_allow_html=True)
            st.video(cur["video_abs"], autoplay=True, muted=True)
            st.markdown("</div>", unsafe_allow_html=True)
            components.html(
                """
                <script>
                const tryAutoPlay = () => {
                  const video = window.parent.document.querySelector(".fish-video video");
                  if (!video) return;
                  video.muted = true;
                  video.setAttribute("playsinline", "");
                  video.setAttribute("webkit-playsinline", "");
                  const storageKey = "fish_counter_playback_rate";
                  const storedRate = window.localStorage.getItem(storageKey);
                  if (storedRate) {
                    const parsedRate = Number.parseFloat(storedRate);
                    if (!Number.isNaN(parsedRate)) {
                      video.playbackRate = parsedRate;
                    }
                  }
                  if (!video.__fishCounterRateListenerAttached) {
                    video.addEventListener("ratechange", () => {
                      window.localStorage.setItem(storageKey, video.playbackRate.toString());
                    });
                    video.__fishCounterRateListenerAttached = true;
                  }
                  const playPromise = video.play();
                  if (playPromise && typeof playPromise.catch === "function") {
                    playPromise.catch(() => {});
                  }
                };
                setTimeout(tryAutoPlay, 200);
                setTimeout(tryAutoPlay, 1000);
                </script>
                """,
                height=0,
                width=0,
            )
        else:
            st.warning("No video matched for this event ID.")

        # Note: counts shown include any in-progress clicks that have not yet been saved.
        st.markdown("**Current tally:** " + format_counts(counts))
        if status.get("reviewed_at"):
            st.caption(f"Reviewed: {status.get('reviewed_at')}  |  False trigger: {status.get('false_trigger', 0)}")

    with right:
        st.subheader("Count fish")

        # Live, in-progress tally (what will be saved when you click Save & Next)
        st.markdown("**Tally to be saved:** " + format_counts(counts))

        # Movement selector (defaults to Up).
        # User preference: show text for Up/Down, keep "x" as the stay toggle.
        mv_label = st.radio(
            "Movement",
            options=["Up", "Down", "x"],
            horizontal=True,
            index={"Up": 0, "Down": 1, "Stay": 2}.get(st.session_state.movement, 0),
            key="mv_radio",
        )
        movement = mv_label if mv_label != "x" else "Stay"
        st.session_state.movement = movement

        st.caption("Movement: Up = Upstream, Down = Downstream, x = Stay in frame")

        cats = [c.strip() for c in (st.session_state.categories or "").split(",") if c.strip()]
        if not cats:
            cats = ["Chinook", "Rainbow", "Unknown", "Non fish"]

        st.caption("Click species to add 1 fish at the selected movement. Use Undo for mistakes, then Save & Next.")

        # Buttons grid
        ncols = 2 if len(cats) <= 10 else 3
        cols = st.columns(ncols)

        def add_observation(species: str, mv: str) -> None:
            key = (species, mv)
            counts[key] = int(counts.get(key, 0)) + 1
            st.session_state._actions.append(key)

        clicked: Optional[str] = None
        for i, cat in enumerate(cats):
            with cols[i % ncols]:
                if st.button(cat, use_container_width=True, key=f"sp_{event_id}_{i}"):
                    clicked = cat

        if clicked is not None:
            add_observation(clicked, movement)
            st.rerun()

        # Quick tools
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Undo", use_container_width=True):
                if st.session_state._actions:
                    sp, mv = st.session_state._actions.pop()
                    counts[(sp, mv)] = max(int(counts.get((sp, mv), 0)) - 1, 0)
                st.rerun()
        with b2:
            if st.button("Clear", use_container_width=True):
                st.session_state._counts = {}
                st.session_state._actions = []
                st.rerun()

        st.text_area("Notes (optional)", key="notes", height=80)

        if st.button("Save & Next", type="primary", use_container_width=True):
            reviewed_at = datetime.now().isoformat(timespec="seconds")
            save_event(conn, event_id, counts, notes=str(st.session_state.notes or ""), false_trigger=0, reviewed_at=reviewed_at)
            st.session_state.queue = get_unreviewed_event_ids(conn)
            st.session_state.current_event_id = st.session_state.queue[0] if st.session_state.queue else None
            st.session_state._loaded_event_id = None
            st.rerun()

        nav1, nav2 = st.columns(2)
        with nav1:
            if st.button("Back", use_container_width=True):
                prev = conn.execute(
                    """
                    SELECT event_id FROM events
                    WHERE (ts < ? OR (ts = ? AND CAST(event_id AS INTEGER) < CAST(? AS INTEGER)))
                    ORDER BY ts DESC, CAST(event_id AS INTEGER) DESC
                    LIMIT 1
                    """,
                    (cur["ts"], cur["ts"], cur["event_id"]),
                ).fetchone()
                if prev:
                    st.session_state.current_event_id = prev[0]
                    st.session_state._loaded_event_id = None
                    st.rerun()
        with nav2:
            if st.button("Skip", use_container_width=True):
                if st.session_state.queue and st.session_state.queue[0] == event_id:
                    st.session_state.queue = st.session_state.queue[1:]
                st.session_state.current_event_id = st.session_state.queue[0] if st.session_state.queue else None
                st.session_state._loaded_event_id = None
                st.rerun()


st.divider()

colA, colB, colC, colD = st.columns(4)
colA.metric("Total events", summary["total_events"])
colB.metric("Videos matched", summary["with_video"])
colC.metric("Reviewed", summary["reviewed"])
colD.metric("Remaining", max(summary["total_events"] - summary["reviewed"], 0))

st.subheader("Counts summary")
summary_rows = conn.execute(
    """
    SELECT e.event_id, e.ts, c.species, c.movement, c.count
    FROM counts c
    JOIN events e ON e.event_id = c.event_id
    WHERE c.count > 0
    ORDER BY e.ts ASC, CAST(e.event_id AS INTEGER) ASC, c.species ASC, c.movement ASC
    """
).fetchall()

expanded_records: List[Dict[str, str]] = []
for row in summary_rows:
    for _ in range(int(row["count"])):
        expanded_records.append(
            {
                "Event #": row["event_id"],
                "Time stamp": row["ts"],
                "Fish species": row["species"],
                "Up or down": row["movement"],
            }
        )

summary_df = pd.DataFrame(
    expanded_records,
    columns=["Event #", "Time stamp", "Fish species", "Up or down"],
)
if summary_df.empty:
    st.info("No fish counted yet.")
else:
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

with st.expander("Diagnostics", expanded=False):
    st.write(st.session_state.diagnostics)
    st.write({"db": st.session_state.db_path})

    if st.button("Export CSV"):
        df = pd.read_sql_query(
            """
            SELECT e.event_id, e.ts, e.video_rel,
                   s.false_trigger, s.notes, s.reviewed_at,
                   c.species, c.movement, c.count
            FROM events e
            LEFT JOIN event_status s ON s.event_id = e.event_id
            LEFT JOIN counts c ON c.event_id = e.event_id
            ORDER BY e.ts ASC, CAST(e.event_id AS INTEGER) ASC
            """,
            conn,
        )
        out = Path(_clean_path(st.session_state.project_root)) / "fish_counts_export.csv"
        df.to_csv(out, index=False)
        st.success(f"Wrote {out}")
