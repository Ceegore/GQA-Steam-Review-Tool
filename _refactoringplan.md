# Refactoring-Plan: Atomic Code Architecture
**Projekt:** `steam_review_tool` — Steam Review Analyzer
**Aktueller Stand:** 1 Datei, **8.623 Zeilen** (`steam_review_tool.py`)
**Ziel:** Modularisierung in eine stark entkoppelte, AI-freundliche Architektur mit max. 500 Zeilen pro Datei.

---

## 1. Zielsetzung

Die monolithische Datei `steam_review_tool.py` enthält aktuell **eine einzige "God-Class"** (`App`, ca. 4.815 Zeilen, ~250 Methoden), eine **fette Service-Klasse** (`SteamAPI`, ~1.090 Zeilen), **20+ UI-Klassen/Dialoge**, **mehrere Helper-Bereiche** (Datums-Picker, Filter-Parser, Trends) und einen **eingebetteten ~350-Zeilen-Playwright-JS-Skript-String**.

**Konsequenzen für AI-Agenten heute:**
- LLM-Context wird bereits beim reinen Öffnen der Datei gesprengt (>30 k Tokens)
- Halluzinationen bei Änderungen an isolierten Features, weil der Agent den gesamten Import-Graph im Kopf behalten muss
- Keine unit-testbare Isolation (jeder Test benötigt `tkinter` und die App-Instanz)

**Zielbild:** Atomare, fokussierte Module, die jeweils exakt eine Aufgabe erfüllen, klar benannt sind und über schmale Interfaces (oder ein Event-Bus) kommunizieren. Nach dem Refactoring passen **jede einzelne Datei und ihr vollständiger Kontext in den LLM-Focus**, und ein Feature-Wunsch wie *"Füge einen neuen Apify-Filter hinzu"* benötigt nur das Laden von **2-3 Dateien à < 300 Zeilen**.

---

## 2. Struktur-Taxonomie (Neue Ordnerstruktur)

