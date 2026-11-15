# Screenplay

A minimal, offline desktop word processor for **novels** and **screenplays**.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

## Features

- Novel and Screenplay writing modes
- Screenplay elements: Scene Heading, Action, Character, Dialogue, Parenthetical, Transition
- Tab cycles screenplay elements; Enter automatically selects the next element
- Character-name suggestions
- Save/open editable `.screenplay` documents
- Export US Letter PDF
- Basic formatting and Find

This is an initial implementation; PDF pagination and screenplay formatting require validation on macOS before distribution. No imported-script editing or scene rearranging is included.
