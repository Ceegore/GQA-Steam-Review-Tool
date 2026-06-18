# Steam Review Analyzer

A small Windows (and macOS/Linux) tool to fetch **all Steam reviews** of a game
in all available languages, with filter options, and export everything to a
single self-contained `.md` file.

> **v0.2 — Refactored (Atomic Code Architecture).**
> The original 9,360-line monolith (`steam_review_tool.py`) has been
> decomposed into a 71-module package (`steam_review_tool/`) with a hard
> 500-line limit per file, dependency injection, and a strict zero-cycle
> import graph. See `_refactoringplan.md` for the full plan and history.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.10+** | Zero build step, easy to read & modify |
| UI | **CustomTkinter** | Modern dark-mode look, no Electron / Qt |
| HTTP | **requests** | Robust, well-known |
| Export | Pure Python Markdown rendering | No extra dependency |

## Features

- **Input:** accepts an App ID, a full Steam store URL, or a `steam://` link
- **App details:** name, developer, publisher, release date, platforms
- **All Steam reviews** via cursor-based pagination (handles 10,000+ reviews)
- **All languages** via the `language=all` parameter
- **Filters:**
  - Language (English, German, …, or "all")
  - Sort order (`all` / `recent` / `updated`)
  - Review type (`all` / `positive` / `negative`)
  - Max age in days (Steam `day_range` parameter)
  - Minimum date (client-side filter, format `YYYY-MM-DD`)
  - Minimum helpful-vote count
  - Reviews per page (20 / 50 / 100)
- **Live progress** (progress bar + page counter)
- **Stop** at any time
- **Markdown export** with game info, applied filters, summary stats,
  per-language distribution, and every review with all metadata
- **Open store page** shortcut
- **Time-series trends** for wishlist / follower / review counts
- **Watch mode** (poll for new reviews)
- **Optional per-language / CSV / JSON split exports**
- **Obsidian-vault sync**

## Install & run

```powershell
# 1. Create a virtual environment (recommended)
cd d:\Projects\test2\steam_review_tool
python -m venv .venv
.\.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py
```

The old monolith `steam_review_tool.py` is preserved as a back-compat
shim and still works with `python steam_review_tool.py`. **New work
should target `main.py` and import from the `steam_review_tool.*`
package.**

## Architecture (v0.2)

```
steam_review_tool/
├── main.py                       # Entry-point (calls App.mainloop)
├── _refactoringplan.md           # The plan that produced this layout
├── _verify.py                    # Pre-commit-style sanity gate
├── build.spec                    # PyInstaller spec
├── steam_review_tool.py          # Back-compat shim -> main.py
├── steam_review_tool/            # The actual source package
│   ├── core/           (5)        constants, timezone, paths, event_bus, logger
│   ├── interfaces/     (8)        Protocol contracts (ISteamApi, IExportTarget, …)
│   ├── models/         (7)        dataclasses (AppDetails, FilterConfig, …)
│   ├── utils/          (5)        pure helpers, no state
│   ├── services/       (13)       SteamAPI, ApifyClient, DumpRepository, TrendsStore,
│   │                              SettingsStore, ReviewAnalyzer, PreAIDigest,
│   │                              BrowserLauncher, PlaywrightJS, PlaywrightSubprocess, …
│   ├── exporters/      (7)        Markdown (+helpers), CSV, JSON,
│   │                              PerLanguage, ObsidianCopier, ExportOrchestrator
│   ├── ui/             (13)       ToolTip, CollapsibleGroup, InfoPanel,
│   │                              SectionHeader, 9 popups, 3 tab controllers, App
│   ├── controllers/    (6)        api/pw/trends workflows, settings, dump-folder,
│   │                              filter, action_handler
│   └── factories/      (1)        App composition root
└── tests/                        # Unit tests (pytest)
    ├── smoke/                    # App boots, can be built & destroyed
    ├── services/                 # Pure-function tests for analyzers + utils
    └── exporters/                # Markdown / CSV / JSON output
```

**Rules enforced by `_verify.py`:**
- 0 files > 500 lines
- 0 circular imports
- App builds headless
- All modules import cleanly

## Verifying the package

```powershell
python _verify.py
```

Exits `0` on success, prints `STATUS: PASS`. Suitable as a pre-commit
hook.

## Usage

