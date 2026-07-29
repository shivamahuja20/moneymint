"""
DSP Mutual Fund holdings parser.

DSP publishes a monthly .zip bundling two workbooks (debt, and equity/FoF), each
with one sheet per scheme on the SEBI template. base.iter_workbooks unpacks the
archive, so this parser only has to resolve the latest zip's URL — done via
advisorkhoj's index, since DSP's own download page is a JS app.

Note: DSP's written-off IL&FS side-pocket rows carry junk in the weight column;
base.py's median-based scale detection and per-row >100% drop handle those.
"""
from . import _advisorkhoj

AMC_NAME = "DSP Mutual Fund"        # must equal scheme_master.amc
AMC_SLUG = "dsp"
ADVISORKHOJ_SLUG = "DSP-Mutual-Fund"


def discover():
    files = _advisorkhoj.latest_files(ADVISORKHOJ_SLUG, exts=("zip",))
    if not files:
        return []
    d, url = files[0]
    return [{"filename": f"DSP_{d.year}_{d.month:02d}.zip", "url": url}]
