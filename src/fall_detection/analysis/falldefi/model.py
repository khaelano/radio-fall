"""FallDeFi detector: noise calibration, event detection and RBF SVM.

Each receiver's spectrogram is divided, bin by bin, by that receiver's median
resting spectrum from the training countdowns. The whitened spectrograms of
the receivers usable in a trace are then averaged. This replaces the paper's
plain average: the C5 receivers are separate radios with their own gain and
noise, and the resting spectrum falls to a third or half across 5–25 Hz.

The noise threshold is ``10 ** (mean + k * std)`` of log10 resting magnitudes,
taken as the median over training resting segments. The paper tunes ``k`` per
link so that weak energy around the event survives while noise is removed
(§5.2), and requires event detection to catch every human-induced event (§3).
Unless ``threshold_k`` is fixed, ``k`` is therefore the largest grid value at
which the requested share of training traces, all of them cued activities,
contains an event. This uses neither fall labels nor test data.

Training follows the released code's event labels: in a fall trace only the
main event (largest duration times maximum frequency) is a fall; its other
events and every event of a non-fall trace are non-falls. Traces without an
event do not train the classifier. Because falls are then outnumbered about
three to one, the SVM weights classes by inverse frequency and is selected by
balanced accuracy, in place of the paper's SMOTE oversampling. At prediction
time a trace is a fall when any of its events is classified as a fall, so a
fall without a detected event is a missed fall.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pywt
from sklearn.exceptions import NotFittedError
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.preprocessing import MinMaxScaler
from sklearn.svm import SVC

from .events import (
    FEATURE_NAMES,
    band_mask,
    detect_events,
    event_features,
    log_noise_statistics,
    main_event,
    main_region,
    power_burst_curve,
)
from .signal import Spectrogram, receiver_spectrogram


@dataclass(frozen=True)
class FallDeFiConfig:
    """Signal, event and classifier settings.

    Defaults adapt the paper and its released code to the C5 receivers at
    120 Hz; docs/falldefi.md explains each choice. The sample rate describes
    the data, not resampling.
    """

    sample_rate_hz: float = 120
    wavelet: str = "sym3"
    wavelet_levels: int = 1
    components: int = 3
    window_samples: int = 64
    hop_samples: int = 32
    fft_samples: int = 64
    noise_low_hz: float = 5.0
    noise_high_hz: float = 25.0
    threshold_k: float | None = None
    k_grid: tuple[float, ...] = tuple(round(0.1 * step, 1) for step in range(44))
    detection_target: float = 0.95
    pbc_low_hz: float = 5.0
    pbc_high_hz: float = 25.0
    merge_gap_seconds: float = 0.5
    svm_log2_c: tuple[int, ...] = tuple(range(-5, 16))
    svm_log2_gamma: tuple[int, ...] = tuple(range(-5, 16))
    class_weight: str | None = "balanced"
    scoring: str = "balanced_accuracy"
    cv_folds: int = 5
    random_seed: int = 42

    def __post_init__(self) -> None:
        for name in ("sample_rate_hz", "merge_gap_seconds"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in (
            "wavelet_levels",
            "components",
            "window_samples",
            "hop_samples",
            "fft_samples",
            "cv_folds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        nyquist = self.sample_rate_hz / 2
        if (
            not self.hop_samples <= self.window_samples <= self.fft_samples
            or self.cv_folds < 2
            or not 0 <= self.noise_low_hz < self.noise_high_hz <= nyquist
            or not 0 <= self.pbc_low_hz < self.pbc_high_hz <= nyquist
            or (
                self.threshold_k is not None
                and (not np.isfinite(self.threshold_k) or self.threshold_k < 0)
            )
            or not self.k_grid
            or not all(np.isfinite(k) and k >= 0 for k in self.k_grid)
            or not np.isfinite(self.detection_target)
            or not 0 < self.detection_target <= 1
            or self.wavelet not in pywt.wavelist(kind="discrete")
            or not self.svm_log2_c
            or not self.svm_log2_gamma
            or self.class_weight not in {None, "balanced"}
            or self.scoring not in {"accuracy", "balanced_accuracy", "f1"}
        ):
            raise ValueError(
                "Invalid STFT, folds, bands, wavelet, threshold or SVM settings"
            )

    @property
    def hop_seconds(self) -> float:
        """Return the time between spectrogram frames."""
        return self.hop_samples / self.sample_rate_hz


@dataclass(frozen=True)
class TraceAnalysis:
    """Intermediate results of one trace, for inspection and figures.

    Attributes:
        spectrogram: Whitened spectrogram averaged over usable receivers.
        region: Retained bins of the largest region above the noise threshold.
        power_burst: Power-burst curve per frame.
        events: Detected ``(start, stop)`` frame ranges.
        main_event: Index of the main event, or None.
        features: Selected features ``[event, feature]``.
    """

    spectrogram: Spectrogram
    region: np.ndarray
    power_burst: np.ndarray
    events: list[tuple[int, int]]
    main_event: int | None
    features: np.ndarray


class FallDeFiDetector:
    """Spectrogram events and an RBF SVM fitted on training data only.

    Args:
        config: Signal, event and classifier settings.
    """

    def __init__(self, config: FallDeFiConfig | None = None) -> None:
        self.config = config if config is not None else FallDeFiConfig()

    def receiver_spectrograms(self, trace: np.ndarray) -> list[Spectrogram | None]:
        """Return each receiver's spectrogram, or None for a dropped receiver.

        Args:
            trace: Amplitudes ``[time, receiver, tone]``; a dropped receiver is
                all NaN, any other must be finite and nonnegative.

        Returns:
            One spectrogram or None per receiver, in receiver order.
        """
        config = self.config
        values = np.asarray(trace, dtype=np.float64)
        if values.ndim != 3:
            raise ValueError("Traces must be [time, receiver, tone]")
        if hasattr(self, "input_shape_") and values.shape[1:] != self.input_shape_:
            raise ValueError("Trace receiver/tone schema differs from fitted data")
        spectra: list[Spectrogram | None] = []
        for receiver in np.moveaxis(values, 1, 0):
            if np.isnan(receiver).all():
                spectra.append(None)
                continue
            spectra.append(
                receiver_spectrogram(
                    receiver,
                    sample_rate_hz=config.sample_rate_hz,
                    wavelet=config.wavelet,
                    wavelet_levels=config.wavelet_levels,
                    components=config.components,
                    window_samples=config.window_samples,
                    hop_samples=config.hop_samples,
                    fft_samples=config.fft_samples,
                )
            )
        return spectra

    def _fuse(self, spectra: list[Spectrogram | None]) -> Spectrogram:
        whitened = [
            spectrum.magnitude / self.floors_[index]
            for index, spectrum in enumerate(spectra)
            if spectrum is not None and self.floors_[index] is not None
        ]
        if not whitened:
            raise ValueError("No receiver of this trace has a resting noise floor")
        reference = next(spectrum for spectrum in spectra if spectrum is not None)
        return Spectrogram(
            np.mean(whitened, axis=0), reference.frequencies_hz, reference.frame_seconds
        )

    def spectrogram(self, trace: np.ndarray) -> Spectrogram:
        """Return the whitened spectrogram averaged over usable receivers.

        Args:
            trace: Amplitudes ``[time, receiver, tone]`` with dropped receivers
                all NaN.

        Returns:
            The fused trace spectrogram, in multiples of the resting floor.
        """
        if not hasattr(self, "floors_"):
            raise NotFittedError("Fit FallDeFiDetector before analyzing traces")
        return self._fuse(self.receiver_spectrograms(trace))

    def _require_threshold(self) -> None:
        if not hasattr(self, "noise_threshold_"):
            raise NotFittedError("Fit FallDeFiDetector before analyzing traces")

    def _events(
        self, spectrogram: Spectrogram, threshold: float
    ) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int]]]:
        config = self.config
        frequencies = spectrogram.frequencies_hz
        band = band_mask(frequencies, config.pbc_low_hz, config.pbc_high_hz)
        region = main_region(spectrogram.magnitude, threshold, band)
        curve = power_burst_curve(
            spectrogram.magnitude,
            region,
            frequencies,
            low_hz=config.pbc_low_hz,
            high_hz=config.pbc_high_hz,
        )
        bins = int(band.sum())
        events = detect_events(
            curve,
            bins * threshold,
            hop_seconds=config.hop_seconds,
            merge_gap_seconds=config.merge_gap_seconds,
        )
        return region, curve, events

    def _analyze(self, spectrogram: Spectrogram, threshold: float) -> TraceAnalysis:
        region, curve, events = self._events(spectrogram, threshold)
        frequencies = spectrogram.frequencies_hz
        features = np.array(
            [
                event_features(
                    spectrogram.magnitude,
                    region,
                    frequencies,
                    event,
                    hop_seconds=self.config.hop_seconds,
                )
                for event in events
            ]
        ).reshape(len(events), len(FEATURE_NAMES))
        return TraceAnalysis(
            spectrogram,
            region,
            curve,
            events,
            main_event(events, region, frequencies),
            features,
        )

    def analyze(self, trace: np.ndarray) -> TraceAnalysis:
        """Segment one trace and extract features of every detected event.

        Args:
            trace: Finite nonnegative amplitudes ``[time, receiver, tone]``.

        Returns:
            Spectrogram, region, power-burst curve, events and features.
        """
        self._require_threshold()
        return self._analyze(self.spectrogram(trace), self.noise_threshold_)

    def fit(
        self, traces: list[np.ndarray], labels: np.ndarray, resting: list[np.ndarray]
    ) -> FallDeFiDetector:
        """Calibrate the noise threshold and fit the classifier on training data.

        Args:
            traces: Training traces ``[time, receiver, tone]``, possibly of
                different lengths.
            labels: Binary trace labels, with 1 denoting a fall.
            resting: Training-only resting segments for the noise threshold;
                the median of their per-segment thresholds is used (§7).
                Without a fixed ``threshold_k``, ``k`` is calibrated on the
                training traces as described in the module docstring.

        Returns:
            This fitted detector.

        Raises:
            ValueError: If inputs are inconsistent or too few events of either
                class remain for cross-validation.
        """
        # A failed refit must not leave an old classifier with a new threshold.
        for name in (
            "input_shape_",
            "floors_",
            "noise_threshold_",
            "threshold_k_",
            "training_detection_rate_",
            "resting_thresholds_",
            "scaler_",
            "classifier_",
            "search_",
            "training_events_",
        ):
            if hasattr(self, name):
                delattr(self, name)
        target = np.asarray(labels)
        if (
            not len(traces)
            or target.shape != (len(traces),)
            or not np.isin(target, [0, 1]).all()
        ):
            raise ValueError("labels must provide a binary target for every trace")
        if not resting:
            raise ValueError("At least one training resting segment is required")
        shapes = {np.shape(trace)[1:] for trace in [*traces, *resting]}
        if len(shapes) != 1:
            raise ValueError("Traces and resting segments must share one schema")
        config = self.config
        resting_spectra = [self.receiver_spectrograms(segment) for segment in resting]
        floors: list[np.ndarray | None] = []
        for index in range(shapes.pop()[0]):
            frames = [
                spectra[index].magnitude
                for spectra in resting_spectra
                if spectra[index] is not None
            ]
            floors.append(
                np.maximum(np.median(np.concatenate(frames), axis=0), 1e-12)
                if frames
                else None
            )
        self.floors_ = floors
        statistics = np.array(
            [
                log_noise_statistics(
                    spectrogram.magnitude,
                    spectrogram.frequencies_hz,
                    low_hz=config.noise_low_hz,
                    high_hz=config.noise_high_hz,
                )
                for spectrogram in map(self._fuse, resting_spectra)
            ]
        )

        def thresholds(k: float) -> np.ndarray:
            return 10 ** (statistics[:, 0] + k * statistics[:, 1])

        spectrograms = [self.spectrogram(trace) for trace in traces]

        def detection_rate(k: float) -> float:
            threshold = float(np.median(thresholds(k)))
            return float(
                np.mean([bool(self._events(s, threshold)[2]) for s in spectrograms])
            )

        if config.threshold_k is not None:
            k = config.threshold_k
        else:
            candidates = sorted(config.k_grid, reverse=True)
            k = next(
                (c for c in candidates if detection_rate(c) >= config.detection_target),
                candidates[-1],
            )
        self.threshold_k_ = float(k)
        self.resting_thresholds_ = thresholds(k)
        self.noise_threshold_ = float(np.median(self.resting_thresholds_))
        rows, event_labels, detected = [], [], []
        for spectrogram, label in zip(spectrograms, target, strict=True):
            analysis = self._analyze(spectrogram, self.noise_threshold_)
            detected.append(bool(analysis.events))
            for index, features in enumerate(analysis.features):
                rows.append(features)
                event_labels.append(int(label == 1 and index == analysis.main_event))
        self.training_detection_rate_ = float(np.mean(detected))
        y = np.asarray(event_labels, dtype=np.int64)
        counts = np.bincount(y, minlength=2)
        if counts.min() < self.config.cv_folds:
            raise ValueError(
                f"Need at least {self.config.cv_folds} training events per class; "
                f"found {counts.tolist()} (non-fall, fall)"
            )
        x = np.asarray(rows)
        self.scaler_ = MinMaxScaler().fit(x)
        self.search_ = GridSearchCV(
            SVC(kernel="rbf", class_weight=self.config.class_weight),
            {
                "C": [2.0**value for value in self.config.svm_log2_c],
                "gamma": [2.0**value for value in self.config.svm_log2_gamma],
            },
            scoring=self.config.scoring,
            cv=StratifiedKFold(
                self.config.cv_folds, shuffle=True, random_state=self.config.random_seed
            ),
            n_jobs=1,
        ).fit(self.scaler_.transform(x), y)
        self.classifier_ = self.search_.best_estimator_
        self.training_events_ = {"non_fall": int(counts[0]), "fall": int(counts[1])}
        self.input_shape_ = np.shape(traces[0])[1:]
        return self

    def classify(self, analysis: TraceAnalysis) -> np.ndarray:
        """Classify each event of an analysis.

        Args:
            analysis: Result of :meth:`analyze`.

        Returns:
            One binary label per event, with 1 denoting a fall.
        """
        if not hasattr(self, "classifier_"):
            raise NotFittedError("Fit FallDeFiDetector before classifying events")
        if not len(analysis.features):
            return np.zeros(0, dtype=np.int64)
        scaled = self.scaler_.transform(analysis.features)
        return self.classifier_.predict(scaled).astype(np.int64)

    def predict(self, traces: list[np.ndarray]) -> np.ndarray:
        """Return 1 for traces with at least one event classified as a fall.

        Args:
            traces: Traces ``[time, receiver, tone]`` with the fitted schema.

        Returns:
            One binary label per trace.
        """
        return np.array(
            [int(self.classify(self.analyze(trace)).any()) for trace in traces],
            dtype=np.int64,
        )
