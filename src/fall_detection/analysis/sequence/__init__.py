"""Our sequence approach: aligned amplitude windows for the neural models.

``alignment`` puts receivers on a shared sequence grid and gives verified access
to sources and exports; ``transforms`` holds the difference transforms (the
current squared difference and its variants); ``segments``, ``cache`` and
``reporting`` write, checkpoint and preview the export; ``training_data`` and
``device_cache`` load it for training. Stage orchestration lives in
``notebooks/latest/02_preprocess.ipynb`` and ``03_training.ipynb``. Shared
amplitude kernels are in ``analysis.preprocessing``.
"""
