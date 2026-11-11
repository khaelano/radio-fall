"""Inference architectures for the notebook's tinygrad phase checkpoints.

Training remains in the notebook; keep these definitions compatible with its
saved parameter names. These models predict collection phases, not falls.
"""

from tinygrad import Tensor, nn
from ..analysis.window_data import LABELS


class CNNModel:
    def __init__(self, features, hidden):
        self.conv1 = nn.Conv1d(features, hidden, 5, padding=2)
        self.conv2 = nn.Conv1d(hidden, hidden, 3, padding=1)
        self.head = nn.Linear(hidden, len(LABELS))

    def __call__(self, x):
        x = self.conv1(x.transpose(1, 2)).relu()
        return self.head(self.conv2(x).relu().mean(axis=2))


class LSTMModel:
    def __init__(self, features, hidden):
        self.encoder = nn.LSTMCell(features, hidden)
        self.head = nn.Linear(hidden, len(LABELS))

    def __call__(self, x):
        state = None
        for t in range(x.shape[1]):
            state = self.encoder(x[:, t, :], state)
        return self.head(state[0])


class GRUModel:
    def __init__(self, features, hidden):
        self.input_gates = nn.Linear(features, 3 * hidden)
        self.hidden_gates = nn.Linear(hidden, 3 * hidden)
        self.head = nn.Linear(hidden, len(LABELS))
        self.hidden_size = hidden

    def __call__(self, x):
        h = Tensor.zeros(x.shape[0], self.hidden_size, device=x.device)
        for t in range(x.shape[1]):
            ir, iz, inn = self.input_gates(x[:, t, :]).chunk(3, dim=1)
            hr, hz, hn = self.hidden_gates(h).chunk(3, dim=1)
            reset, update = (ir + hr).sigmoid(), (iz + hz).sigmoid()
            candidate = (inn + reset * hn).tanh()
            h = (1 - update) * candidate + update * h
        return self.head(h)
