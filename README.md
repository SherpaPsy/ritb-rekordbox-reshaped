# 🎶 RITB Rekordbox Reshaped

A Python-based tool to parse your AlphaTheta Rekordbox database and populate an organized Microsoft Access database of your DJ sets, tracks, artists, and labels.

## ✨ Features
- Easy-to-use **CustomTkinter GUI** setup.
- Automatically pulls your Rekordbox track data.
- Creates a structured sqlite database with tables for:
  - Sets
  - Tracks
  - Artists
  - Labels
- Supports optional cover artwork for sets and tracks.
- Clean, shareable, and extensible project.

---

## 📦 Project Setup

This project uses [Poetry](https://python-poetry.org/) for dependency management.

### 1️⃣ Install Poetry (if not already installed):

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Confirm installation:

```bash
poetry --version
```

---

### 2️⃣ Install Dependencies:

In the root directory of the project:

```bash
poetry install
```

> **Note:** The project is configured in **dependency-only mode**—no packaging setup is required.

---

### 3️⃣ Run Initial GUI Setup:

```bash
poetry run python setup_gui.py
```

This will:
- Prompt for your DJ name.
- Let you select:
  - Your Rekordbox database file.
  - The folder to save the generated Access `.accdb` database.
  - An optional default cover image.
- Save your configuration securely in the `secrets/` folder (excluded from version control).

---

## 🗂️ Project Structure

```
ritb-rekordbox-to-access/
├── assets/                  # Optional: Contains default logo image
├── secrets/                 # Stores personal config (ignored in Git)
├── setup_gui.py             # CustomTkinter GUI setup script
├── pyproject.toml           # Poetry config
├── README.md                # This file!
└── .gitignore
```

---

## 📚 Future Enhancements
- Parsing and importing track artwork.
- Rekordbox database parsing to auto-populate Access tables.
- Command-line interface option.

---

## 🤝 Contributions

Feel free to fork, open PRs, or suggest features!

---

## 📝 License

[MIT License](LICENSE)
