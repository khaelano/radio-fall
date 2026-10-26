# Data layout

Each raw session should have a stable identifier and contain a manifest plus
separate modality recordings. Raw recordings are immutable.

```text
data/
├── raw/<session-id>/
│   ├── manifest.json
│   ├── radio/
│   └── camera/
├── interim/                    extracted frames, windows, and features
├── annotations/                proposed and manually verified labels
├── processed/                  model-ready dataset versions
├── splits/                     train, validation, and test assignments
└── experiments/                engineering experiment outputs
```

Camera-generated labels must retain their model name, model version,
confidence, and review status. Store them as proposed labels until they have
been manually verified.
