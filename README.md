# Radio fall detection

This repository develops a radio-based fall detector. The camera and radar
modules remain available for related-work and comparison experiments, but the
collection workflow uses direct USB CSI receivers and operator-confirmed
reference labels.

## Project structure

```text
src/
├── firmware/radio/             ESP32-C5/C6 transmitter and receiver
└── fall_detection/
    ├── contracts/              shared artifact contracts
    ├── radio/                  CSI acquisition and processing
    ├── vision/                 camera comparator and proposed labeler
    ├── collection/             synchronized recording orchestration
    └── evaluation/             event matching and detector comparison
configs/                        versioned runtime and experiment settings
data/                           raw, derived, annotation, and split artifacts
tests/                          tests arranged by research module
notebooks/                      exploratory analysis only
docs/                           procedures, notes, and figures
draft/                          thesis drafts
```

Raw radio and camera formats remain modality-specific. The shared seam is the
session, annotation, and prediction artifacts exchanged after acquisition.
This keeps hardware details out of the comparison and evaluation code.

## Setup

Install the radio collection environment from the repository root:

```sh
uv sync --extra radio
```

Install both radio and vision dependencies when working on the comparator:

```sh
uv sync --extra radio --extra vision
```

Run the tests with:

```sh
uv run pytest -q
```

See [the radio module](src/fall_detection/radio/README.md) for CSI collection
commands and [the firmware module](src/firmware/radio/README.md) for ESP-IDF
build and flash instructions.

For guided collection, see [the collection module](src/fall_detection/collection/README.md).
It provides direct USB receiver discovery, profile-fingerprint readiness checks,
operator confirmation, and schema-2 per-receiver artifacts.
