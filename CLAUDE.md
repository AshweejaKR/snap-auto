# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

`snap-auto` is a new, empty repository intended for Snapchat automation (see README.md). No source code, dependencies, build tooling, or tests exist yet — only `README.md`, `LICENSE`, `.gitattributes`, and a Python-oriented `.gitignore`.

The `.gitignore` indicates the project is expected to be Python-based, but no `pyproject.toml`, `requirements.txt`, `setup.py`, or package layout has been created yet.

## Working in this repo

Since there is no established structure, build system, or test suite:

- Before adding code, check with the user for their preferred Python packaging/dependency approach (e.g. `uv`, `poetry`, `pip` + `requirements.txt`) if it isn't already obvious from new files they've added.
- Once real source files, configs, or tests are added, update this CLAUDE.md with actual build/lint/test commands and architecture notes — do not leave this placeholder stale.