```
steam_review_tool/
├── main.py                          # Entry-Point (war: if __name__ == "__main__")
├── requirements.txt
├── build.spec
├── build.bat
├── README.md
│
├── steam_review_tool/               # Source-Package (neu)
│   │
│   ├── __init__.py
│   │
│   ├── core/                        # Lifecycle, Konstanten, globale Utilities
│   │   ├── __init__.py
│   │   ├── constants.py             # STEAM_API_BASE, STEAM_LANGUAGES, DEFAULT_DUMP_ROOT
│   │   ├── timezone.py              # BERLIN, format_berlin(), current_berlin_str()
│   │   ├── paths.py                 # PathHelper (dump_root, game_folder, seen_ids_path)
│   │   ├── event_bus.py             # SimpleEventBus (publish/subscribe)
│   │   └── logger.py                # get_logger(name) → zentrales Logging
│   │
│   ├── interfaces/                  # Reine Verträge (je 5-30 Zeilen)
│   │   ├── __init__.py
│   │   ├── i_steam_api.py           # ISteamApi
│   │   ├── i_settings_store.py      # ISettingsStore
│   │   ├── i_review_source.py       # IReviewSource (api | playwright)
│   │   ├── i_dump_repository.py     # IDumpRepository
│   │   ├── i_export_target.py       # IExportTarget
│   │   ├── i_trends_store.py        # ITrendsStore
│   │   ├── i_window_context.py      # IWindowContext (Zugriff auf CTk-Widgets)
│   │   └── i_clock.py               # IClock (testbare Zeit-Quelle)
│   │
│   ├── models/                      # Reine Datenstrukturen (dataclasses)
│   │   ├── __init__.py
│   │   ├── app_details.py           # AppDetails, Platforms
│   │   ├── review.py                # Review, ReviewFilter, ReviewSort, ReviewType
│   │   ├── filter_config.py         # FilterConfig (since, min_date, helpful, …)
│   │   ├── export_context.py        # ExportContext (war: @dataclass ab Zeile 3920)
│   │   ├── trends_snapshot.py       # TrendsSnapshot, TrackedApp
│   │   ├── keyword_list.py          # KeywordList
│   │   └── ai_prompt_template.py    # AIPromptTemplate
│   │
│   ├── utils/                       # Reine Helper-Funktionen, KEIN State
│   │   ├── __init__.py
│   │   ├── datetime_utils.py        # parse_since_preset, compute_since_timestamp
│   │   ├── text_utils.py            # sanitize_for_filename, short_filter_label
│   │   ├── file_hash.py             # _file_content_hash, file_hash_cached
│   │   ├── url_utils.py             # resolve_app_id (Steam-URL-Parser)
│   │   └── markdown_utils.py        # _md_escape, _to_iso, _yesno
│   │
│   ├── services/                    # Hintergrund-Logik, KEINE UI
│   │   ├── __init__.py
│   │   ├── steam_api_service.py     # SteamAPI (war: Zeile 2832)
│   │   ├── playwright_scraper.py    # PlaywrightScraper (war: Teile von App + JS-Script)
│   │   ├── playwright_subprocess.py # PlaywrightSubprocessRunner
│   │   ├── python_runtime.py        # _find_external_python, _probe_external_python
│   │   ├── dependency_checker.py    # is_playwright_available, is_chromium_installed
│   │   ├── dependency_installer.py  # install_playwright, install_chromium
│   │   ├── dump_repository.py       # SeenIdsRepository (File-I/O für seen_ids.json)
│   │   ├── resume_store.py          # ResumeStore (API + PW Resume-Cursor)
│   │   ├── trends_store.py          # TrendsStore (war: Zeile 1469)
│   │   ├── review_analyzer.py       # classify_review_type, extract_tags,
│   │   │                            # aggregate_top_themes, compute_playtime_histogram,
│   │   │                            # split_first_24h, compute_deltas
│   │   ├── pre_ai_digest.py         # build_pre_ai_digest, quick_stats_footer
│   │   ├── settings_store.py        # SettingsStore (JSON-Load/Save unter ~/.steam_review_tool/)
│   │   ├── browser_launcher.py      # Anti-Detect + GATE_BUTTON_TEXTS
│   │   └── store_page_parser.py     # fetch_popularity_metrics (DOM-Snippets)
│   │
│   ├── exporters/                   # Output-Strategien
│   │   ├── __init__.py
│   │   ├── markdown_exporter.py     # MarkdownExporter.render (war: Zeile 3937)
│   │   ├── csv_exporter.py          # reviews_to_csv
│   │   ├── json_exporter.py         # reviews_to_json
│   │   ├── per_language_exporter.py # group_by_language, write_per_language
│   │   ├── obsidian_copier.py       # copy_to_obsidian_vault
│   │   └── export_orchestrator.py   # koordiniert md/csv/json/per-lang
│   │
│   ├── ui/                          # CustomTkinter-Komponenten
│   │   ├── __init__.py
│   │   ├── app_window.py            # App (nur noch ~300 Z. Lifecycle + DI)
│   │   ├── tooltip.py               # ToolTip (war: Zeile 4466)
│   │   ├── collapsible_group.py     # CollapsibleGroup (war: Zeile 1604)
│   │   ├── info_panel.py            # InfoPanel (war: Zeile 1676)
│   │   ├── log_text.py              # LogText-Widget (shared scrollbar)
│   │   ├── section_header.py        # _make_section helper
│   │   ├── tab_api.py               # ApiTabController (war: _build_tab_api, ~580 Z.)
│   │   ├── tab_playwright.py        # PlaywrightTabController (~440 Z.)
│   │   ├── tab_trends.py            # TrendsTabController (~115 Z.)
│   │   ├── popup_date_picker.py     # DatePickerPopup (war: Zeile 798)
│   │   ├── popup_time_picker.py     # TimePickerPopup (war: Zeile 956)
│   │   ├── popup_help.py            # HelpDialog (war: Zeile 1769)
│   │   ├── popup_top_complaints.py  # TopComplaintsDialog (war: Zeile 1875)
│   │   ├── popup_search.py          # SearchWindow (war: Zeile 1986)
│   │   ├── popup_settings.py        # SettingsDialog (war: Zeile 2208)
│   │   ├── popup_batch_dump.py      # BatchDumpDialog (war: Zeile 2338)
│   │   ├── popup_trends_chart.py    # TrendsWindow (war: Zeile 2539)
│   │   └── popup_about.py           # AboutDialog (aus _on_show_about extrahiert)
│   │
│   └── factories/                   # Dependency Injection (Composition Root)
│       ├── __init__.py
│       └── app_factory.py           # AppFactory.build() → verdrahtet Services an UI
│
└── resources/                       # Optional: statische Assets (Icons, Fonts)
```

