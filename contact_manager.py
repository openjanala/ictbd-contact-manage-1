"""
Contact Manager
================
A single-file desktop Contact Management application for Windows.

- Pure Python + Tkinter (no external GUI libraries required, ships with Python)
- No SQL database — contacts are stored locally in a JSON file (contacts_data.json)
  created automatically next to this script the first time you run it.
- Add / Edit / Delete / Search / Sort contacts
- Fields: First Name, Last Name, Phone, Email, Address, Company, Notes, Favorite
- Data is saved automatically after every change (no "Save" button to forget)

Run with:
    python contact_manager.py

Requirements:
    Python 3.8+ (Tkinter is included with standard Python on Windows)
"""

import json
import os
import re
import sys
import uuid
import tkinter as tk
from tkinter import ttk, messagebox
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

        self.error_label = make_label(form, "", size=9, color=COLORS["danger"],
                                       bg=COLORS["sidebar"])
        self.error_label.pack(fill="x", padx=20, pady=(0, 4), anchor="w")

        # Action buttons (fixed at bottom, not scrolled)
        actions = tk.Frame(panel, bg=COLORS["sidebar"])
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=16)

        self.save_btn = RoundedButton(actions, "💾  Save Contact", self.save_contact,
                                       bg=COLORS["accent"], hover_bg=COLORS["accent_dark"],
                                       width=160, height=38)
        self.save_btn.pack(side="left")

        self.delete_btn = RoundedButton(actions, "🗑  Delete", self.delete_contact,
                                         bg=COLORS["danger"], hover_bg=COLORS["danger_dark"],
                                         width=110, height=38)
        self.delete_btn.pack(side="left", padx=(10, 0))

        self.cancel_btn = RoundedButton(actions, "Cancel", self.new_contact,
                                         bg=COLORS["border"], hover_bg=COLORS["border"],
                                         fg=COLORS["text"], width=90, height=38)
        self.cancel_btn.pack(side="right")

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
        if self.selected_id:
            self.f_first.focus()

    # ---- form behavior ------------------------------------------------------

    def new_contact(self):
        self.selected_id = None
        self.tree.selection_remove(self.tree.selection())
        self._clear_form()

    def _clear_form(self, focus=True):
        self.form_title.configure(text="New Contact")
        self.fav_btn.configure(text="☆", fg=COLORS["muted"])
        self._current_favorite = False
        for field in (self.f_first, self.f_last, self.f_phone, self.f_email,
                      self.f_company, self.f_address):
            field.set("")
        self.f_notes.delete("1.0", "end")
        self.error_label.configure(text="")
        self.delete_btn.set_enabled(False)
        if focus:
            self.f_first.focus()

    def _load_contact_into_form(self, contact):
        self.selected_id = contact["id"]
        self.form_title.configure(text="Edit Contact")
        self._current_favorite = contact.get("favorite", False)
        self._refresh_fav_icon()
        self.f_first.set(contact.get("first_name", ""))
        self.f_last.set(contact.get("last_name", ""))
        self.f_phone.set(contact.get("phone", ""))
        self.f_email.set(contact.get("email", ""))
        self.f_company.set(contact.get("company", ""))
        self.f_address.set(contact.get("address", ""))
        self.f_notes.delete("1.0", "end")
        self.f_notes.insert("1.0", contact.get("notes", ""))
        self.error_label.configure(text="")
        self.delete_btn.set_enabled(True)

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
        self.delete_btn.set_enabled(True)
        self.form_title.configure(text="Edit Contact")
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
