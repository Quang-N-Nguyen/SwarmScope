"""Build the SwarmScope platform (the in-browser workbench) into platform/build/.

    python platform/build_platform.py

Needs npm (to fetch Pyodide 0.26.4, Python compiled to WebAssembly). The result is a
static folder: open it through any web server, or publish it as a hosted page.
  - engine/swarmscope_bundle.json   the swarmscope package + webrun.py
  - engine/sample_log.txt           synthetic sample log (platform/make_sample.py)
  - pyodide/                        Pyodide runtime; the stdlib zip is shipped as base64 text
  - outputs/*/swarmscope_*.html     the six analysed viewers
"""
import base64, glob, json, os, shutil, subprocess, tarfile, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "platform")
OUT = os.path.join(HERE, "build")
PYODIDE = "0.26.4"


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "engine"))
    os.makedirs(os.path.join(OUT, "pyodide"))
    os.chdir(ROOT)
    files = sorted(glob.glob("swarmscope/**/*.py", recursive=True)) + ["swarmscope/viz/template.html", "swarmscope/viz/world.html", "swarmscope/viz/d3.min.js"]
    bundle = {p: open(p).read() for p in files}
    bundle["webrun.py"] = open(os.path.join(HERE, "webrun.py")).read()
    json.dump(bundle, open(os.path.join(OUT, "engine", "swarmscope_bundle.json"), "w"))
    shutil.copy(os.path.join(HERE, "sample_log.jsonl"), os.path.join(OUT, "engine", "sample_log.txt"))
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["npm", "pack", f"pyodide@{PYODIDE}"], cwd=tmp, check=True, capture_output=True)
        with tarfile.open(os.path.join(tmp, f"pyodide-{PYODIDE}.tgz")) as t:
            try:
                t.extractall(tmp, filter="data")
            except TypeError:  # Python without tar filters
                t.extractall(tmp)
        pkg = os.path.join(tmp, "package")
        for f in ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "pyodide-lock.json"):
            shutil.copy(os.path.join(pkg, f), os.path.join(OUT, "pyodide", f))
        with open(os.path.join(pkg, "python_stdlib.zip"), "rb") as f:
            open(os.path.join(OUT, "pyodide", "python_stdlib.b64.txt"), "w").write(base64.b64encode(f.read()).decode())
    for v in glob.glob("outputs/*/swarmscope_*.html"):
        dst = os.path.join(OUT, v)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(v, dst)
    shutil.copy(os.path.join(HERE, "index.html"), os.path.join(OUT, "index.html"))
    print("built", OUT)


if __name__ == "__main__":
    main()
