# Configuration

Keep versioned settings separate from implementations:

- `collection/` contains synchronized session and recording settings.
- `radio/` contains CSI acquisition and radio-model settings.
- `vision/` contains camera and vision-model settings.
- `experiments/` contains named evaluation conditions.

Do not place machine-specific paths, credentials, or participant identifiers
in committed configuration files.
