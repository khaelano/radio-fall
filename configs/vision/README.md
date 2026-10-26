# Vision configuration

Place camera capture, comparator, and proposed-labeler settings here.

The default `rule_based_fall.toml` also contains a `[scenario_completion]`
table. It validates the expected activity transition for the active collection
trial (for example, walking → seated) and reports evidence coverage rather
than a calibrated confidence score. Thresholds are intended for pilot
calibration from recorded pose sequences.