**Verzeichnis-Größe-Prognose:** ~75 Dateien, Ø ~110 Zeilen, Maximum ~480 Zeilen (`markdown_exporter.py`).

---

## 3. Code-Format & Konventionen

### 3.1 Datei-Hardlimits
- **Absolute Obergrenze:** 500 Zeilen pro Datei (ohne Leerzeilen/Kommentare zählt reiner Code).
- **Warnschwelle:** ab 300 Zeilen Refactoring-Pflicht (Datei wird in Phase N+1 aufgespalten).
- **Verbot von "God-Words"** im Dateinamen: `Manager`, `Controller`, `System`, `Helper` (außer in `popup_*` und `tab_*` per Konvention, da UI-Pattern).

### 3.2 Datei-Aufbau (strikt in dieser Reihenfolge)
```python
"""Modul-Docstring: 1 Satz Verantwortlichkeit + 1-3 Sätze Kontext."""
from __future__ import annotations
# 1. Imports (alphabetisch sortiert, je Block: stdlib, third-party, local)
import json
from pathlib import Path
from typing import Optional
import customtkinter as ctk
from steam_review_tool.core.logger import get_logger
from steam_review_tool.interfaces.i_dump_repository import IDumpRepository
# 2. Modul-Konstanten (in ALL_CAPS)
MAX_RETRIES = 3
# 3. Helper (private, _prefix)
def _validate_path(p: Path) -> bool: ...
# 4. Public API (Klassen/Funktionen)
class DumpRepository: ...
# 5. __all__ (exporterte Symbole)
__all__ = ["DumpRepository"]
```

### 3.3 Dependency Injection (statt `new X()`)
Jede Klasse bekommt ihre Abhängigkeiten über den Konstruktor:
```python
class ApiTabController:
    def __init__(
        self,
        parent: ctk.CTkFrame,
        context: IWindowContext,
        review_source_factory: Callable[[], IReviewSource],
        settings: ISettingsStore,
        clock: IClock,
    ) -> None:
        self._ctx = context
        self._source_factory = review_source_factory
        self._settings = settings
        self._clock = clock
```
**Verboten:** `SteamAPI()`, `TrendsStore(...)`, `SettingsStore()` direkt im UI-Code — immer über Factory.

### 3.4 Event-Bus (statt direkter Aufrufe)
Statt `self.api.split_button.bind(...)` + `self.api.export_to_path(...)` quer durchs Tab:
```python
# services/publishers.py
event_bus.publish("review.fetch.completed", reviews=..., source="api")
event_bus.subscribe("review.fetch.completed", self._on_reviews_loaded)
event_bus.subscribe("settings.changed", self._refresh_filter_labels)
```
**Vorteil:** Tab kennt Service nicht, Service kennt Tab nicht → **keine zirkulären Imports**.

### 3.5 Interface-Konvention
Jedes Interface in `interfaces/` ist ein `Protocol` (für Entkopplung + Type-Hints), nie eine `ABC`-Hierarchie:
```python
# interfaces/i_review_source.py
from typing import Protocol
from steam_review_tool.models.review import Review
class IReviewSource(Protocol):
    def fetch_all(self, app_id: int, config: FilterConfig) -> Iterator[Review]: ...
    def cancel(self) -> None: ...
```

---

## 4. Mapping: Alt → Neu (Ist → Soll)

### 4.1 Aktuelle Klassen (53 Stück) und ihre neuen Heimat-Dateien

