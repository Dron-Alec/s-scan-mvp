"""Failed scans must never score as clean. Run: python test_scoring.py"""
from unittest import mock

import app

err = {"critical": 0, "high": 0, "medium": 0, "low": 0, "findings_list": [], "error": "x"}
ok = {"critical": 0, "high": 0, "medium": 0, "low": 0, "findings_list": []}

with mock.patch.object(app, "run_slither", return_value=err), mock.patch.object(app, "run_goplus", return_value=err):
    assert app.compute_score(app.get_combined_analysis("0x0")) is None
with mock.patch.object(app, "run_slither", return_value=err), mock.patch.object(app, "run_goplus", return_value=ok):
    assert app.compute_score(app.get_combined_analysis("0x0")) == 100
assert app.compute_score({"critical": 1, "high": 1, "medium": 1}) == 55

import interface  # streamlit runs in bare mode; UI code is skipped without a button click

assert interface.compute_score({}, err, {}) is None
assert interface.compute_score({}, {"high": 2}, {}) == 70
pdf = interface.generate_pdf({
    "contract_address": "0x0", "final_score": None, "analysis_data": err,
    "age_data": {}, "tvl_data": {}, "tx_data": {},
})
assert pdf.startswith(b"%PDF")
print("ok")
