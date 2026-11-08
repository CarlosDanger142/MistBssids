#!/usr/bin/env python3
"""
Mist AP BSSID Finder - desktop GUI

A GUI equivalent of allynjcrowe/mist-get_bssid (main.py + mist_client.py).
Original: https://github.com/allynjcrowe/mist-get_bssid  (GPL-3.0, Allyn Crowe, Nexum)
This derivative work is therefore also offered under GPL-3.0.

For each connected AP it reports:
    HostName, Location (map name), MAC, 2.4/5/6 GHz BSSIDs, LLDP switch name + port

Input modes
    1. Inventory CSV   - the export from the Mist portal inventory page (same as the
                         original script; one stats API call per AP).
    2. All APs in site - no CSV needed; pulls every AP's stats in a few paged calls.

Requires:  Python 3.8+, `requests`   (optional: `keyring` to store the token in the
OS keychain).    Run:  python mist_bssid_gui.py
"""
import csv
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import requests

try:  # optional
    import keyring
except Exception:  # pragma: no cover
    keyring = None

APP_NAME = "Mist AP BSSID Finder"
SETTINGS_PATH = Path.home() / ".mist_bssid_gui.json"
KEYRING_SERVICE = "mist-bssid-gui"

REGIONS = {
    "Global 01 (api.mist.com)": "https://api.mist.com",
    "Global 02 (api.gc1.mist.com)": "https://api.gc1.mist.com",
    "Global 03 (api.ac2.mist.com)": "https://api.ac2.mist.com",
    "Global 04 (api.gc2.mist.com)": "https://api.gc2.mist.com",
    "Global 05 (api.gc4.mist.com)": "https://api.gc4.mist.com",
    "EMEA 01 (api.eu.mist.com)": "https://api.eu.mist.com",
    "EMEA 02 (api.gc3.mist.com)": "https://api.gc3.mist.com",
    "EMEA 03 (api.ac6.mist.com)": "https://api.ac6.mist.com",
    "EMEA 04 (api.gc6.mist.com)": "https://api.gc6.mist.com",
    "APAC 01 (api.ac5.mist.com)": "https://api.ac5.mist.com",
    "APAC 02 (api.gc5.mist.com)": "https://api.gc5.mist.com",
    "APAC 03 (api.gc7.mist.com)": "https://api.gc7.mist.com",
}

COLUMNS = ("HostName", "Location", "MAC", "2.4 GHz BSSID", "5 GHz BSSID",
           "6 GHz BSSID", "Switch Name", "Switch Port")

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


# --------------------------------------------------------------------------- #
# Core logic (no GUI) - mirrors the original script
# --------------------------------------------------------------------------- #
class MistError(Exception):
    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal  # fatal = stop the whole run (bad token, no access)


class Cancelled(Exception):
    pass


class MistClient:
    """Small GET-only Mist API client with 429 backoff and readable errors."""

    def __init__(self, base_url, token, log=None, cancel=None, timeout=30):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": "Token " + token,
        })
        self.log = log or (lambda *a: None)
        self.cancel = cancel or threading.Event()
        self.timeout = timeout

    def _sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.cancel.is_set():
                raise Cancelled()
            time.sleep(0.2)

    def get(self, path, params=None):
        url = self.base + path
        for _ in range(6):
            if self.cancel.is_set():
                raise Cancelled()
            self.log("log", "GET " + url)
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                raise MistError("Network error calling %s: %s" % (url, exc))
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    raise MistError("Invalid JSON returned from " + url)
            if resp.status_code == 429:
                try:
                    wait = float(resp.headers.get("Retry-After", 5))
                except ValueError:
                    wait = 5
                self.log("log", "Rate limited (429); waiting %.0fs" % wait)
                self._sleep(wait)
                continue
            if resp.status_code == 401:
                raise MistError("401 Unauthorized - check the API token and region.", fatal=True)
            if resp.status_code == 403:
                raise MistError("403 Forbidden - the token cannot access this org/site.", fatal=True)
            if resp.status_code == 404:
                raise MistError("404 Not found: " + url)
            raise MistError("HTTP %s from %s: %s" % (resp.status_code, url, resp.text[:300]))
        raise MistError("Gave up after repeated rate limiting (429).", fatal=True)


