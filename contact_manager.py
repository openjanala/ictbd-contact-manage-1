"""
Contact Manager
================
A single-file desktop Contact Management application for Windows.

- Pure Python + Tkinter (no external GUI libraries required, ships with Python)
- No SQL database — contacts are stored locally in a JSON file (contacts_data.json)
  created automatically next to this script the first time you run it.
- Add / Edit / Delete / Search / Sort contacts
- Explicit "view" vs "edit" mode: selecting a contact shows it read-only with
  an Edit button, so you never accidentally change something while browsing.
- Export your contacts as a full JSON backup, or as a CSV file in the same
  column layout Google Contacts uses (so it also imports into Google Contacts,
  Excel, Outlook, etc).
- Import contacts back from a JSON backup or CSV file (Google Contacts,
  Outlook, Apple, or a generic Name/Phone/Email sheet). Duplicates already in
  your list (matched by phone or email) are skipped automatically.
- Fields: First Name, Last Name, Phone, Email, Address, Company, Notes, Favorite
- Data is saved automatically after every change (no "Save" button to forget)

Run with:
    python contact_manager.py

Requirements:
    Python 3.8+ (Tkinter is included with standard Python on Windows)
"""

import csv
import json
import os
import re
import sys
import uuid
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

# --------------------------------------------------------------------------
# Paths / Constants
# --------------------------------------------------------------------------

def get_data_dir():
    """Folder where the JSON 'database' file lives (next to the script/exe)."""
    if getattr(sys, "frozen", False):
        # Running as a bundled .exe (e.g. via PyInstaller)
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DATA_DIR = get_data_dir()
DATA_FILE = os.path.join(DATA_DIR, "contacts_data.json")

APP_TITLE = "Contact Manager"
APP_MIN_WIDTH = 980
APP_MIN_HEIGHT = 600

# Color palette (modern, soft, flat UI)
COLORS = {
    "bg": "#F4F5F7",
    "sidebar": "#FFFFFF",
    "accent": "#4F6EF7",
    "accent_dark": "#3C57D6",
    "accent_light": "#EAEEFF",
    "text": "#1F2430",
    "muted": "#6B7280",
    "border": "#E3E5EA",
    "danger": "#E5484D",
    "danger_dark": "#C5393E",
    "success": "#2DBE6C",
    "favorite": "#F5A623",
    "row_alt": "#FAFAFC",
    "white": "#FFFFFF",
}

FONT_FAMILY = "Segoe UI"  # default on Windows; falls back gracefully elsewhere

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------
# Data Layer  (JSON-backed "database")
# --------------------------------------------------------------------------

