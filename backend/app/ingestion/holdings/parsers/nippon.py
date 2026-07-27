"""
Nippon India Mutual Fund holdings parser.

Nippon publishes ONE consolidated workbook per month for all schemes:
  https://mf.nipponindiaim.com/InvestorServices/FactsheetsDocuments/
      NIMF-MONTHLY-PORTFOLIO-<DD-Mon-YY>.xls
It's actually a modern .xlsx served under a .xls name (base.open_workbook reads it
by content), with ~108 sheets — an "Index" plus one per fund. Each fund sheet is the
standard SEBI template, though ISIN sits before Name — the label-based column map in
base.parse_standard_sheet handles that automatically.
"""
import calendar
import datetime

import httpx

from .. import base

AMC_NAME = "Nippon India Mutual Fund"     # must equal scheme_master.amc
AMC_SLUG = "nippon"
BASE = ("https://mf.nipponindiaim.com/InvestorServices/FactsheetsDocuments/"
        "NIMF-MONTHLY-PORTFOLIO-{tag}.xls")


def _month_ends(n=3):
    """Last day of each of the last n completed months, newest first."""
    d = datetime.date.today().replace(day=1)
    for _ in range(n):
        d = d - datetime.timedelta(days=1)          # last day of previous month
        yield d
        d = d.replace(day=1)


def discover():
    """The most recent month's consolidated file that exists."""
    for me in _month_ends():
        tag = me.strftime("%d-%b-%y")               # e.g. 30-Jun-26
        url = BASE.format(tag=tag)
        try:
            r = httpx.get(url, headers={"User-Agent": base.UA}, timeout=60.0,
                          follow_redirects=True)
        except httpx.HTTPError:
            continue
        if r.status_code == 200 and len(r.content) > 10000:
            return [{"filename": f"NIMF_{me.year}_{me.month:02d}.xls", "url": url}]
    return []