def radio_bssid(radio_mac):
    """Same formatting as the original script: '<mac>-<second-to-last char>f'."""
    if not radio_mac:
        return ""
    return "%s-%sf" % (radio_mac, radio_mac[-2:-1])


def normalize_mac(mac):
    return (mac or "").replace(":", "").replace("-", "").strip().lower()


def build_row(name, mac, stats, map_names):
    radios = stats.get("radio_stat") or {}

    def band(key):
        return radio_bssid((radios.get(key) or {}).get("mac") or "")

    lldp = stats.get("lldp_stat") or {}
    ap_map = map_names.get(stats.get("map_id"), "Not on Map")
    return [name or stats.get("name") or "", ap_map, mac,
            band("band_24"), band("band_5"), band("band_6"),
            lldp.get("system_name") or "", lldp.get("port_id") or ""]


def read_inventory(path):
    """Read the Mist portal inventory export (needs Name, MAC Address; Status optional)."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        for needed in ("MAC Address",):
            if needed not in fields:
                raise MistError("CSV is missing the '%s' column. Columns found: %s"
                                % (needed, ", ".join(fields) or "none"))
        return list(reader)


def fetch_maps(client, site_id):
    data = client.get("/api/v1/sites/%s/maps" % site_id)
    return {m.get("id"): m.get("name", "") for m in data}


def fetch_all_ap_stats(client, site_id, limit=1000, max_pages=50):
    out = []
    for page in range(1, max_pages + 1):
        batch = client.get("/api/v1/sites/%s/stats/devices" % site_id,
                           params={"type": "ap", "limit": limit, "page": page})
        out.extend(batch)
        if len(batch) < limit:
            break
    return out


def fetch_orgs(client):
    me = client.get("/api/v1/self")
    orgs = {}
    for priv in me.get("privileges", []):
        if priv.get("scope") == "org" and priv.get("org_id"):
            orgs[priv["org_id"]] = priv.get("name") or priv["org_id"]
    return orgs  # {org_id: name}


def fetch_sites(client, org_id):
    data = client.get("/api/v1/orgs/%s/sites" % org_id, params={"limit": 1000})
    return {s["id"]: s.get("name", s["id"]) for s in data}  # {site_id: name}


def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def run_job(cfg, emit, cancel, client=None):
    """Worker body. `emit(kind, *payload)` streams updates to the GUI."""
    client = client or MistClient(cfg["base_url"], cfg["token"], emit, cancel)
    site = cfg["site_id"]
    rows, skipped, errors = [], 0, 0

    emit("log", "Retrieving site maps...")
    maps = fetch_maps(client, site)

    if cfg["mode"] == "csv":
        inventory = read_inventory(cfg["csv_path"])
        total = len(inventory)
        emit("log", "Loaded %d inventory rows from CSV" % total)
        for i, ap in enumerate(inventory, 1):
            if cancel.is_set():
                raise Cancelled()
            emit("progress", i - 1, total)
            if (ap.get("Status") or "").strip().lower() == "disconnected":
                skipped += 1  # no BSSID data for disconnected APs
                continue
            mac = normalize_mac(ap.get("MAC Address"))
            if not mac:
                errors += 1
                emit("log", "Row %d has no MAC address; skipped" % i)
                continue
            try:
                stats = client.get("/api/v1/sites/%s/stats/devices/00000000-0000-0000-1000-%s"
                                   % (site, mac))
            except MistError as exc:
                if exc.fatal:
                    raise
                errors += 1
                emit("log", "ERROR for %s: %s" % (mac, exc))
                continue
            row = build_row(ap.get("Name"), mac, stats, maps)
            rows.append(row)
            emit("row", row)
        emit("progress", total, total)
    else:
        emit("log", "Retrieving all AP stats for the site...")
        all_stats = fetch_all_ap_stats(client, site)
        total = len(all_stats)
        emit("log", "Site returned %d APs" % total)
        for i, stats in enumerate(all_stats, 1):
            if cancel.is_set():
                raise Cancelled()
            emit("progress", i - 1, total)
            if (stats.get("status") or "").lower() != "connected":
                skipped += 1
                continue
            row = build_row(stats.get("name"), normalize_mac(stats.get("mac")), stats, maps)
            rows.append(row)
            emit("row", row)
        emit("progress", total, total)

    saved = None
    if cfg.get("autosave_dir"):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = Path(cfg["autosave_dir"]) / ("ap_list-%s.csv" % stamp)
        n = 1
        while target.exists():
            n += 1
            target = Path(cfg["autosave_dir"]) / ("ap_list-%s-%d.csv" % (stamp, n))
        saved = str(target)
        write_csv(saved, rows)
        emit("log", "Saved " + saved)
    return {"rows": len(rows), "skipped": skipped, "errors": errors, "saved": saved}


# --------------------------------------------------------------------------- #
# Settings / .env helpers
# --------------------------------------------------------------------------- #
def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        return {}


def save_settings(data):
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def read_dotenv(path=".env"):
    """Tiny .env reader so the original script's .env can pre-fill the form."""
    values = {}
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    except Exception:
        pass
    return values


