# Notebooks

Use numbered notebooks for exploratory analysis and experiments. Move reusable
preprocessing, modeling, and
evaluation logic into `src/fall_detection/` and test it under `tests/`.

`03_cnn_baseline/` contains the isolated, pinned within-session CNN pilot.
`trash/` contains the older exploration notebooks and two-receiver transport
simulation for manual review. Moving them changes relative paths; restore them
to their original locations before attempting a rerun. The pilot remains in
place because later four-receiver experiments depend on it.
