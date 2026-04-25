# Archive Studio for Mac 1.0

**Archive Studio for Mac** is a community macOS adaptation of **Archive Studio**, originally developed by **Mark Humphries** and **Lianne C. Leddy**.

It is a desktop tool for historians, archivists, and researchers who want to use AI models to transcribe, correct, translate, and export historical documents from images or PDFs.

The app is designed for a local-first workflow: your projects, images, transcriptions, translations, task history, and exports are stored on your own computer.

---

## Status

This is an experimental community build for macOS.

It is intended for researchers who are comfortable testing an early tool and checking AI outputs critically. The app can be useful for historical transcription workflows, but it should not be treated as a fully validated archival production system.

---

## Relationship to the original Archive Studio

This project is based on the original **Archive Studio** codebase by Mark Humphries and Lianne C. Leddy.

The original project was developed as a Windows-oriented desktop application for AI-assisted archival transcription and analysis. This version adapts the concept for macOS and adds or emphasizes a more focused workflow around:

- macOS desktop use
- local project folders
- AI transcription and correction
- translation as a workflow step
- export to TXT, Markdown, CSV, JSON, and JSONL
- API key storage through macOS Keychain
- a simpler project-based workflow for document transcription

This repository should be understood as **Archive Studio for Mac: a community adaptation**, not as the official main Archive Studio project.

Original project:  
https://github.com/mhumphries2323/Archive_Studio

---

## What the app does

Archive Studio for Mac lets you:

- create a local project from images or PDFs
- view page images inside the app
- run AI transcription / OCR / HTR
- correct AI transcriptions against the page image
- translate corrected transcriptions
- edit text manually
- keep different text stages for each page
- export results as TXT, Markdown, CSV, JSON, or JSONL
- inspect logs when API calls or tasks fail

The basic workflow is:

1. Import a PDF or folder of page images.
2. Run transcription.
3. Review and correct the text.
4. Optionally translate it.
5. Export the results.
6. Archive or delete the working project folder when finished.

---

## Project folders

Each project is stored as a local working folder.

A project folder may contain:

```text
images/          copied page images
exports/         exported TXT / Markdown / CSV / JSON / JSONL files
task_runs/       task history and task-related data
project.db       SQLite project database
project.db-wal   SQLite write-ahead log file
project.db-shm   SQLite shared-memory file

This is intentional. A project is a workspace, not just a single text file.

Once you have exported the files you need, you can archive or delete the project folder. If you delete the project folder before exporting, you may lose the working data inside it.

Text stages

The app stores text in stages.

Typical stages include:

Original — the first AI transcription/OCR/HTR result
Corrected — a corrected version checked against the image
Translated — a translation of the source text

The original transcription is not the same thing as a translation. Translation should be treated as a derived interpretation of the source transcription.

Each text version stores basic provenance, including which model created it and when.

Example:

Stage: original | By: ai:google:gemini-3.1-pro-preview | At: 2026-04-25 08:09
AI providers

The app can use API-based AI models from:

Google Gemini
OpenAI
Anthropic Claude

You need your own API key from the provider you want to use.

API use may cost money. Check the provider’s pricing and usage dashboard before processing large collections.

API key storage

On macOS, API keys entered through the app are stored in macOS Keychain.

The app settings file stores provider choices and model names, but not the API keys themselves.

Technical users can also provide keys with environment variables:

export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GOOGLE_API_KEY="..."
export GEMINI_API_KEY="..."

Credentials are loaded from macOS Keychain first, then from environment variables.

Recommended models

For historical handwriting and difficult archival images, recent Gemini Pro models have often performed very well in testing.

The current default can be changed in the app under:

Settings → Model Settings

You should experiment with different models on a small sample before running a large batch.

Export formats

The app supports export to:

TXT — plain text, useful for simple reading and reuse
Markdown — readable structured text, useful for Obsidian, GitHub, and note-taking workflows
CSV — tabular export for spreadsheet/database workflows
JSON — structured export
JSONL — one JSON object per line, useful for pipelines and later processing

TXT and Markdown are both included because they serve different purposes. TXT is the neutral plain-text format. Markdown is better when headings, page markers, lists, and readable structure matter.

Installation / development setup

This repository currently provides a Python source version and a local macOS launcher workflow.

Requirements:

macOS
Python 3.11 or newer
Git
API keys for AI features

Clone the repository:

git clone https://github.com/JonBangPloug/Archive_Studio_for_Mac.git
cd Archive_Studio_for_Mac

Create a virtual environment:

python3.11 -m venv .venv
source .venv/bin/activate

Install dependencies:

pip install -e ".[dev,ai]"

Run tests:

pytest

Launch the app:

python -m archivestudio
macOS clickable launcher

You can create a clickable local macOS launcher with:

source .venv/bin/activate
python scripts/build_macos_launcher.py

This creates a .app bundle in dist/.

Important: this launcher is a local convenience launcher, not a fully portable macOS release. It points to the current source checkout and virtual environment. If you move the project folder or delete the virtual environment, rebuild the launcher.

For wider distribution, the app should eventually be packaged with a real bundling tool such as PyInstaller, Briefcase, or py2app.

Logs and troubleshooting

The app writes logs to help diagnose problems such as:

wrong API key
missing billing or quota
rate limits
network errors
provider/model errors
prompt/template errors
application errors

If a task appears to be running slowly, check the log. Successful API calls may appear as repeated 200 OK responses.

Do not share logs publicly without checking that they do not contain private document text or local file paths you want to keep private.

Security notes
Do not commit API keys to GitHub.
Do not store keys in project folders.
API keys entered through the app are stored in macOS Keychain.
Local project folders may contain copied page images and transcriptions, so treat them as research data.
Limitations

This is an experimental research tool.

Current limitations may include:

AI output must be checked by the user
difficult handwriting may produce errors
translation is interpretive and should be reviewed
API calls require internet access
large batches may take time
the macOS launcher is currently local-machine oriented, not a notarized distributable app
Citation and attribution

This app is based on Archive Studio by Mark Humphries and Lianne C. Leddy.

If you use this Mac adaptation, please cite or acknowledge both the original Archive Studio project and this community Mac version where relevant.

Original Archive Studio citation:

Mark Humphries and Lianne C. Leddy, 2025. ArchiveStudio 1.0 Beta. Department of History: Wilfrid Laurier University.

Community Mac adaptation:

Jon Bang Ploug, Archive Studio for Mac, community macOS adaptation of Archive Studio.

License

This project follows the licensing terms of the original Archive Studio project.

License: Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)

You are free to share and adapt the material under the following terms:

Attribution — give appropriate credit and indicate if changes were made
NonCommercial — do not use the material for commercial purposes

License text:
https://creativecommons.org/licenses/by-nc/4.0/

Acknowledgments

Archive Studio for Mac builds on the original Archive Studio project by:

Mark Humphries
Lianne C. Leddy

The app uses AI models and APIs provided by:

OpenAI
Google Gemini
Anthropic Claude