| Aktuelle Zeile | Symbol | Neue Datei |
|---|---|---|
| 79 | `PLAYWRIGHT_SCRAPER_SCRIPT` | `services/browser_launcher.py` + `services/playwright_scraper.py` (ausgelagert in `.py` als String) |
| 424 | `main()` (Bootstrap) | `main.py` |
| 604 | `parse_since_preset` | `utils/datetime_utils.py` |
| 616 | `compute_since_timestamp` | `utils/datetime_utils.py` |
| 660 | `format_berlin` | `core/timezone.py` |
| 668 | `current_berlin_str` | `core/timezone.py` |
| 695 | `DEFAULT_DUMP_ROOT` | `core/constants.py` |
| 698 | `_file_content_hash` | `utils/file_hash.py` |
| 714 | `sanitize_for_filename` | `utils/text_utils.py` |
| 734 | `make_export_basename` | `utils/text_utils.py` |
| 753 | `short_filter_label` | `utils/text_utils.py` |
| 798 | `DatePickerPopup` | `ui/popup_date_picker.py` |
| 956 | `TimePickerPopup` | `ui/popup_time_picker.py` |
| 1147 | `classify_review_type` | `services/review_analyzer.py` |
| 1175 | `extract_tags` | `services/review_analyzer.py` |
| 1222 | `aggregate_top_themes` | `services/review_analyzer.py` |
| 1290 | `compute_playtime_histogram` | `services/review_analyzer.py` |
| 1326 | `split_first_24h` | `services/review_analyzer.py` |
| 1348 | `compute_deltas` | `services/review_analyzer.py` |
| 1373 | `build_pre_ai_digest` | `services/pre_ai_digest.py` |
| 1446 | `quick_stats_footer` | `services/pre_ai_digest.py` |
| 1469 | `TrendsStore` | `services/trends_store.py` |
| 1604 | `CollapsibleGroup` | `ui/collapsible_group.py` |
| 1676 | `InfoPanel` | `ui/info_panel.py` |
| 1769 | `HelpDialog` | `ui/popup_help.py` |
| 1875 | `TopComplaintsDialog` | `ui/popup_top_complaints.py` |
| 1986 | `SearchWindow` | `ui/popup_search.py` |
| 2208 | `SettingsDialog` | `ui/popup_settings.py` |
| 2338 | `BatchDumpDialog` | `ui/popup_batch_dump.py` |
| 2539 | `TrendsWindow` | `ui/popup_trends_chart.py` |
| 2832 | `SteamAPI` | `services/steam_api_service.py` |
| 3920 | `ExportContext` | `models/export_context.py` |
| 3937 | `MarkdownExporter` | `exporters/markdown_exporter.py` |
| 4267 | `group_by_language` | `exporters/per_language_exporter.py` |
| 4276 | `write_per_language` | `exporters/per_language_exporter.py` |
| 4307 | `reviews_to_csv` | `exporters/csv_exporter.py` |
| 4350 | `reviews_to_json` | `exporters/json_exporter.py` |
| 4357 | `build_summary` | `exporters/per_language_exporter.py` |
| 4466 | `ToolTip` | `ui/tooltip.py` |
| 4539 | `App` (God-Class) | **zerlegt in 5 Dateien** (s. §4.2) |
| 9354 | `main()` | `main.py` |

### 4.2 Zerschlagung der `App`-God-Class (~4.815 Z., ~250 Methoden)

