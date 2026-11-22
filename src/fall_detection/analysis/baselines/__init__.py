"""Classical baselines adapted from prior Wi-Fi fall-detection research.

Each subpackage adapts one paper to the ESP32-C5 receivers and runs as a
command (``python -m fall_detection.analysis.baselines.<name>``). The private
modules hold what the baselines share: reading labelled attempts
(``_recorded_attempts``) and grouped evaluation (``_grouped_holdout``). Our own
sequence approach lives in ``analysis.sequence``.
"""
