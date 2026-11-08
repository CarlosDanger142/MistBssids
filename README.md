[README.md](https://github.com/user-attachments/files/34550116/README.md)
# Mist AP BSSID Finder[README.md](https://github.com/user-attachments/files/34550161/README.md)


A small desktop GUI that pulls AP details from the [Juniper Mist](https://www.juniper.net/us/en/products/cloud-services/mist-ai.html) API and shows them in a sortable, filterable table you can export to CSV.

For each connected AP it reports:
# Mist AP BSSID Finder

A small desktop GUI that pulls AP details from the [Juniper Mist](https://www.juniper.net/us/en/products/cloud-services/mist-ai.html) API and shows them in a sortable, filterable table you can export to CSV.

For each connected AP it reports:

| Column | Source |
|---|---|
| HostName | AP name |
| Location | Map name (or `Not on Map`) |
| MAC | AP MAC address |
| 2.4 GHz / 5 GHz / 6 GHz BSSID | Radio MACs from the AP stats, formatted like the original script |
| Switch Name / Switch Port | LLDP neighbor data |

This is a GUI equivalent of [allynjcrowe/mist-get_bssid](https://github.com/allynjcrowe/mist-get_bssid) (Allyn Crowe, Nexum). It is a derivative work and is therefore licensed under **GPL-3.0**, the same as the original.

> **Screenshot:** add one here, for example `docs/screenshot.png`, and link it with `![Mist AP BSSID Finder](docs/screenshot.png)`.

## Features

- Two input modes:
  - **Inventory CSV:** the export from the Mist portal inventory page, same as the original script. One stats call per AP.
  - **All APs in a site:** no CSV needed. Pulls every AP's stats in a few paged calls.
- Load your organizations and sites from the token, or paste an Org/Site ID directly.
- All 12 Mist cloud regions are built in. You can also paste a custom API URL or a portal address (`https://manage.xx.mist.com/...`) and it converts it to the API host.
- Live progress bar, log pane and a Cancel button. Automatic backoff when the API rate-limits (HTTP 429).
- Click a column header to sort. Use the filter box to search all columns.
- Copy selected rows (or all visible rows) to the clipboard as tab-separated text.
- Auto-save each run to a timestamped CSV, or export manually.
- Read-only: the tool only makes `GET` requests.

## Requirements

- Python 3.8 or newer
- [`requests`](https://pypi.org/project/requests/)
- `tkinter` (Python's Tk bindings, see the notes for your OS below)
- Optional: [`keyring`](https://pypi.org/project/keyring/) to store the API token in your OS keychain

You also need a Mist API token. A token with read-only access to the org or site is enough.

## Install

### macOS (Homebrew Python)

Homebrew's Python does **not** include Tk, so install it separately. The version must match your Python.

```bash
# 1. Check your Python version
python3 --version            # e.g. Python 3.15.2

# 2. Install Tk for that version
brew install python-tk@3.15  # use the same major.minor as above

# 3. Get the code and create a virtual environment
git clone https://github.com/CarlosDanger142/MistBssids.git
cd MistBssids
python3 -m venv .venv
source .venv/bin/activate    # prompt should now start with (.venv)

# 4. Install dependencies
pip install requests
pip install keyring          # optional

# 5. Verify Tk works inside the venv (prints a version number)
python3 -c "import tkinter; print(tkinter.TkVersion)"
```

The Python that ships with Xcode's command line tools has an old Tk that can show a blank or broken window. Use Homebrew's Python or the installer from [python.org](https://www.python.org/downloads/), which includes Tk.

### Windows

Install Python from [python.org](https://www.python.org/downloads/). Tk is included by default. Then, in PowerShell:

```powershell
git clone https://github.com/CarlosDanger142/MistBssids.git
cd MistBssids
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install requests
pip install keyring          # optional
```

### Linux

```bash
sudo apt install python3-tk   # Debian/Ubuntu; other distros have an equivalent package
git clone https://github.com/CarlosDanger142/MistBssids.git
cd MistBssids
python3 -m venv .venv
source .venv/bin/activate
pip install requests
pip install keyring           # optional
```

## Run

Each time you open a new terminal, activate the venv first, then run the script from the project folder:

```bash
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python3 mist_bssid_gui.py     # Windows: python mist_bssid_gui.py
```

## Usage

1. **Region / API URL:** pick your Mist cloud region from the dropdown. The region must match where your org lives, or you will get a `401`.
2. **API token:** paste your token. Tick **Remember token in system keychain** to store it in your OS keychain (only shown if `keyring` is installed).
3. Click **Load orgs & sites**, then pick an organization and a site. You can also paste an Org ID or Site ID directly into the boxes.
4. Choose a source:
   - **Inventory CSV:** export the AP inventory from the Mist portal and browse to it. The file needs a `MAC Address` column. `Name` and `Status` are used if present, and APs with status `disconnected` are skipped.
   - **All APs in the selected site:** no file needed. Only connected APs are listed.
5. Optionally tick **Auto-save CSV to folder** and choose an output folder. The default is `~/MistBSSID`. Files are named `ap_list-YYYYMMDD-HHMMSS.csv`.
6. Click **Run**. Results appear in the table as they arrive.

### Using a `.env` file

To stay compatible with the original script, the form is pre-filled from a `.env` file in the folder you run the script from:

```
api_base_url=https://api.mist.com
mist_api_token=YOUR_TOKEN
mist_org_id=YOUR_ORG_ID
mist_site_id=YOUR_SITE_ID
```

The token in a `.env` file is stored in plain text. Keep the file out of version control (add `.env` to `.gitignore`) or use the keychain option instead.

## Settings and files

- Preferences (region, org ID, site ID, CSV path, output folder, mode) are saved to `~/.mist_bssid_gui.json`. The API token is never saved there.
- The API token is only stored if you tick the keychain option, and then it goes to the OS keychain, not to disk.

## API endpoints used

All requests are `GET`:

- `/api/v1/self`
- `/api/v1/orgs/{org_id}/sites`
- `/api/v1/sites/{site_id}/maps`
- `/api/v1/sites/{site_id}/stats/devices` (all APs, paged)
- `/api/v1/sites/{site_id}/stats/devices/{device_id}` (one AP, CSV mode)

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'requests'` | The package isn't installed in the Python you are running. Make sure the venv is active (your prompt should start with `(.venv)`), then run `pip install requests`. A new terminal window needs `source .venv/bin/activate` again. |
| `ModuleNotFoundError: ... '_tkinter'` or `Unsupported platform for standard library module '_tkinter'` | Your Python was installed without Tk. On macOS with Homebrew: `brew install python-tk@3.X`, matching `python3 --version`. On Debian/Ubuntu: `sudo apt install python3-tk`. If it still fails, delete `.venv` and recreate it. |
| Prompt has no `(.venv)` | The venv isn't active. Run `source .venv/bin/activate` from the folder that contains `.venv`. If the folder doesn't exist, create it with `python3 -m venv .venv`. |
| `401 Unauthorized` | Wrong token or wrong region. Check that the region matches where your org lives. |
| `403 Forbidden` | The token has no access to that org or site. |
| `404 Not found` for some APs in CSV mode | The inventory export covers the whole org, but the selected site only has some of those APs. These are logged and counted as errors, and the run continues. |
| Repeated `429` messages | Mist is rate-limiting you. The tool waits and retries automatically. |

## Credits and license

- Original script: [allynjcrowe/mist-get_bssid](https://github.com/allynjcrowe/mist-get_bssid), Allyn Crowe, Nexum (GPL-3.0).
- This GUI is a derivative work and is also released under the **GNU General Public License v3.0**. See [`LICENSE`](LICENSE) for the full text.

| Column | Source |
|---|---|
| HostName | AP name |
| Location | Map name (or `Not on Map`) |
| MAC | AP MAC address |
| 2.4 GHz / 5 GHz / 6 GHz BSSID | Radio MACs from the AP stats, formatted like the original script |
| Switch Name / Switch Port | LLDP neighbor data |

This is a GUI equivalent of [allynjcrowe/mist-get_bssid](https://github.com/allynjcrowe/mist-get_bssid) (Allyn Crowe, Nexum). It is a derivative work and is therefore licensed under **GPL-3.0**, the same as the original.

> **Screenshot:** add one here, for example `docs/screenshot.png`, and link it with `![Mist AP BSSID Finder](docs/screenshot.png)`.

## Features

- Two input modes:
  - **Inventory CSV:** the export from the Mist portal inventory page, same as the original script. One stats call per AP.
  - **All APs in a site:** no CSV needed. Pulls every AP's stats in a few paged calls.
- Load your organizations and sites from the token, or paste an Org/Site ID directly.
- All 12 Mist cloud regions are built in. You can also paste a custom API URL or a portal address (`https://manage.xx.mist.com/...`) and it converts it to the API host.
- Live progress bar, log pane and a Cancel button. Automatic backoff when the API rate-limits (HTTP 429).
- Click a column header to sort. Use the filter box to search all columns.
- Copy selected rows (or all visible rows) to the clipboard as tab-separated text.
- Auto-save each run to a timestamped CSV, or export manually.
- Read-only: the tool only makes `GET` requests.

## Requirements

- Python 3.8 or newer
- [`requests`](https://pypi.org/project/requests/)
- `tkinter` (Python's Tk bindings, see the notes for your OS below)
- Optional: [`keyring`](https://pypi.org/project/keyring/) to store the API token in your OS keychain

You also need a Mist API token. A token with read-only access to the org or site is enough.

## Install

### macOS (Homebrew Python)

Homebrew's Python does **not** include Tk, so install it separately. The version must match your Python.

```bash
# 1. Check your Python version
python3 --version            # e.g. Python 3.15.2

# 2. Install Tk for that version
brew install python-tk@3.15  # use the same major.minor as above

# 3. Get the code and create a virtual environment
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python3 -m venv .venv
source .venv/bin/activate    # prompt should now start with (.venv)

# 4. Install dependencies
pip install requests
pip install keyring          # optional

# 5. Verify Tk works inside the venv (prints a version number)
python3 -c "import tkinter; print(tkinter.TkVersion)"
```

The Python that ships with Xcode's command line tools has an old Tk that can show a blank or broken window. Use Homebrew's Python or the installer from [python.org](https://www.python.org/downloads/), which includes Tk.

### Windows

Install Python from [python.org](https://www.python.org/downloads/). Tk is included by default. Then, in PowerShell:

```powershell
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install requests
pip install keyring          # optional
```

### Linux

```bash
sudo apt install python3-tk   # Debian/Ubuntu; other distros have an equivalent package
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python3 -m venv .venv
source .venv/bin/activate
pip install requests
pip install keyring           # optional
```

## Run

Each time you open a new terminal, activate the venv first, then run the script from the project folder:

```bash
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python3 mist_bssid_gui.py     # Windows: python mist_bssid_gui.py
```

## Usage

1. **Region / API URL:** pick your Mist cloud region from the dropdown. The region must match where your org lives, or you will get a `401`.
2. **API token:** paste your token. Tick **Remember token in system keychain** to store it in your OS keychain (only shown if `keyring` is installed).
3. Click **Load orgs & sites**, then pick an organization and a site. You can also paste an Org ID or Site ID directly into the boxes.
4. Choose a source:
   - **Inventory CSV:** export the AP inventory from the Mist portal and browse to it. The file needs a `MAC Address` column. `Name` and `Status` are used if present, and APs with status `disconnected` are skipped.
   - **All APs in the selected site:** no file needed. Only connected APs are listed.
5. Optionally tick **Auto-save CSV to folder** and choose an output folder. The default is `~/MistBSSID`. Files are named `ap_list-YYYYMMDD-HHMMSS.csv`.
6. Click **Run**. Results appear in the table as they arrive.

### Using a `.env` file

To stay compatible with the original script, the form is pre-filled from a `.env` file in the folder you run the script from:

```
api_base_url=https://api.mist.com
mist_api_token=YOUR_TOKEN
mist_org_id=YOUR_ORG_ID
mist_site_id=YOUR_SITE_ID
```

The token in a `.env` file is stored in plain text. Keep the file out of version control (add `.env` to `.gitignore`) or use the keychain option instead.

## Settings and files

- Preferences (region, org ID, site ID, CSV path, output folder, mode) are saved to `~/.mist_bssid_gui.json`. The API token is never saved there.
- The API token is only stored if you tick the keychain option, and then it goes to the OS keychain, not to disk.

## API endpoints used

All requests are `GET`:

- `/api/v1/self`
- `/api/v1/orgs/{org_id}/sites`
- `/api/v1/sites/{site_id}/maps`
- `/api/v1/sites/{site_id}/stats/devices` (all APs, paged)
- `/api/v1/sites/{site_id}/stats/devices/{device_id}` (one AP, CSV mode)

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'requests'` | The package isn't installed in the Python you are running. Make sure the venv is active (your prompt should start with `(.venv)`), then run `pip install requests`. A new terminal window needs `source .venv/bin/activate` again. |
| `ModuleNotFoundError: ... '_tkinter'` or `Unsupported platform for standard library module '_tkinter'` | Your Python was installed without Tk. On macOS with Homebrew: `brew install python-tk@3.X`, matching `python3 --version`. On Debian/Ubuntu: `sudo apt install python3-tk`. If it still fails, delete `.venv` and recreate it. |
| Prompt has no `(.venv)` | The venv isn't active. Run `source .venv/bin/activate` from the folder that contains `.venv`. If the folder doesn't exist, create it with `python3 -m venv .venv`. |
| `401 Unauthorized` | Wrong token or wrong region. Check that the region matches where your org lives. |
| `403 Forbidden` | The token has no access to that org or site. |
| `404 Not found` for some APs in CSV mode | The inventory export covers the whole org, but the selected site only has some of those APs. These are logged and counted as errors, and the run continues. |
| Repeated `429` messages | Mist is rate-limiting you. The tool waits and retries automatically. |

## Credits and license

- Original script: [allynjcrowe/mist-get_bssid](https://github.com/allynjcrowe/mist-get_bssid), Allyn Crowe, Nexum (GPL-3.0).
- This GUI is a derivative work and is also released under the **GNU General Public License v3.0**. See [`LICENSE`](LICENSE) for the full text.