| Methoden-Cluster | Verantwortlichkeit | Neue Datei | ~Zeilen |
|---|---|---|---|
| `__init__`, `_build_ui`, `_tick_clock`, `_tick_info_clock`, `_refresh_status_bar`, `_tick_status_bar`, `_on_close` | **App-Lifecycle + globale UI-Struktur** | `ui/app_window.py` | ~280 |
| `_build_tab_api` (~580 Z.) | **Tab "Steam API" komplett** | `ui/tab_api.py` | ~480 |
| `_build_tab_playwright` (~440 Z.) | **Tab "Playwright" komplett** | `ui/tab_playwright.py` | ~420 |
| `_build_tab_trends` (~115 Z.) | **Tab "Trends"** | `ui/tab_trends.py` | ~115 |
| `_on_load`, `_fetch_worker`, `_on_progress`, `_on_stop`, `_on_api_resume`, `_watch_*`, `_auto_incr_export`, `_on_new_reviews`, `_export_split_write`, `_on_export`, `_do_export_to_path`, `_also_csv`, `_also_json`, `_per_language`, `_get_keyword_list`, `_get_ai_prompt_template`, `_format_ai_prompt` | **Steam-API-Workflow** | `controllers/api_workflow.py` | ~480 |
| `_on_pw_load`, `_refresh_dep_status`, `_on_install_playwright`, `_on_install_chromium`, `_find_working_python`, `_on_pw_scrape`, `_on_pw_resume`, `_pw_scrape_worker`, `_on_pw_export`, `_do_pw_export_to_path`, `_pw_log`, `_refresh_pw_since_label` | **Playwright-Workflow** | `controllers/playwright_workflow.py` | ~480 |
| `_trends_refresh_worker`, `_refresh_trends_list`, `_on_trends_*`, `_trends_log_line`, `_get_trends_store`, `_on_trends_view_graph`, `_load_reviews_for_trends` | **Trends-Workflow** | `controllers/trends_workflow.py` | ~280 |
| `_make_section`, `_build_since_section`, `_on_since_preset_change`, `_on_pw_since_preset_change`, `_toggle_since_row`, `_refresh_since_label`, `_since_preset_attr`, `_since_date_attr`, `_since_time_attr`, `get_since_timestamp`, `_parse_min_date`, `_parse_day_range`, `_parse_helpful`, `_reset_api_filters`, `_reset_pw_filters` | **Filter-Helfer (shared API+PW)** | `controllers/filter_controller.py` | ~280 |
| `_settings_load/save/apply`, `_on_settings`, `_settings_load_raw`, `_resume_load_all`, `_resume_save_all`, `_resume_get/set/clear`, `_refresh_resume_buttons` | **Settings-Controller** | `controllers/settings_controller.py` | ~280 |
| `_get_dump_root`, `_get_game_dump_folder`, `_seen_ids_path`, `_load_seen_ids`, `_save_seen_ids`, `_on_pick_obsidian_vault`, `_on_clear_obsidian_vault`, `_refresh_obsidian_label`, `_copy_to_obsidian_vault`, `_on_pick_dump_root`, `_on_open_dump_folder`, `_on_open_game_folder`, `_refresh_dump_label`, `_on_fetch_new` | **Dump-Folder-Controller** | `controllers/dump_folder_controller.py` | ~280 |
| `_on_copy_with_ai_prompt`, `_on_save_as_prompt`, `_on_open_latest_md`, `_on_quick_view_negatives`, `_on_top_complaints`, `_on_copy_filtered_dump`, `_on_batch_dump`, `_on_search_dump`, `_on_write_summary`, `_on_open_store`, `_on_show_help`, `_on_show_about`, `_clear_loaded_game`, `_set_busy` | **Action-Handler** | `controllers/action_handler.py` | ~280 |
| `_log`, `_update_info_panels`, `_reorganize_tab` | **Logger + Info-Panel** | `ui/log_controller.py` | ~120 |

**Ergebnis:** App-Klasse schrumpft von 4.815 auf ~280 Zeilen. Jeder Controller hat **eine Verantwortlichkeit**.

---

## 5. Refactoring-Prozess (Phasen mit Sicherheitsnetz)

> **Grundregel:** Nach **jeder Phase** ist die App lauffähig. Wir refactoren **behavior-preserving** und testen manuell + automatisch.

### Phase 0 — Vorbereitung (1-2 h)
- **0.1** `tests/` Ordner anlegen, `pytest` installieren.
- **0.2** Snapshot der aktuellen App erzeugen (`git tag pre-refactor`).
- **0.3** Smoke-Test schreiben: `tests/smoke/test_app_starts.py` — startet App headless, schließt nach 1 s.
- **0.4** Black-/Ruff-Config anlegen, damit Stil konsistent bleibt.