class ContactStore:
    """
    Handles all persistence. Acts as a tiny embedded database using a single
    JSON file. No SQL involved — contacts are kept in memory as a list of
    dicts and written to disk after every change.
    """

    def __init__(self, path):
        self.path = path
        self.contacts = []
        self.load()

    # ---- persistence -----------------------------------------------------

    def load(self):
        if not os.path.exists(self.path):
            self.contacts = []
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.contacts = raw.get("contacts", [])
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable file -> back it up, start fresh instead
            # of crashing the whole app.
            backup_path = self.path + ".bak"
            try:
                if os.path.exists(self.path):
                    os.replace(self.path, backup_path)
            except OSError:
                pass
            self.contacts = []
            self.save()

    def save(self):
        payload = {
            "contacts": self.contacts,
            "_meta": {
                "app": APP_TITLE,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "version": 1,
            },
        }
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.path)  # atomic-ish replace

    # ---- CRUD --------------------------------------------------------------

    def add(self, data):
        record = dict(data)
        record["id"] = uuid.uuid4().hex
        record["created_at"] = datetime.now().isoformat(timespec="seconds")
        record["updated_at"] = record["created_at"]
        self.contacts.append(record)
        self.save()
        return record

    def update(self, contact_id, data):
        for c in self.contacts:
            if c["id"] == contact_id:
                c.update(data)
                c["updated_at"] = datetime.now().isoformat(timespec="seconds")
                self.save()
                return c
        return None

    def delete(self, contact_id):
        before = len(self.contacts)
        self.contacts = [c for c in self.contacts if c["id"] != contact_id]
        if len(self.contacts) != before:
            self.save()
            return True
        return False

    def get(self, contact_id):
        for c in self.contacts:
            if c["id"] == contact_id:
                return c
        return None

    def toggle_favorite(self, contact_id):
        c = self.get(contact_id)
        if c:
            c["favorite"] = not c.get("favorite", False)
            self.save()
        return c

    # ---- queries ------------------------------------------------------------

    def search(self, query):
        if not query:
            return list(self.contacts)
        q = query.lower().strip()
        results = []
        for c in self.contacts:
            haystack = " ".join(
                str(c.get(field, ""))
                for field in ("first_name", "last_name", "phone", "email",
                              "company", "address", "notes")
            ).lower()
            if q in haystack:
                results.append(c)
        return results

    def sorted_contacts(self, contacts, sort_key="name"):
        if sort_key == "name":
            return sorted(
                contacts,
                key=lambda c: (c.get("last_name", "").lower(),
                               c.get("first_name", "").lower()),
            )
        if sort_key == "company":
            return sorted(contacts, key=lambda c: c.get("company", "").lower())
        if sort_key == "recent":
            return sorted(contacts, key=lambda c: c.get("updated_at", ""), reverse=True)
        if sort_key == "favorite":
            return sorted(
                contacts,
                key=lambda c: (not c.get("favorite", False),
                               c.get("last_name", "").lower(),
                               c.get("first_name", "").lower()),
            )
        return contacts

    # ---- export ---------------------------------------------------------

    def export_json(self, path):
        """Full-fidelity backup (every field, including favorite/id/timestamps)."""
        payload = {
            "contacts": self.contacts,
            "_meta": {
                "app": APP_TITLE,
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "version": 1,
                "count": len(self.contacts),
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return len(self.contacts)

    def export_csv(self, path):
        """
        Google-Contacts-style CSV export. Uses the same column names Google
        Contacts uses for its own export/import, so this file can also be
        opened in Google Contacts, Excel, Outlook, etc.
        """
        fieldnames = [
            "First Name", "Last Name", "Phone 1 - Value", "E-mail 1 - Value",
            "Organization Name", "Address 1 - Formatted", "Notes", "Favorite",
        ]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for c in self.contacts:
                writer.writerow({
                    "First Name": c.get("first_name", ""),
                    "Last Name": c.get("last_name", ""),
                    "Phone 1 - Value": c.get("phone", ""),
                    "E-mail 1 - Value": c.get("email", ""),
                    "Organization Name": c.get("company", ""),
                    "Address 1 - Formatted": c.get("address", ""),
                    "Notes": c.get("notes", ""),
                    "Favorite": "Yes" if c.get("favorite") else "",
                })
        return len(self.contacts)

    # ---- import -----------------------------------------------------------

    def _existing_signatures(self):
        """A set of (phone, email) signatures used to detect duplicates."""
        sigs = set()
        for c in self.contacts:
            phone = (c.get("phone") or "").strip().lower()
            email = (c.get("email") or "").strip().lower()
            if phone or email:
                sigs.add((phone, email))
        return sigs

    def import_json(self, path, skip_duplicates=True):
        """
        Import contacts from a JSON backup produced by this app (export_json
        or the regular contacts_data.json). Returns (added, skipped, errors).
        """
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        records = raw.get("contacts", raw if isinstance(raw, list) else [])
        return self._import_records(records, skip_duplicates)

    def import_csv(self, path, skip_duplicates=True):
        """
        Import contacts from a CSV file. Understands Google Contacts' export
        column names (e.g. "Given Name"/"First Name", "Phone 1 - Value")
        and falls back to looser matching for other common CSV exports
        (Outlook, Apple, plain "Name,Phone,Email" sheets, etc.).
        Returns (added, skipped, errors).
        """
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            headers = reader.fieldnames or []

        records = [self._map_csv_row(row, headers) for row in rows]
        return self._import_records(records, skip_duplicates)

    @staticmethod
    def _first_present(row, *keys):
        for k in keys:
            if k in row and row[k]:
                return row[k].strip()
        return ""

    def _map_csv_row(self, row, headers):
        """Map one CSV row (from Google/Outlook/Apple/generic export) to our
        internal field names."""
        first = self._first_present(row, "First Name", "Given Name", "first_name", "First")
        last = self._first_present(row, "Last Name", "Family Name", "last_name", "Last")

        if not first and not last:
            # Fall back to a single "Name"/"Full Name" column, split it.
            full = self._first_present(row, "Name", "Full Name", "name")
            if full:
                parts = full.split(" ", 1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ""

        phone = self._first_present(
            row, "Phone 1 - Value", "Phone Number", "Phone", "phone",
            "Mobile Phone", "Primary Phone",
        )
        email = self._first_present(
            row, "E-mail 1 - Value", "E-mail Address", "Email", "email", "Primary Email",
        )
        company = self._first_present(
            row, "Organization Name", "Company", "company", "Organization",
        )
        address = self._first_present(
            row, "Address 1 - Formatted", "Address", "address", "Home Address",
        )
        notes = self._first_present(row, "Notes", "notes", "Note")
        favorite_raw = self._first_present(row, "Favorite", "favorite").lower()
        favorite = favorite_raw in ("yes", "true", "1", "y")

        return {
            "first_name": first,
            "last_name": last,
            "phone": phone,
            "email": email,
            "company": company,
            "address": address,
            "notes": notes,
            "favorite": favorite,
        }

    def _import_records(self, records, skip_duplicates):
        existing_sigs = self._existing_signatures()
        added, skipped, errors = 0, 0, 0

        for raw in records:
            try:
                first = str(raw.get("first_name", "")).strip()
                last = str(raw.get("last_name", "")).strip()
                phone = str(raw.get("phone", "")).strip()
                email = str(raw.get("email", "")).strip()

                if not first and not last and not phone and not email:
                    continue  # blank row, silently ignore

                if not first:
                    # First name is required by this app's validation rules;
                    # fall back to last name or a generic label rather than
                    # silently dropping a real contact.
                    first = last or "Unnamed"
                    last = "" if first == last else last

                sig = (phone.lower(), email.lower())
                if skip_duplicates and (phone or email) and sig in existing_sigs:
                    skipped += 1
                    continue

                data = {
                    "first_name": first,
                    "last_name": last,
                    "phone": phone,
                    "email": email,
                    "company": str(raw.get("company", "")).strip(),
                    "address": str(raw.get("address", "")).strip(),
                    "notes": str(raw.get("notes", "")).strip(),
                    "favorite": bool(raw.get("favorite", False)),
                }
                self.add(data)
                existing_sigs.add(sig)
                added += 1
            except Exception:
                errors += 1

        return added, skipped, errors


# --------------------------------------------------------------------------
# Small reusable UI helpers
# --------------------------------------------------------------------------

class RoundedButton(tk.Canvas):
    """A simple flat 'button' built on a Canvas so we get full color control
    (ttk buttons on Windows ignore background color)."""

    def __init__(self, parent, text, command, bg=COLORS["accent"],
                 hover_bg=None, fg=COLORS["white"], width=140, height=36,
                 font_size=10, font_weight="bold"):
        super().__init__(parent, width=width, height=height,
                          highlightthickness=0, bg=parent["bg"], cursor="hand2")
        self.command = command
        self.bg_color = bg
        self.hover_bg = hover_bg or bg
        self.fg = fg
        self.width = width
        self.height = height
        self.font = (FONT_FAMILY, font_size, font_weight)
        self.text = text
        self._draw(self.bg_color)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._draw(self.hover_bg))
        self.bind("<Leave>", lambda e: self._draw(self.bg_color))

    def _draw(self, color):
        self.delete("all")
        r = 8
        w, h = self.width, self.height
        self.create_round_rect(1, 1, w - 1, h - 1, r, fill=color, outline=color)
        self.create_text(w / 2, h / 2, text=self.text, fill=self.fg, font=self.font)

    def create_round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _on_click(self, event):
        if self.command:
            self.command()

    def set_enabled(self, enabled):
        if enabled:
            self.configure(cursor="hand2")
            self.bind("<Button-1>", self._on_click)
            self._draw(self.bg_color)
        else:
            self.configure(cursor="arrow")
            self.unbind("<Button-1>")
            self._draw(COLORS["border"])


def make_label(parent, text, size=10, weight="normal", color=COLORS["text"], bg=None, **kw):
    return tk.Label(
        parent, text=text, font=(FONT_FAMILY, size, weight),
        fg=color, bg=bg or parent["bg"], **kw
    )


class LabeledEntry(tk.Frame):
    """A label stacked above a styled Entry, with an optional validation hint."""

    def __init__(self, parent, label_text, required=False, **kw):
        super().__init__(parent, bg=parent["bg"])
        top = tk.Frame(self, bg=parent["bg"])
        top.pack(fill="x", anchor="w")
        lbl_text = label_text + (" *" if required else "")
        make_label(top, lbl_text, size=9, weight="bold",
                   color=COLORS["muted"]).pack(side="left")

        self.entry_frame = tk.Frame(self, bg=COLORS["white"],
                                     highlightbackground=COLORS["border"],
                                     highlightcolor=COLORS["accent"],
                                     highlightthickness=1, bd=0)
        self.entry_frame.pack(fill="x", pady=(4, 10))

        self.var = tk.StringVar()
        self.entry = tk.Entry(
            self.entry_frame, textvariable=self.var, relief="flat",
            font=(FONT_FAMILY, 10), bg=COLORS["white"], fg=COLORS["text"],
            insertbackground=COLORS["text"], bd=0, **kw
        )
        self.entry.pack(fill="x", padx=10, pady=8)

    def get(self):
        return self.var.get().strip()

    def set(self, value):
        self.var.set(value or "")

    def focus(self):
        self.entry.focus_set()

    def set_readonly(self, readonly):
        if readonly:
            self.entry.configure(state="disabled", disabledforeground=COLORS["text"],
                                  disabledbackground=COLORS["row_alt"])
            self.entry_frame.configure(bg=COLORS["row_alt"],
                                        highlightbackground=COLORS["row_alt"])
        else:
            self.entry.configure(state="normal")
            self.entry_frame.configure(bg=COLORS["white"],
                                        highlightbackground=COLORS["border"])

    def flash_error(self):
        self.entry_frame.configure(highlightbackground=COLORS["danger"],
                                    highlightthickness=2)
        self.after(1400, lambda: self.entry_frame.configure(
            highlightbackground=COLORS["border"], highlightthickness=1))


# --------------------------------------------------------------------------
# Main Application
# --------------------------------------------------------------------------

class ContactManagerApp:
    def __init__(self, root):
        self.root = root
        self.store = ContactStore(DATA_FILE)

        self.selected_id = None
        self.sort_key = "name"
        self.search_var = tk.StringVar()

        self._setup_window()
        self._build_layout()

        # Only start reacting to search-box changes once every widget
        # (especially self.tree) actually exists.
        self.search_var.trace_add("write", lambda *_: self.refresh_list())

        self.refresh_list()
        self._clear_form(focus=False)
        self._set_mode("edit")

    # ---- window / style ---------------------------------------------------

    def _setup_window(self):
        self.root.title(APP_TITLE)
        self.root.geometry(f"{APP_MIN_WIDTH}x{APP_MIN_HEIGHT}")
        self.root.minsize(APP_MIN_WIDTH, APP_MIN_HEIGHT)
        self.root.configure(bg=COLORS["bg"])

        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Treeview",
                         background=COLORS["white"],
                         fieldbackground=COLORS["white"],
                         foreground=COLORS["text"],
                         rowheight=34,
                         borderwidth=0,
                         font=(FONT_FAMILY, 10))
        style.configure("Treeview.Heading",
                         background=COLORS["bg"],
                         foreground=COLORS["muted"],
                         font=(FONT_FAMILY, 9, "bold"),
                         relief="flat",
                         borderwidth=0)
        style.map("Treeview",
                   background=[("selected", COLORS["accent_light"])],
                   foreground=[("selected", COLORS["text"])])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

        # Allow closing gracefully (data already autosaved on every change)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def _build_layout(self):
        # Three columns: list panel (left), detail/form panel (right)
        container = tk.Frame(self.root, bg=COLORS["bg"])
        container.pack(fill="both", expand=True)

        self._build_topbar(container)

        body = tk.Frame(container, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=4)
        body.rowconfigure(0, weight=1)

        self._build_list_panel(body)
        self._build_form_panel(body)

    # ---- top bar (title + search + sort) -----------------------------------

    def _build_topbar(self, parent):
        bar = tk.Frame(parent, bg=COLORS["bg"])
        bar.pack(fill="x", padx=16, pady=16)

        left = tk.Frame(bar, bg=COLORS["bg"])
        left.pack(side="left")
        make_label(left, "📇  Contact Manager", size=16, weight="bold").pack(anchor="w")
        self.count_label = make_label(left, "", size=9, color=COLORS["muted"])
        self.count_label.pack(anchor="w")

        right = tk.Frame(bar, bg=COLORS["bg"])
        right.pack(side="right")

        # Backup menu (Export / Import) — styled to match the rest of the UI
        backup_frame = tk.Frame(right, bg=COLORS["bg"])
        backup_frame.pack(side="right", padx=(10, 0))
        make_label(backup_frame, "Backup", size=9, color=COLORS["muted"]).pack(anchor="w")

        self.backup_menu_btn = tk.Menubutton(
            backup_frame, text="⬇⬆  Export / Import", relief="flat",
            font=(FONT_FAMILY, 9, "bold"), bg=COLORS["white"], fg=COLORS["text"],
            activebackground=COLORS["accent_light"], activeforeground=COLORS["text"],
            bd=1, padx=10, pady=6, cursor="hand2",
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        backup_menu = tk.Menu(self.backup_menu_btn, tearoff=0,
                               font=(FONT_FAMILY, 9), bg=COLORS["white"],
                               fg=COLORS["text"], activebackground=COLORS["accent_light"])
        backup_menu.add_command(label="📤  Export as JSON backup (full)",
                                 command=self.export_json_dialog)
        backup_menu.add_command(label="📄  Export as CSV (Google Contacts format)",
                                 command=self.export_csv_dialog)
        backup_menu.add_separator()
        backup_menu.add_command(label="📥  Import from file...",
                                 command=self.import_dialog)
        self.backup_menu_btn.configure(menu=backup_menu)
        self.backup_menu_btn.pack()

        # Sort dropdown
        sort_frame = tk.Frame(right, bg=COLORS["bg"])
        sort_frame.pack(side="right", padx=(10, 0))
        make_label(sort_frame, "Sort by", size=9, color=COLORS["muted"]).pack(anchor="w")
        self.sort_combo = ttk.Combobox(
            sort_frame, state="readonly", width=14,
            values=["Name", "Company", "Recently updated", "Favorites first"],
            font=(FONT_FAMILY, 9)
        )
        self.sort_combo.current(0)
        self.sort_combo.pack()
        self.sort_combo.bind("<<ComboboxSelected>>", self._on_sort_change)

        # Search box
        search_frame = tk.Frame(right, bg=COLORS["white"], highlightthickness=1,
                                 highlightbackground=COLORS["border"])
        search_frame.pack(side="right", padx=(0, 16))
        make_label(search_frame, "🔍", bg=COLORS["white"]).pack(side="left", padx=(8, 0))
        search_entry = tk.Entry(search_frame, textvariable=self.search_var,
                                 relief="flat", font=(FONT_FAMILY, 10), width=26,
                                 bg=COLORS["white"], bd=0)
        search_entry.pack(side="left", padx=8, pady=7)
        search_entry.insert(0, "")
        self._set_placeholder(search_entry, "Search name, phone, email, company...")

    def _set_placeholder(self, entry, text):
        """Lightweight placeholder behaviour for a Tk Entry."""
        entry.placeholder = text
        entry.placeholder_color = COLORS["muted"]
        entry.default_fg = COLORS["text"]

        def on_focus_in(_):
            if entry.get() == entry.placeholder:
                entry.delete(0, "end")
                entry.config(fg=entry.default_fg)

        def on_focus_out(_):
            if not entry.get():
                entry.insert(0, entry.placeholder)
                entry.config(fg=entry.placeholder_color)

        entry.insert(0, text)
        entry.config(fg=entry.placeholder_color)
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    # ---- list panel (left) -------------------------------------------------

    def _build_list_panel(self, parent):
        panel = tk.Frame(parent, bg=COLORS["sidebar"], highlightthickness=1,
                          highlightbackground=COLORS["border"])
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        header = tk.Frame(panel, bg=COLORS["sidebar"])
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        make_label(header, "All Contacts", size=11, weight="bold",
                   bg=COLORS["sidebar"]).pack(side="left")

        new_btn = RoundedButton(header, "+ New Contact", self.new_contact,
                                 width=130, height=30, font_size=9)
        new_btn.pack(side="right")

        tree_frame = tk.Frame(panel, bg=COLORS["sidebar"])
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        columns = ("name", "phone", "company")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                  selectmode="browse")
        self.tree.heading("name", text="NAME")
        self.tree.heading("phone", text="PHONE")
        self.tree.heading("company", text="COMPANY")
        self.tree.column("name", width=170, anchor="w")
        self.tree.column("phone", width=120, anchor="w")
        self.tree.column("company", width=130, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.tag_configure("favorite", foreground=COLORS["favorite"])
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)
        self.tree.bind("<Double-1>", lambda e: self.edit_contact_focus())

    # ---- form panel (right) ------------------------------------------------

    def _build_form_panel(self, parent):
        panel = tk.Frame(parent, bg=COLORS["sidebar"], highlightthickness=1,
                          highlightbackground=COLORS["border"])
        panel.grid(row=0, column=1, sticky="nsew")
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        header = tk.Frame(panel, bg=COLORS["sidebar"])
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 6))
        self.form_title = make_label(header, "New Contact", size=12, weight="bold",
                                      bg=COLORS["sidebar"])
        self.form_title.pack(side="left")

        self.fav_btn = tk.Label(header, text="☆", font=(FONT_FAMILY, 16),
                                 bg=COLORS["sidebar"], fg=COLORS["muted"], cursor="hand2")
        self.fav_btn.pack(side="right")
        self.fav_btn.bind("<Button-1>", lambda e: self._toggle_favorite_in_form())

        scroll_canvas = tk.Canvas(panel, bg=COLORS["sidebar"], highlightthickness=0)
        scroll_canvas.grid(row=1, column=0, sticky="nsew", padx=(20, 0))
        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=scroll_canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        scroll_canvas.configure(yscrollcommand=scrollbar.set)

        form = tk.Frame(scroll_canvas, bg=COLORS["sidebar"])
        form_id = scroll_canvas.create_window((0, 0), window=form, anchor="nw")

        def on_configure(event):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def on_canvas_resize(event):
            scroll_canvas.itemconfig(form_id, width=event.width)

        form.bind("<Configure>", on_configure)
        scroll_canvas.bind("<Configure>", on_canvas_resize)

        # Mouse wheel scrolling
        def on_mousewheel(event):
            scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        scroll_canvas.bind_all("<MouseWheel>", on_mousewheel)

        pad = {"padx": 20}
        row1 = tk.Frame(form, bg=COLORS["sidebar"])
        row1.pack(fill="x", **pad, pady=(10, 0))
        row1.columnconfigure(0, weight=1)
        row1.columnconfigure(1, weight=1)
        self.f_first = LabeledEntry(row1, "First Name", required=True)
        self.f_first.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.f_last = LabeledEntry(row1, "Last Name")
        self.f_last.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        row2 = tk.Frame(form, bg=COLORS["sidebar"])
        row2.pack(fill="x", **pad)
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)
        self.f_phone = LabeledEntry(row2, "Phone", required=True)
        self.f_phone.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.f_email = LabeledEntry(row2, "Email")
        self.f_email.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.f_company = LabeledEntry(form, "Company")
        self.f_company.pack(fill="x", **pad)

        self.f_address = LabeledEntry(form, "Address")
        self.f_address.pack(fill="x", **pad)

        # Notes (multi-line)
        notes_wrap = tk.Frame(form, bg=COLORS["sidebar"])
        notes_wrap.pack(fill="x", **pad)
        make_label(notes_wrap, "NOTES", size=9, weight="bold",
                   color=COLORS["muted"]).pack(anchor="w")
        notes_box = tk.Frame(notes_wrap, bg=COLORS["white"],
                              highlightbackground=COLORS["border"],
                              highlightcolor=COLORS["accent"], highlightthickness=1)
        notes_box.pack(fill="x", pady=(4, 10))
        self.f_notes = tk.Text(notes_box, height=4, relief="flat", wrap="word",
                                font=(FONT_FAMILY, 10), bg=COLORS["white"],
                                fg=COLORS["text"], bd=0, padx=10, pady=8)
        self.f_notes.pack(fill="x")
        self.notes_box = notes_box

        self.error_label = make_label(form, "", size=9, color=COLORS["danger"],
                                       bg=COLORS["sidebar"])
        self.error_label.pack(fill="x", padx=20, pady=(0, 4), anchor="w")

        # Action buttons (fixed at bottom, not scrolled)
        # Different buttons are shown depending on mode:
        #   - View mode (a saved contact is selected): Edit + Delete
        #   - Edit mode (new contact, or editing an existing one): Save + Cancel
        actions = tk.Frame(panel, bg=COLORS["sidebar"])
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=16)
        self.actions_frame = actions

        self.save_btn = RoundedButton(actions, "💾  Save Contact", self.save_contact,
                                       bg=COLORS["accent"], hover_bg=COLORS["accent_dark"],
                                       width=160, height=38)

        self.edit_btn = RoundedButton(actions, "✏️  Edit", self.enter_edit_mode,
                                       bg=COLORS["accent"], hover_bg=COLORS["accent_dark"],
                                       width=110, height=38)

        self.delete_btn = RoundedButton(actions, "🗑  Delete", self.delete_contact,
                                         bg=COLORS["danger"], hover_bg=COLORS["danger_dark"],
                                         width=110, height=38)

        self.cancel_btn = RoundedButton(actions, "Cancel", self.cancel_edit,
                                         bg=COLORS["border"], hover_bg=COLORS["border"],
                                         fg=COLORS["text"], width=90, height=38)

    # ---- list / search / sort behavior -------------------------------------

    def _on_sort_change(self, event=None):
        mapping = {
            "Name": "name",
            "Company": "company",
            "Recently updated": "recent",
            "Favorites first": "favorite",
        }
        self.sort_key = mapping.get(self.sort_combo.get(), "name")
        self.refresh_list()

    def refresh_list(self):
        query = self.search_var.get()
        if query == "Search name, phone, email, company...":
            query = ""
        results = self.store.search(query)
        results = self.store.sorted_contacts(results, self.sort_key)

        self.tree.delete(*self.tree.get_children())
        for c in results:
            name = f"{c.get('first_name','')} {c.get('last_name','')}".strip()
            star = "★ " if c.get("favorite") else ""
            tag = ("favorite",) if c.get("favorite") else ()
            self.tree.insert("", "end", iid=c["id"],
                              values=(star + name, c.get("phone", ""), c.get("company", "")),
                              tags=tag)

        total = len(self.store.contacts)
        shown = len(results)
        if query:
            self.count_label.configure(text=f"{shown} of {total} contacts")
        else:
            self.count_label.configure(text=f"{total} contact{'s' if total != 1 else ''}")

        # Re-select previously selected row if it's still visible
        if self.selected_id and self.tree.exists(self.selected_id):
            self.tree.selection_set(self.selected_id)

    def _on_row_select(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        contact_id = selection[0]
        contact = self.store.get(contact_id)
        if contact:
            self._load_contact_into_form(contact)

    def edit_contact_focus(self):
        """Double-click on a row jumps straight into edit mode."""
        if self.selected_id:
            self.enter_edit_mode()

    # ---- export / import ---------------------------------------------------

    def export_json_dialog(self):
        if not self.store.contacts:
            messagebox.showinfo("Nothing to export", "You don't have any contacts yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Export contacts as JSON backup",
            defaultextension=".json",
            filetypes=[("JSON backup", "*.json")],
            initialfile=f"contacts_backup_{datetime.now().strftime('%Y-%m-%d')}.json",
        )
        if not path:
            return
        try:
            count = self.store.export_json(path)
            messagebox.showinfo("Export complete",
                                 f"Exported {count} contact{'s' if count != 1 else ''} to:\n{path}")
        except OSError as e:
            messagebox.showerror("Export failed", f"Could not write the file:\n{e}")

    def export_csv_dialog(self):
        if not self.store.contacts:
            messagebox.showinfo("Nothing to export", "You don't have any contacts yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Export contacts as CSV (Google Contacts format)",
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")],
            initialfile=f"contacts_backup_{datetime.now().strftime('%Y-%m-%d')}.csv",
        )
        if not path:
            return
        try:
            count = self.store.export_csv(path)
            messagebox.showinfo("Export complete",
                                 f"Exported {count} contact{'s' if count != 1 else ''} to:\n{path}\n\n"
                                 "This CSV uses the same column layout as Google Contacts, "
                                 "so it can also be imported there.")
        except OSError as e:
            messagebox.showerror("Export failed", f"Could not write the file:\n{e}")

    def import_dialog(self):
        path = filedialog.askopenfilename(
            title="Import contacts",
            filetypes=[
                ("Contacts backup", "*.json *.csv"),
                ("JSON backup", "*.json"),
                ("CSV (Google Contacts, Outlook, Apple...)", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        confirm = messagebox.askyesno(
            "Import contacts",
            "Importing will add new contacts from this file.\n"
            "Contacts that already exist (matched by phone or email) will be skipped "
            "automatically so you won't get duplicates.\n\nContinue?",
        )
        if not confirm:
            return

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".json":
                added, skipped, errors = self.store.import_json(path)
            elif ext == ".csv":
                added, skipped, errors = self.store.import_csv(path)
            else:
                # Unknown extension — sniff the content instead of guessing.
                with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    head = f.read(200).lstrip()
                if head.startswith("{") or head.startswith("["):
                    added, skipped, errors = self.store.import_json(path)
                else:
                    added, skipped, errors = self.store.import_csv(path)
        except (json.JSONDecodeError, OSError, csv.Error) as e:
            messagebox.showerror("Import failed",
                                  f"Couldn't read that file as a contacts backup:\n{e}")
            return

        self.refresh_list()

        summary = f"Added {added} new contact{'s' if added != 1 else ''}."
        if skipped:
            summary += f"\nSkipped {skipped} duplicate{'s' if skipped != 1 else ''} already in your list."
        if errors:
            summary += f"\n{errors} row{'s' if errors != 1 else ''} could not be read and were skipped."
        messagebox.showinfo("Import complete", summary)

    # ---- form behavior ------------------------------------------------------

    def new_contact(self):
        self.selected_id = None
        self.tree.selection_remove(self.tree.selection())
        self._clear_form()
        self._set_mode("edit")

    def _set_mode(self, mode):
        """
        mode is "view" (a saved contact selected, fields read-only, Edit
        button shown) or "edit" (new contact, or actively editing one;
        fields editable, Save/Cancel shown).
        """
        self.mode = mode
        is_view = (mode == "view")

        for field in (self.f_first, self.f_last, self.f_phone, self.f_email,
                      self.f_company, self.f_address):
            field.set_readonly(is_view)
        self.f_notes.configure(state="normal")  # must be normal to change bg in some Tk builds
        self.f_notes.configure(bg=COLORS["row_alt"] if is_view else COLORS["white"])
        self.f_notes.configure(state="disabled" if is_view else "normal")
        self.notes_box.configure(
            bg=COLORS["row_alt"] if is_view else COLORS["white"],
            highlightbackground=COLORS["row_alt"] if is_view else COLORS["border"],
        )

        # Favorite star is always clickable, even in view mode, since toggling
        # it doesn't require the "edit" flow (mirrors most contacts apps).

        # Swap button sets
        for w in (self.save_btn, self.edit_btn, self.delete_btn, self.cancel_btn):
            w.pack_forget()

        if is_view:
            self.edit_btn.pack(side="left")
            self.delete_btn.pack(side="left", padx=(10, 0))
        else:
            self.save_btn.pack(side="left")
            self.cancel_btn.pack(side="right")
            if self.selected_id:
                # Editing an existing contact: also allow deleting from here.
                self.delete_btn.pack(side="left", padx=(10, 0))

    def enter_edit_mode(self):
        self._set_mode("edit")
        self.f_first.focus()

    def cancel_edit(self):
        """Cancel out of edit mode: back to view if editing an existing
        contact, or back to a blank new-contact form otherwise."""
        if self.selected_id:
            contact = self.store.get(self.selected_id)
            if contact:
                self._load_contact_into_form(contact)
                return
        self.new_contact()

    def _clear_form(self, focus=True):
        self.form_title.configure(text="New Contact")
        self.fav_btn.configure(text="☆", fg=COLORS["muted"])
        self._current_favorite = False
        for field in (self.f_first, self.f_last, self.f_phone, self.f_email,
                      self.f_company, self.f_address):
            field.set("")
        self.f_notes.configure(state="normal")
        self.f_notes.delete("1.0", "end")
        self.error_label.configure(text="")
        if focus:
            self.f_first.focus()

    def _load_contact_into_form(self, contact):
        self.selected_id = contact["id"]
        name = f"{contact.get('first_name','')} {contact.get('last_name','')}".strip()
        self.form_title.configure(text=name or "Edit Contact")
        self._current_favorite = contact.get("favorite", False)
        self._refresh_fav_icon()
        self.f_first.set(contact.get("first_name", ""))
        self.f_last.set(contact.get("last_name", ""))
        self.f_phone.set(contact.get("phone", ""))
        self.f_email.set(contact.get("email", ""))
        self.f_company.set(contact.get("company", ""))
        self.f_address.set(contact.get("address", ""))
        self.f_notes.configure(state="normal")
        self.f_notes.delete("1.0", "end")
        self.f_notes.insert("1.0", contact.get("notes", ""))
        self.error_label.configure(text="")
        self._set_mode("view")

    def _refresh_fav_icon(self):
        if self._current_favorite:
            self.fav_btn.configure(text="★", fg=COLORS["favorite"])
        else:
            self.fav_btn.configure(text="☆", fg=COLORS["muted"])

    def _toggle_favorite_in_form(self):
        self._current_favorite = not getattr(self, "_current_favorite", False)
        self._refresh_fav_icon()
        # If editing an existing contact, persist immediately
        if self.selected_id:
            self.store.update(self.selected_id, {"favorite": self._current_favorite})
            self.refresh_list()

    def _validate(self):
        first = self.f_first.get()
        phone = self.f_phone.get()
        email = self.f_email.get()

        if not first:
            self.error_label.configure(text="First name is required.")
            self.f_first.flash_error()
            return False
        if not phone:
            self.error_label.configure(text="Phone number is required.")
            self.f_phone.flash_error()
            return False
        if email and not EMAIL_RE.match(email):
            self.error_label.configure(text="That email address doesn't look valid.")
            self.f_email.flash_error()
            return False
        self.error_label.configure(text="")
        return True

    def save_contact(self):
        if not self._validate():
            return

        data = {
            "first_name": self.f_first.get(),
            "last_name": self.f_last.get(),
            "phone": self.f_phone.get(),
            "email": self.f_email.get(),
            "company": self.f_company.get(),
            "address": self.f_address.get(),
            "notes": self.f_notes.get("1.0", "end").strip(),
            "favorite": getattr(self, "_current_favorite", False),
        }

        if self.selected_id:
            self.store.update(self.selected_id, data)
        else:
            record = self.store.add(data)
            self.selected_id = record["id"]

        self.refresh_list()
        if self.tree.exists(self.selected_id):
            self.tree.selection_set(self.selected_id)
            self.tree.see(self.selected_id)

        name = f"{data['first_name']} {data['last_name']}".strip()
        self.form_title.configure(text=name or "Edit Contact")
        self._set_mode("view")
        self._flash_saved()

    def _flash_saved(self):
        original = self.error_label["fg"]
        self.error_label.configure(text="✓ Saved", fg=COLORS["success"])
        self.error_label.after(1600, lambda: self.error_label.configure(text="", fg=original))

    def delete_contact(self):
        if not self.selected_id:
            return
        contact = self.store.get(self.selected_id)
        name = f"{contact.get('first_name','')} {contact.get('last_name','')}".strip() if contact else ""
        confirm = messagebox.askyesno(
            "Delete Contact",
            f"Are you sure you want to delete '{name or 'this contact'}'?\nThis cannot be undone.",
        )
        if confirm:
            self.store.delete(self.selected_id)
            self.new_contact()
            self.refresh_list()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    root = tk.Tk()
    try:
        # Slightly nicer DPI handling on Windows
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = ContactManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
