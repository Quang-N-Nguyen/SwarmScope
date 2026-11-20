"""Assemble the static website (project page + viewers + workbench) for GitHub Pages.

    python platform/build_platform.py      # first, if platform/build/ is missing
    python scripts/build_site.py [OUT]     # default OUT: site/

Layout of OUT:
    index.html                  project page (findings, links to every viewer)
    outputs/*/swarmscope_*.html the analysed viewers (graph + world map)
    platform/                   in-browser workbench (Pyodide); reuses ../outputs/
    .nojekyll                   serve files as-is (no Jekyll processing)

Only the viewer HTML files are copied from outputs/, not report.md or findings.json.
"""
import glob
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_ARTIFACT = "https://claude.ai/artifact/RTJ4QhFXtRV4EUxpDPfywZ"


def replace_once(text, old, new, where):
    if text.count(old) != 1:
        sys.exit(f"build_site: expected one '{old}' in {where}, found {text.count(old)}")
    return text.replace(old, new)


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site"))
    build = os.path.join(ROOT, "platform", "build")
    if not os.path.isdir(os.path.join(build, "pyodide")):
        sys.exit("build_site: platform/build/ is missing; run python platform/build_platform.py first")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)

    # Project page: add a link to the workbench next to Code / Paper.
    page = open(os.path.join(ROOT, "index.html")).read()
    code = '<a href="https://github.com/Quang-N-Nguyen/SwarmScope" target="_blank" rel="noopener">Code</a>'
    page = replace_once(page, code, '<a href="platform/">Workbench</a>\n      ' + code, "index.html")
    open(os.path.join(out, "index.html"), "w").write(page)

    # Viewers (one copy, shared by both pages).
    for v in sorted(glob.glob(os.path.join(ROOT, "outputs", "*", "swarmscope_*.html"))):
        rel = os.path.relpath(v, ROOT)
        os.makedirs(os.path.join(out, os.path.dirname(rel)), exist_ok=True)
        shutil.copy(v, os.path.join(out, rel))

    # Workbench: everything but its own outputs/ copy; point it at ../outputs/ and the project page.
    shutil.copytree(build, os.path.join(out, "platform"), ignore=shutil.ignore_patterns("outputs"))
    wb_path = os.path.join(out, "platform", "index.html")
    wb = open(wb_path).read()
    n = wb.count("f:'outputs/")
    if n == 0:
        sys.exit("build_site: no viewer links found in platform/index.html")
    wb = wb.replace("f:'outputs/", "f:'../outputs/")
    wb = replace_once(wb, f'<a href="{RESULTS_ARTIFACT}" target="_blank" rel="noopener">Results</a>',
                      '<a href="../">Results</a>', "platform/index.html")
    open(wb_path, "w").write(wb)

    open(os.path.join(out, ".nojekyll"), "w").close()
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out) for f in fs)
    print(f"site: {out} ({size / 1e6:.1f} MB, {n} workbench viewer links)")


if __name__ == "__main__":
    main()