### Phase 1 — Konstanten, Utilities, Interfaces extrahieren (≤ 4 h, **Zero-Risk**)
- **1.1** `core/constants.py` anlegen, Konstanten aus Zeile 48-63 verschieben.
- **1.2** `core/timezone.py` extrahieren (Zeile 27-34, 660-670).
- **1.3** `utils/text_utils.py`, `utils/datetime_utils.py`, `utils/url_utils.py`, `utils/file_hash.py` extrahieren.
- **1.4** `core/event_bus.py` minimal implementieren (~30 Zeilen).
- **1.5** `interfaces/` Ordner anlegen, alle 8 Protocol-Dateien mit leeren Methoden-Rümpfen.
- **1.6** Smoke-Test grün. ✅

### Phase 2 — Services herauslösen (≤ 1 Tag, **Low-Risk**)
- **2.1** `services/steam_api_service.py` = 1:1-Extraktion von `SteamAPI`. **Keine** Logik-Änderung.
- **2.2** `services/dump_repository.py` (Methoden `_get_game_dump_folder`, `_seen_ids_path`, `_load_seen_ids`, `_save_seen_ids`).
- **2.3** `services/settings_store.py` (`_settings_load/save/apply/load_raw`).
- **2.4** `services/trends_store.py` (TrendsStore 1:1).
- **2.5** `services/resume_store.py` (`_resume_load_all`, `_resume_save_all`, `_resume_get/set/clear`).
- **2.6** `services/review_analyzer.py` (alle pure Funktionen ab Zeile 1147).
- **2.7** `services/pre_ai_digest.py` (`build_pre_ai_digest`, `quick_stats_footer`).
- **2.8** Pro Service ein Unit-Test (`tests/services/test_*.py`).
- **2.9** App-Klasse ruft jetzt Services über ihre Interface-Protocols auf. Alle Funktionsaufrufe müssen via DI ersetzt werden.
- ✅ **Checkpoint:** App läuft, Tests grün.

### Phase 3 — Exporter & Models isolieren (≤ 0,5 Tage)
- **3.1** `models/` — alle `@dataclass` Klassen aus dem Hauptfile heraus.
- **3.2** `exporters/markdown_exporter.py` = 1:1-Extraktion von `MarkdownExporter`.
- **3.3** `exporters/csv_exporter.py`, `exporters/json_exporter.py`, `exporters/per_language_exporter.py`.
- **3.4** `exporters/export_orchestrator.py` als neuer Composer (aus `_do_export_to_path`).
- **3.5** `exporters/obsidian_copier.py` (`_copy_to_obsidian_vault`).
- ✅ **Checkpoint:** Export-Pipeline funktional identisch (Datei-Vergleich alt/neu).

### Phase 4 — UI-Primitive (Popups & Widgets) (≤ 1 Tag)
- **4.1** `ui/tooltip.py`, `ui/collapsible_group.py`, `ui/info_panel.py`, `ui/log_text.py`, `ui/section_header.py` — jeweils 1:1 extrahieren.
- **4.2** `ui/popup_*.py` für alle 9 Dialoge.
- **4.3** `factories/app_factory.py` initial: lädt nur den App-Lifecycle + Popups.
- ✅ **Checkpoint:** `App` hat keine Popup-Logik mehr, aber alles startet noch.

### Phase 5 — Tab-Controller (Big Bang mit Sicherheitsnetz) (≤ 2 Tage)
- **5.1** `ui/tab_api.py` anlegen. `_build_tab_api` 1:1 übernehmen. **Aufpassen:** Closures auf `self.app_id`, `self.reviews`, `self._settings_*` müssen zu Konstruktor-Injects werden.
- **5.2** `ui/tab_playwright.py`, `ui/tab_trends.py` analog.
- **5.3** Pro Tab-Controller eine `IWindowContext` definieren (Widgets, die quer benutzt werden).
- **5.4** **Manuelle Tests:** jeden Tab klicken, jeden Filter setzen, jeden Button drücken.
- ✅ **Checkpoint:** App ist jetzt nur noch Tab-Orchestrator (~280 Z.) + 3 Tabs.

