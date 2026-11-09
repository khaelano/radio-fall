"""Offscreen check of the live phase score table."""

import os
import subprocess
import sys

import pytest


def test_multi_model_phase_scores_are_visible():
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    script = "import os\nos.environ['QT_QPA_PLATFORM']='offscreen'\nfrom types import SimpleNamespace\nfrom PySide6 import QtCore, QtWidgets\nfrom fall_detection.detection import app\nimport fall_detection.radio.visualization.transport_status as transport\n\napplication=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])\nclass Panel:\n def __init__(self): self.widget=QtWidgets.QLabel('Synthetic transport')\n def apply(self,*args,**kwargs): pass\ntransport.GatewayStatusPanel=Panel\nphase=SimpleNamespace(receivers={'a':'rx-1','b':'rx-2','c':'rx-3','d':'rx-4'}, status=lambda **kwargs:{'models':[{'receiver':'rx-1','duration_seconds':2,'model':'cnn','probabilities':{'preparation':.1,'action':.8,'resting':.1},'coverage':.95}],'failure':'','dropped':0})\nengine=SimpleNamespace(phase_engine=phase,bundle=SimpleNamespace(metadata={'threshold':.5,'receivers':['rx-1','rx-2','rx-3','rx-4']}),status=lambda:dict(prediction=None,quality=None,failure='',native=dict(kernel='test',pending=0,overflow=0),skipped_inference=0))\nradio=SimpleNamespace(manager=SimpleNamespace(preflight_ready=True,failure=None,diagnostics=lambda:None))\nseen=[]\ndef inspect():\n for widget in application.allWidgets():\n  if isinstance(widget,QtWidgets.QTableWidget) and widget.columnCount()==7:\n   seen.append((widget.rowCount(),widget.item(0,4).text(),widget.item(0,6).text(), [w.text() for w in application.allWidgets() if isinstance(w,QtWidgets.QLabel) and (\"Stopped\" in w.text() or \"phase scores\" in w.text())]))\nQtCore.QTimer.singleShot(1200,inspect)\nstatus=app._gui(SimpleNamespace(duration=2.0),radio,engine,lambda:[])\nassert status == 0 and len(seen) == 1 and seen[0][:3] == (48, '0.800', '95.0%'), (status, seen)\nprint('GUI rows and phase score:',seen)\n"
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
