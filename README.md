# Archive Studio for Mac
<img width="100" height="100" alt="Archive Studio for Mac 1 0 Logo" src="https://github.com/user-attachments/assets/109898bc-c304-4154-94ee-e3a8c73c2fea" />

# Archive Studio for Mac 1.1

**Archive Studio for Mac** is a community macOS adaptation inspired by the original **Archive Studio** project developed by **Mark Humphries** and **Lianne C. Leddy**.

This desktop tool is designed for historians, archivists, and researchers who want to use AI models to transcribe, correct, translate, and export historical documents from images or PDFs.

---

## Core Features

Archive Studio for Mac is designed for a **local-first workflow**: your projects, images, transcriptions, translations, task history, and exports are stored entirely on your own computer.

* Create local projects from images or PDFs.
* View page images directly inside the app.
* Run AI transcription / OCR / HTR.
* Correct AI transcriptions side-by-side with the page image.
* Translate corrected or original transcriptions.
* Edit text manually and track different text stages for each page.
* Inspect detailed logs for failed API calls or tasks.

### The Basic Workflow

1. Import a PDF or folder of page images.
2. Run the AI transcription.
3. Review and correct the text.
4. Optionally translate the text.
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
`Stage: original | By: ai:google:gemini-2.5-pro | At: 2026-04-25 08:09`

---

## AI Models and API Keys

The app utilizes API-based AI models from **Google Gemini**, **OpenAI**, and **Anthropic Claude**. 
*For historical handwriting and difficult archival images, recent Gemini Pro models have performed very well in testing. You can change your default model in the app under **Settings → Model...***

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
git clone https://github.com/JonBangPloug/Archive_Studio_for_Mac.git
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

## 🛠️ Maintenance & Feedback

As this project is a "machine under construction," your feedback is the fuel that keeps it running.

* **Found a mechanical failure?** Please [Open an Issue](link-to-your-repo/issues) with a description of the bug.
* **Have an idea for a new feature?** Start a thread in [Discussions](link-to-your-repo/discussions).

---

## About & Credits

### Relationship to the Original Archive Studio
This project is a community macOS adaptation inspired by the original [Archive Studio](https://github.com/mhumphries2323/Archive_Studio) project developed for Windows by Mark Humphries and Lianne C. Leddy. This new app was built as a fresh PySide6/SQLite app, emphasizing local project folders, targeted export formats, and Keychain API storage on macOS.

### Citation and Attribution
If you use this adaptation, please acknowledge both projects where relevant:
* **Original:** Mark Humphries and Lianne C. Leddy, 2025. *ArchiveStudio 1.0 Beta*. Department of History: Wilfrid Laurier University.
* **Mac Adaptation:** Jon Bang Ploug. *Archive Studio for Mac*, a community macOS adaptation.

### License
This project is licensed under the **MIT License** (see the `LICENSE` file for full details).