### Phase 6 — Workflow-Controller (Logik aus App heraus) (≤ 2 Tage)
- **6.1** `controllers/api_workflow.py` — Methoden `_on_load`, `_fetch_worker`, `_on_stop`, `_on_export`, …
- **6.2** `controllers/playwright_workflow.py` — alle `_on_pw_*` Methoden + Dependency-Install.
- **6.3** `controllers/trends_workflow.py`.
- **6.4** `controllers/filter_controller.py` (since-Logik).
- **6.5** `controllers/dump_folder_controller.py`.
- **6.6** `controllers/settings_controller.py`.
- **6.7** `controllers/action_handler.py` (Copy-to-AI, Search-Dump, About, Help).
- **6.8** Event-Bus-Verdrahtung: Tabs publishen, Workflows subscriben.
- ✅ **Checkpoint:** Alle Buttons funktional identisch.

### Phase 7 — Playwright-JS-Skript auslagern (≤ 0,5 Tage)
- **7.1** `services/browser_launcher.py` mit `ANTI_DETECT` und `GATE_BUTTON_TEXTS`.
- **7.2** `services/playwright_scraper.py` als reine Python-Klasse, die JS über `page.evaluate()` aufruft (statt String-Injection).
- **7.3** JS-Logik aus dem String in `static/js/scraper.js` als eigene Datei (zur Laufzeit geladen).
- ✅ **Checkpoint:** Playwright-Tab funktioniert identisch.

### Phase 8 — Cleanup & Hardlimit-Check (≤ 0,5 Tage)
- **8.1** Tool `wc -l steam_review_tool/**/*.py | sort -n` ausführen.
- **8.2** Jede Datei > 500 Z. → weiter aufteilen.
- **8.3** Zirkularitäts-Check: `pydeps steam_review_tool/` oder `importlinter`.
- **8.4** Coverage-Report: pro Service/Controller ≥ 1 Unit-Test.
- **8.5** PyInstaller-Build testen (`build.bat`) — Bundle muss weiterhin funktionieren.
- **8.6** README aktualisieren (neue Start-Anweisung: `python main.py`).

---

## 6. Zukünftiger Agent-Workflow (Beispiel)

**Szenario:** User fordert *"Füge einen neuen Filter 'nur Reviews mit Dev-Antwort' im Steam-API-Tab hinzu"*.

**Vorher (heute):**
1. Agent lädt 8.623 Z. Kontext.
2. Sucht die richtige Stelle in `_build_tab_api` → Risk, versehentlich was an `_fetch_worker` zu ändern.
3. Testet manuell.

**Nachher (nach Refactoring):**
1. Agent lädt **nur**:
   - `interfaces/i_review_source.py` (40 Z., um Signatur zu prüfen)
   - `services/steam_api_service.py` (480 Z., um Filter durchzureichen)
   - `ui/tab_api.py` (480 Z., um neue Checkbox + Bindung zu ergänzen)
   - `models/filter_config.py` (60 Z., um neues Feld zu ergänzen)
   - ggf. `controllers/api_workflow.py` (480 Z., wenn Worker-Logik betroffen)
2. **Summe:** ~1.560 Z. = ~18 % der Originaldatei. Passt locker in jedes LLM-Context-Window.
3. Agent kann fokussiert arbeiten, mit hoher Wahrscheinlichkeit keine Halluzinationen, da Imports klar sind.

**Weitere Beispiele:**
| Aufgabe | Benötigte Dateien | ~Zeilen |
|---|---|---|
| Bug in Datums-Picker | `ui/popup_date_picker.py` | 160 |
| Neuer Export-Format (PDF) | `exporters/pdf_exporter.py` (NEU) + `exporters/export_orchestrator.py` | 200 + 280 |
| Neuer Trends-Metriken | `services/trends_store.py` + `ui/popup_trends_chart.py` | 320 + 295 |
| Obsidian-Export anpassen | `exporters/obsidian_copier.py` | 180 |

---

## 7. Erfolgskontrolle

