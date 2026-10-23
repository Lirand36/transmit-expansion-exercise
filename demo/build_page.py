"""Build the pages: plan page (template + data from the last run -> demo/index.html) and the submission page."""

from pathlib import Path

HERE = Path(__file__).parent

page = (HERE / "template.html").read_text()
data = (HERE.parent / "output" / "demo_data.json").read_text()
page = page.replace("/*DATA*/null", data)
(HERE / "index.html").write_text(page)
print("Built demo/index.html")

# The submission page links to the local plan page, so the repo works without any outside link.
sub = HERE.parent / "submission"
(sub / "index.html").write_text((sub / "template.html").read_text().replace("__PLAN_URL__", "../demo/index.html"))
print("Built submission/index.html")
