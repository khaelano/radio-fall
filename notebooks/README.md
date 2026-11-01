# Notebooks

Use numbered notebooks for exploratory analysis and experiments, for example
`01_data_exploration.ipynb`. Move reusable preprocessing, modeling, and
evaluation logic into `src/fall_detection/` and test it under `tests/`.

`03_cnn_baseline/` contains the isolated, pinned within-session CNN pilot.
`04_transport_simulation/` reuses that environment and decoder for packet-level
transport replay, training-cohort EDA, explicit missingness preprocessing, and
clean versus missingness-trained model comparisons. Its executed notebook and
report distinguish the two real CSI views from four-slot virtual traffic.