def resolve_base_url(text):
    text = (text or "").strip()
    if text in REGIONS:
        return REGIONS[text]
    if text:
        url = text if text.startswith("http") else "https://" + text
        url = url.replace("{}", "").rstrip("/")
        # A pasted portal address (https://manage.gc4.mist.com/...) -> API host
        match = re.match(r"https?://manage\.((?:[a-z0-9]+\.)?mist\.com)", url)
        if match:
            return "https://api." + match.group(1)
        return url
    return REGIONS["Global 01 (api.mist.com)"]


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1150x780")
        self.minsize(950, 620)

        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.rows = []
        self.org_map = {}   # label -> id
        self.site_map = {}  # label -> id
        self.sort_state = {}
        self.settings = load_settings()

        self._build()
        self._prefill()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- layout ----------------------------------------------------------- #
    def _build(self):
        pad = {"padx": 6, "pady": 4}
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        conn = ttk.LabelFrame(root, text="Mist connection", padding=8)
        conn.pack(fill="x")
        conn.columnconfigure(1, weight=1)
        conn.columnconfigure(3, weight=1)

        ttk.Label(conn, text="Region / API URL").grid(row=0, column=0, sticky="w", **pad)
        self.region = ttk.Combobox(conn, values=list(REGIONS), width=34)
        self.region.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(conn, text="API token").grid(row=0, column=2, sticky="w", **pad)
        self.token = ttk.Entry(conn, show="*")
        self.token.grid(row=0, column=3, sticky="ew", **pad)
        self.show_token = tk.BooleanVar(value=False)
        ttk.Checkbutton(conn, text="Show", variable=self.show_token,
                        command=lambda: self.token.config(show="" if self.show_token.get() else "*")
                        ).grid(row=0, column=4, **pad)

        ttk.Label(conn, text="Organization").grid(row=1, column=0, sticky="w", **pad)
        self.org = ttk.Combobox(conn)
        self.org.grid(row=1, column=1, sticky="ew", **pad)
        self.org.bind("<<ComboboxSelected>>", lambda e: self._load_sites())
        ttk.Label(conn, text="Site").grid(row=1, column=2, sticky="w", **pad)
        self.site = ttk.Combobox(conn)
        self.site.grid(row=1, column=3, sticky="ew", **pad)
        self.load_btn = ttk.Button(conn, text="Load orgs && sites", command=self._load_orgs)
        self.load_btn.grid(row=1, column=4, **pad)

        self.remember = tk.BooleanVar(value=False)
        if keyring is not None:
            ttk.Checkbutton(conn, text="Remember token in system keychain",
                            variable=self.remember).grid(row=2, column=1, columnspan=2,
                                                         sticky="w", **pad)
        ttk.Label(conn, text="Tip: you can also paste an Org/Site ID directly into the boxes.",
                  foreground="gray").grid(row=2, column=3, columnspan=2, sticky="e", **pad)

        src = ttk.LabelFrame(root, text="Source and output", padding=8)
        src.pack(fill="x", pady=(8, 0))
        src.columnconfigure(1, weight=1)
        self.mode = tk.StringVar(value="csv")
        ttk.Radiobutton(src, text="Inventory CSV (portal export)", variable=self.mode,
                        value="csv").grid(row=0, column=0, sticky="w", **pad)
        self.csv_path = ttk.Entry(src)
        self.csv_path.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(src, text="Browse...", command=self._browse_csv).grid(row=0, column=2, **pad)
        ttk.Radiobutton(src, text="All APs in the selected site (no CSV)", variable=self.mode,
                        value="site").grid(row=1, column=0, columnspan=2, sticky="w", **pad)
        self.autosave = tk.BooleanVar(value=True)
        ttk.Checkbutton(src, text="Auto-save CSV to folder:", variable=self.autosave
                        ).grid(row=2, column=0, sticky="w", **pad)
        self.out_dir = ttk.Entry(src)
        self.out_dir.grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(src, text="Browse...", command=self._browse_out).grid(row=2, column=2, **pad)

        bar = ttk.Frame(root)
        bar.pack(fill="x", pady=(8, 0))
        self.run_btn = ttk.Button(bar, text="Run", command=self._start)
        self.run_btn.pack(side="left", padx=4)
        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)
        ttk.Button(bar, text="Export CSV...", command=self._export).pack(side="left", padx=4)
        ttk.Button(bar, text="Copy rows", command=self._copy).pack(side="left", padx=4)
        ttk.Button(bar, text="Clear", command=self._clear).pack(side="left", padx=4)
        ttk.Label(bar, text="Filter:").pack(side="left", padx=(24, 4))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self._refresh_table())
        ttk.Entry(bar, textvariable=self.filter_var, width=28).pack(side="left")

        prog = ttk.Frame(root)
        prog.pack(fill="x", pady=(8, 0))
        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)
        self.status = ttk.Label(prog, text="Ready", width=44, anchor="e")
        self.status.pack(side="left", padx=8)

        panes = ttk.PanedWindow(root, orient="vertical")
        panes.pack(fill="both", expand=True, pady=(8, 0))

        table_frame = ttk.Frame(panes)
        self.tree = ttk.Treeview(table_frame, columns=COLUMNS, show="headings",
                                 selectmode="extended")
        widths = (170, 150, 120, 150, 150, 150, 160, 100)
        for col, w in zip(COLUMNS, widths):
            self.tree.heading(col, text=col, command=lambda c=col: self._sort(c))
            self.tree.column(col, width=w, anchor="w")
        ysb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        panes.add(table_frame, weight=4)

        log_frame = ttk.Frame(panes)
        self.log_text = tk.Text(log_frame, height=7, state="disabled", wrap="none")
        lsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb.pack(side="left", fill="y")
        panes.add(log_frame, weight=1)

    def _prefill(self):
        env = read_dotenv()  # lets the original script's .env pre-fill the form
        s = self.settings
        base = env.get("api_base_url", "").replace("{}", "").rstrip("/")
        region_text = s.get("region") or base or list(REGIONS)[0]
        for label, url in REGIONS.items():
            if base and url == base:
                region_text = label
        self.region.set(region_text)

        token = env.get("mist_api_token", "")
        if not token and keyring is not None:
            try:
                token = keyring.get_password(KEYRING_SERVICE, "api_token") or ""
                self.remember.set(bool(token))
            except Exception:
                token = ""
        self.token.insert(0, token)
        self.org.set(env.get("mist_org_id") or s.get("org_id", ""))
        self.site.set(env.get("mist_site_id") or s.get("site_id", ""))
        self.csv_path.insert(0, s.get("csv_path", ""))
        self.out_dir.insert(0, s.get("out_dir", str(Path.home() / "MistBSSID")))
        self.mode.set(s.get("mode", "csv"))

    # ---- helpers ---------------------------------------------------------- #
    def _log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", "%s  %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _id_from(self, combo, mapping):
        text = combo.get().strip()
        if text in mapping:
            return mapping[text]
        match = UUID_RE.search(text)
        return match.group(0) if match else text

    def _client(self, log=None):
        token = self.token.get().strip()
        if not token:
            raise MistError("Please enter your Mist API token.")
        return MistClient(resolve_base_url(self.region.get()), token,
                          log or (lambda *a: None), self.cancel)

    def _browse_csv(self):
        path = filedialog.askopenfilename(title="Select Mist inventory export",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_path.delete(0, "end")
            self.csv_path.insert(0, path)

    def _browse_out(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.out_dir.delete(0, "end")
            self.out_dir.insert(0, path)

    # ---- org / site loading ---------------------------------------------- #
    def _load_orgs(self):
        try:
            client = self._client()
        except MistError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.load_btn.config(state="disabled")
        self.status.config(text="Loading organizations...")

        def work():
            try:
                self.q.put(("orgs", fetch_orgs(client)))
            except (MistError, Cancelled) as exc:
                self.q.put(("error", str(exc) or "Cancelled"))

        threading.Thread(target=work, daemon=True).start()

    def _load_sites(self):
        org_id = self._id_from(self.org, self.org_map)
        if not org_id:
            return
        try:
            client = self._client()
        except MistError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.status.config(text="Loading sites...")

        def work():
            try:
                self.q.put(("sites", fetch_sites(client, org_id)))
            except (MistError, Cancelled) as exc:
                self.q.put(("error", str(exc) or "Cancelled"))

        threading.Thread(target=work, daemon=True).start()

    # ---- run ------------------------------------------------------------- #
    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        token = self.token.get().strip()
        site_id = self._id_from(self.site, self.site_map)
        mode = self.mode.get()
        csv_path = self.csv_path.get().strip()
        if not token:
            messagebox.showerror(APP_NAME, "Please enter your Mist API token.")
            return
        if not site_id:
            messagebox.showerror(APP_NAME, "Please choose or enter a Site ID.")
            return
        if mode == "csv" and not os.path.isfile(csv_path):
            messagebox.showerror(APP_NAME, "Please choose the inventory CSV file.")
            return

        cfg = {
            "base_url": resolve_base_url(self.region.get()),
            "token": token,
            "site_id": site_id,
            "mode": mode,
            "csv_path": csv_path,
            "autosave_dir": self.out_dir.get().strip() if self.autosave.get() else "",
        }
        self._save_prefs(site_id)
        self._clear()
        self.cancel.clear()
        self.run_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.status.config(text="Running...")

        def emit(kind, *payload):
            self.q.put((kind,) + payload)

        def work():
            try:
                self.q.put(("done", run_job(cfg, emit, self.cancel)))
            except Cancelled:
                self.q.put(("cancelled",))
            except MistError as exc:
                self.q.put(("error", str(exc)))
            except Exception as exc:  # unexpected - show it rather than die silently
                self.q.put(("error", "%s: %s" % (type(exc).__name__, exc)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _cancel(self):
        self.cancel.set()
        self.status.config(text="Cancelling...")

    def _finish_run(self):
        self.run_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

    # ---- queue polling ---------------------------------------------------- #
    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind, payload = item[0], item[1:]
                if kind == "log":
                    self._log(payload[0])
                elif kind == "progress":
                    done, total = payload
                    self.progress.config(maximum=max(total, 1), value=done)
                    self.status.config(text="Processed %d of %d" % (done, total))
                elif kind == "row":
                    self.rows.append(payload[0])
                    if self._matches(payload[0]):
                        self.tree.insert("", "end", values=payload[0])
                elif kind == "done":
                    summary = payload[0]
                    self._finish_run()
                    msg = "Done: %d APs, %d skipped (disconnected), %d errors" % (
                        summary["rows"], summary["skipped"], summary["errors"])
                    self.status.config(text=msg)
                    self._log(msg)
                elif kind == "cancelled":
                    self._finish_run()
                    self.status.config(text="Cancelled (%d rows kept)" % len(self.rows))
                    self._log("Cancelled by user")
                elif kind == "error":
                    self._finish_run()
                    self.load_btn.config(state="normal")
                    self.status.config(text="Error")
                    self._log("ERROR: " + payload[0])
                    messagebox.showerror(APP_NAME, payload[0])
                elif kind == "orgs":
                    self.load_btn.config(state="normal")
                    orgs = payload[0]
                    self.org_map = {"%s (%s)" % (name, oid): oid for oid, name in orgs.items()}
                    self.org["values"] = list(self.org_map)
                    if len(self.org_map) >= 1 and not self.org.get().strip():
                        self.org.set(next(iter(self.org_map)))
                    self.status.config(text="Loaded %d organization(s)" % len(orgs))
                    if self.org.get().strip():
                        self._load_sites()
                elif kind == "sites":
                    sites = payload[0]
                    self.site_map = {"%s (%s)" % (name, sid): sid for sid, name in sites.items()}
                    self.site["values"] = sorted(self.site_map, key=str.lower)
                    self.status.config(text="Loaded %d site(s) - pick one" % len(sites))
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ---- table ----------------------------------------------------------- #
    def _matches(self, row):
        needle = self.filter_var.get().strip().lower()
        return not needle or any(needle in str(c).lower() for c in row)

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            if self._matches(row):
                self.tree.insert("", "end", values=row)

    def _sort(self, col):
        idx = COLUMNS.index(col)
        reverse = self.sort_state.get(col, False)
        self.rows.sort(key=lambda r: str(r[idx]).lower(), reverse=reverse)
        self.sort_state[col] = not reverse
        self._refresh_table()

    def _clear(self):
        self.rows = []
        self.tree.delete(*self.tree.get_children())
        self.progress.config(value=0)

    def _export(self):
        if not self.rows:
            messagebox.showinfo(APP_NAME, "Nothing to export yet.")
            return
        initial = "ap_list-%s.csv" % datetime.now().strftime("%Y%m%d-%H%M%S")
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=initial,
                                            filetypes=[("CSV files", "*.csv")])
        if path:
            write_csv(path, self.rows)
            self._log("Exported %d rows to %s" % (len(self.rows), path))

    def _copy(self):
        selected = self.tree.selection()
        if selected:
            data = [self.tree.item(i, "values") for i in selected]
        else:
            data = [r for r in self.rows if self._matches(r)]
        text = "\n".join("\t".join(str(c) for c in row) for row in data)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.config(text="Copied %d row(s) to clipboard" % len(data))

    # ---- persistence ------------------------------------------------------ #
    def _save_prefs(self, site_id):
        org_id = self._id_from(self.org, self.org_map)
        save_settings({
            "region": self.region.get().strip(),
            "org_id": org_id,
            "site_id": site_id,
            "csv_path": self.csv_path.get().strip(),
            "out_dir": self.out_dir.get().strip(),
            "mode": self.mode.get(),
        })
        if keyring is not None:
            try:
                if self.remember.get() and self.token.get().strip():
                    keyring.set_password(KEYRING_SERVICE, "api_token", self.token.get().strip())
                elif not self.remember.get():
                    keyring.delete_password(KEYRING_SERVICE, "api_token")
            except Exception:
                pass

    def _on_close(self):
        self.cancel.set()
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