1. Paste an App ID or a Steam store URL (e.g. `4311090` or
   `https://store.steampowered.com/app/4311090/Bus_Simulator_27_Demo/`)
   and click **Load Game**.
2. Adjust the filters in the *Filters* panel.
3. Click **Fetch Reviews** — the progress bar will update per page.
4. Click **Stop** to cancel mid-fetch.
5. When done, click **Export to .md** and pick a destination.

## Output example

The exported Markdown file contains:

- A title block with game name and export timestamp
- A "Game Information" table (ID, dev, publisher, release, platforms, URL)
- An "Applied Filters" table (so the export is reproducible)
- A "Summary" block with totals, positivity ratio, and per-language distribution
- A "Pre-AI Digest" block: stats, top complaints / praise, top reviewers
- An "All Reviews" section with every review including:
  - Author, profile link, review URL
  - Recommendation (👍/👎)
  - Language, posted/updated timestamps
  - Steam-purchase flag, free-game flag
  - Playtime, last played, helpful/funny/comment counts
  - Dev-weighted score
  - Auto-classified type (bug/feature/praise/complaint)
  - User-defined keyword tags
  - Full review text (blockquote, keywords highlighted)

## Notes on Steam API limits

- Steam's review API is **public** and does not require an API key, but
  it is rate-limited. The tool sleeps 0.4 s between page requests.
- For very new apps the review feed may be empty for a while even though
  the storefront shows reviews (Steam's review index is cached separately).
- The `language=all` parameter asks Steam to return all languages, but
  Steam may still apply a server-side filter based on your Steam account's
  language preferences. For an exhaustive result, also run the tool with
  each specific language and concatenate the exports.
- The `min_date` filter is applied **client-side** because the Steam API
  has no native "since" parameter.

## Files

| Path | Purpose |
|---|---|
| `main.py` | Entry-point (preferred) |
| `steam_review_tool.py` | Back-compat shim — calls into the package |
| `steam_review_tool/` | The refactored 71-module package |
| `_refactoringplan.md` | The plan that drove this refactor |
| `_verify.py` | Sanity gate (run before committing) |
| `requirements.txt` | Runtime deps |
| `requirements-dev.txt` | Adds PyInstaller |
| `build.spec` | PyInstaller spec (`collect_submodules('steam_review_tool')`) |
| `build.bat` | One-click Windows build |
| `tests/` | Unit tests (pytest) |

## Build a Windows .exe (no Python required to run)

A pre-built `SteamReviewAnalyzer.exe` is at `dist/SteamReviewAnalyzer.exe`
after a successful build. It runs on any Windows 10/11 machine without Python.

### One-click build (Windows)

```powershell
cd d:\Projects\test2\steam_review_tool
build.bat
```

The script will:
1. Create a `.venv` (if missing)
2. Install `requirements-dev.txt` (customtkinter, requests, pyinstaller)
3. Run PyInstaller against `build.spec`
4. Drop the .exe into `dist\SteamReviewAnalyzer.exe`

### Manual build

```powershell
cd d:\Projects\test2\steam_review_tool
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
pyinstaller --clean --noconfirm build.spec
```

Result: `dist\SteamReviewAnalyzer.exe` — single, windowed, double-clickable.

### Build details

- Mode: `--onefile --windowed` → single .exe, no console window pops up
- CustomTkinter assets (themes, fonts, JSON descriptors) are bundled
  via `collect_all("customtkinter")` in `build.spec`
- The entire `steam_review_tool/` package is bundled via
  `collect_submodules("steam_review_tool")` so the .exe picks up every
  service, controller, and widget automatically.
- Size: ~13 MB (UPX-compressed)
- First launch is slightly slower (PyInstaller extracts to `%TEMP%`);
  subsequent launches are instant
- Tested on Windows 11 with Python 3.12 + PyInstaller 6.21

### Icon (optional)

To give the .exe a custom icon, drop a 256×256 `.ico` file into the
project folder and uncomment the `icon=` line in `build.spec`, then
rebuild.

## Migrating old code that imported from the monolith

Before:
```python
from steam_review_tool import SteamAPI, MarkdownExporter, ToolTip
```

After:
```python
from steam_review_tool.services.steam_api_service import SteamAPI
from steam_review_tool.exporters.markdown_exporter import MarkdownExporter
from steam_review_tool.ui.tooltip import ToolTip
```

The mapping for every symbol is in `_refactoringplan.md` § 4.1.