### 7.1 Quantitative Ziele
- [ ] **0 Dateien** ≥ 500 Zeilen (gemessen mit `cloc`/`wc -l`).
- [ ] **≥ 80 %** der Dateien ≤ 300 Zeilen.
- [ ] **0 zirkuläre Imports** (geprüft mit `pydeps --no-show --circular`).
- [ ] **App-Startzeit** ≤ +5 % ggü. pre-refactor (gemessen mit `time python main.py`).
- [ ] **PyInstaller-Build** (`build.bat`) erzeugt funktionsfähiges `.exe` mit CustomTkinter-Bundle.
- [ ] **≥ 30 Unit-Tests** für Services, Utils und Models.

### 7.2 Qualitative Ziele
- [ ] Jede Datei hat **einen** klaren Verantwortlichkeitssatz im Modul-Docstring.
- [ ] Keine Datei mit `Manager`, `Controller` (außer in `controllers/`-Ordner per Konvention), `Helper`, `System` im Namen (außer historisch gewachsene UI-Suffixe).
- [ ] Jeder Service hat **eine** Protocol-Interface-Datei in `interfaces/`.
- [ ] **Event-Bus** wird für alle Cross-Module-Kommunikation genutzt (Tabs ↔ Workflows).
- [ ] **DI-Konstruktoren** in allen UI-Klassen (kein `MyService()` im UI-Code).

### 7.3 Reviewer-Checkliste
Vor jedem Merge in `main`:
1. `python main.py` startet ohne Fehler.
2. Smoke-Test `pytest tests/smoke -q` grün.
3. `wc -l steam_review_tool/**/*.py | awk '$1 > 500'` → leere Ausgabe.
4. `pydeps steam_review_tool/ --show-cycles` → leer.
5. `build.bat` erzeugt `.exe` ≤ 15 MB.
6. Mindestens 1 manueller Klick-Test pro Tab (API, Playwright, Trends).

---

## 8. Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|---|---|---|
| Closures auf `self.*` brechen bei Extraktion | **hoch** | mittel | Phase 5/6 schrittweise mit `git diff` + Smoke-Test nach jeder Methode |
| CustomTkinter-Widgets müssen `master` kennen | mittel | niedrig | `IWindowContext` als DI für shared widgets |
| PyInstaller findet neue Module nicht | mittel | hoch | `build.spec` anpassen (`collect_submodules('steam_review_tool')`), in Phase 8 verifizieren |
| Performance-Regression durch viele Imports | niedrig | niedrig | `__init__.py` lazy-loading + `python -X importtime` messen |
| Dataclass-Field-Rename bricht Persistenz | mittel | hoch | Settings/Resume mit `field(default=...)` + Migrations-Helper ab Phase 6 |
| AI-Agent passt veraltete Datei an, weil es die alte Struktur "kennt" | mittel | mittel | Nach Phase 4 alte Monolith-Datei löschen, nur Package-Struktur im Repo |

---

## 9. Geschätzter Aufwand (zur Orientierung, nicht als Zeitangabe für den User)

| Phase | Umfang |
|---|---|
| 0 — Vorbereitung | klein |
| 1 — Konstanten/Utils/Interfaces | klein |
| 2 — Services | mittel |
| 3 — Exporter & Models | klein |
| 4 — UI-Primitive | mittel |
| 5 — Tab-Controller | groß (größter Brocken) |
| 6 — Workflow-Controller | groß |
| 7 — Playwright-JS | klein |
| 8 — Cleanup | klein |

**Reihenfolge:** strikt 0 → 8, **keine Phase überspringen**. Phase 5+6 können in mehrere kleine Commits zerlegt werden (1 Methode pro Commit), wenn das Team das bevorzugt.

---

## 10. Out-of-Scope (bewusst nicht enthalten)

- **Keine** Verhaltensänderungen (kein neues Feature, keine UX-Änderung).
- **Keine** Framework-Migration (CustomTkinter bleibt).
- **Keine** Python-3.13+/PEP-725-Profile-Migration — das ist ein eigenes Projekt.
- **Keine** Internationalisierung der UI-Strings.
- **Keine** Änderung am `PLAYWRIGHT_SCRAPER_SCRIPT` (außer Auslagerung, Phase 7).

---

**Status:** Plan bereit zur Freigabe. Nach Freigabe startet **Phase 0** mit Snapshot + Smoke-Test.