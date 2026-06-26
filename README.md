# Contact Manager

A desktop Contact Management application for Windows — single Python file, no SQL database (uses a local JSON file as storage), with a clean modern UI.

## How to run it

1. Install Python 3.8+ from https://www.python.org/downloads/ if you don't have it.
   - On the installer's first screen, check **"Add python.exe to PATH"**.
   - Tkinter (the UI toolkit this app uses) is included with Python on Windows automatically — nothing extra to install.
2. Put `contact_manager.py` in any folder.
3. Double-click `contact_manager.py`, **or** open Command Prompt in that folder and run:
   ```
   python contact_manager.py
   ```

The first time it runs, it will create a file called `contacts_data.json` in the same folder — that's your "database." All your contacts live in that one file. Back it up by copying that file; restore by copying it back.

## What it can do

- **Add / Edit / Delete** contacts (First Name, Last Name, Phone, Email, Company, Address, Notes)
- **Search** instantly across name, phone, email, company, address, and notes
- **Sort** by Name, Company, Recently updated, or Favorites first
- **Favorite** contacts with a star toggle
- Required-field validation (First Name + Phone) and email format checking
- Confirmation prompt before deleting
- Autosaves after every change — no save button to forget

## Turning it into a standalone .exe (optional)

If you want to hand this to someone without Python installed, you can package it with **PyInstaller**:

```
pip install pyinstaller
pyinstaller --onefile --windowed --name "ContactManager" contact_manager.py
```

The `.exe` will appear in the `dist` folder. Note: the `.exe` will create `contacts_data.json` next to itself, same as the script does.

## Notes on the "no SQL database" requirement

There's no database engine (no SQLite, no MySQL, etc.) — contacts are stored as plain JSON in `contacts_data.json`, read into memory when the app starts and written back to disk after every add/edit/delete. This keeps the whole thing a single, dependency-free Python file while still persisting data reliably between runs.
