"""Build the pages: plan page (template + scoring engine + data from the last run -> demo/index.html) and the submission page."""

from pathlib import Path

HERE = Path(__file__).parent

page = (HERE / "template.html").read_text()
engine = (HERE / "engine.js").read_text().replace('if (typeof module !== "undefined") module.exports = { compute };', "")
data = (HERE.parent / "output" / "demo_data.json").read_text()
page = page.replace("/*DATA*/null", data).replace("/*ENGINE*/", engine)
(HERE / "index.html").write_text(page)
print("Built demo/index.html")

# The submission page links to the local plan page, so the repo works without any outside link.
sub = HERE.parent / "submission"
(sub / "index.html").write_text((sub / "template.html").read_text().replace("__PLAN_URL__", "../demo/index.html"))
print("Built submission/index.html")
