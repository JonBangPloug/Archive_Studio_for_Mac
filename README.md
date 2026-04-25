# Archive Studio for Mac

**Archive Studio for Mac** is a community macOS adaptation of **Archive Studio**, originally developed by **Mark Humphries** and **Lianne C. Leddy**.

This desktop tool is designed for historians, archivists, and researchers who want to use AI models to transcribe, correct, translate, and export historical documents from images or PDFs.

> **Status: Experimental Community Build**
> This app is intended for researchers comfortable testing an early tool and critically evaluating AI outputs. While useful for historical transcription workflows, it should not be treated as a fully validated archival production system.

---

## Core Features

Archive Studio for Mac is designed for a **local-first workflow**: your projects, images, transcriptions, translations, task history, and exports are stored on your own computer.

* Create local projects from images or PDFs.
* View page images directly inside the app.
* Run AI transcription / OCR / HTR.
* Correct AI transcriptions side-by-side with the page image.
* Translate corrected transcriptions.
* Edit text manually and track different text stages for each page.
* Inspect detailed logs for failed API calls or tasks.

### The Basic Workflow

1. Import a PDF or folder of page images.
2. Run the AI transcription.
3. Review and correct the text.
4. Optionally translate the corrected text.
5. Export the results.
6. Archive or delete the working project folder when finished.

---

## Project Structure and Text Stages

### Project Folders
Each project is stored as a local working folder. A project is a workspace, not just a single text file. Once you have exported the files you need, you can archive or delete the project folder. **Warning:** If you delete the project folder before exporting, you will lose the working data inside it.

A typical project folder structure looks like this:

```text
project-name/
├── images/            # copied page images
├── exports/           # exported TXT / Markdown / CSV / JSON / JSONL files
├── task_runs/         # task history and task-related data
├── project.db         # SQLite project database
├── project.db-wal     # SQLite write-ahead log file
└── project.db-shm     # SQLite shared-memory file
```

### Text Stages
The app stores text in stages. Each text version stores basic provenance, including the model used and timestamp. The original transcription is distinct from a translation; translation is treated as a derived interpretation.

* **Original:** The first AI transcription/OCR/HTR result.
* **Corrected:** A corrected version checked against the source image.
* **Translated:** A translation of the source text.

*Example Provenance:*
`Stage: original | By: ai:google:gemini-3.1-pro-preview | At: 2026-04-25 08:09`

---

## AI Models and API Keys

The app utilizes API-based AI models from **Google Gemini**, **OpenAI**, and **Anthropic Claude**. 
*For historical handwriting and difficult archival images, recent Gemini Pro models have performed very well in testing. You can change your default model under **Settings → Model Settings**.*

### API Key Storage
You must provide your own API keys. **Note:** API use incurs costs; check your provider’s pricing dashboard before processing large collections.

* Keys entered through the app are securely stored in the **macOS Keychain**.
* The app settings file stores provider choices and model names, but **never** the keys themselves.

Technical users can alternatively provide keys via environment variables (loaded as a fallback if not in Keychain):

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GOOGLE_API_KEY="..."
export GEMINI_API_KEY="..."
```

---

## Export Formats

| Format | Description & Best Use Case |
| :--- | :--- |
| **TXT** | Neutral plain-text format. Best for simple reading and general reuse. |
| **Markdown** | Readable structured text. Ideal for Obsidian, GitHub, and note-taking workflows where headings, page markers, and lists matter. |
| **CSV** | Tabular export. Perfect for spreadsheet and database workflows. |
| **JSON** | Structured data export. |
| **JSONL** | One JSON object per line. Useful for automated pipelines and later processing. |

---

## Installation & Development Setup

This repository provides a Python source version and a local macOS launcher workflow.

**Requirements:**
* macOS
* Python 3.11 or newer
* Git
* API keys for AI features

### Setup Instructions

1. **Clone the repository:**
```bash
git clone [https://github.com/JonBangPloug/Archive_Studio_for_Mac.git](https://github.com/JonBangPloug/Archive_Studio_for_Mac.git)
cd Archive_Studio_for_Mac
```

2. **Create and activate a virtual environment:**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

3. **Install dependencies:**
```bash
pip install -e ".[dev,ai]"
```

4. **Run tests:**
```bash
pytest
```

5. **Launch the app:**
```bash
python -m archivestudio
```

### macOS Clickable Launcher
You can create a clickable local macOS `.app` bundle (output to `dist/`) with:

```bash
source .venv/bin/activate
python scripts/build_macos_launcher.py
```
*Note: This is a convenience launcher tied to your current source checkout and virtual environment. It is not a fully portable macOS release. Rebuild it if you move the project folder or delete the virtual environment.*

---

## Security, Logs & Troubleshooting

**Security Best Practices:**
* **Never** commit API keys to GitHub or store them in project folders.
* Treat local project folders as sensitive research data, as they contain copied images and transcriptions.

**Troubleshooting:**
The app writes logs to help diagnose issues like network errors, missing quotas, rate limits, or prompt failures. If a task is slow, check the logs. Successful API calls often appear as repeated `200 OK` responses. 
*Do not share logs publicly without verifying they are free of private document text or local file paths.*

---

## About & Credits

### Relationship to the Original Archive Studio
This project is based on the [original Archive Studio](https://github.com/mhumphries2323/Archive_Studio) codebase developed for Windows by Mark Humphries and Lianne C. Leddy. This community version adapts the concept for macOS, emphasizing local project folders, targeted export formats, and Keychain API storage.

### Citation and Attribution
If you use this adaptation, please acknowledge both projects:
* **Original:** Mark Humphries and Lianne C. Leddy, 2025. *ArchiveStudio 1.0 Beta*. Department of History: Wilfrid Laurier University.
* **Mac Adaptation:** Jon Bang Ploug. *Archive Studio for Mac*, a community macOS adaptation.

### License
This project follows the original licensing terms: **[Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/)**. 
You are free to share and adapt the material provided you give appropriate credit and do not use the material for commercial purposes.
```
