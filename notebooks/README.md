# Notebooks

Use numbered notebooks for exploratory analysis and experiments. Move reusable
preprocessing, modeling, and
evaluation logic into `src/fall_detection/` and test it under `tests/`.

`shared_cnn/` contains the shared four-receiver helpers and pinned CPU environment.
`trash/` contains the older exploration notebooks, two-receiver CNN pilot and transport
simulation for manual review. Moving them changes relative paths; restore them
to their original locations before attempting a rerun.
