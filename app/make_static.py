"""Build app/data.js and a single-file app/factory-static.html (CSS, JS and recorded evidence inlined).
three.js and GSAP still load from CDN. Usage: python app/make_static.py"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from taskfactory import appdata  # noqa: E402

data = appdata.build(HERE.parent / "tasks")
js = "window.FACTORY_DATA=" + json.dumps(data, separators=(",", ":")) + ";\n"
(HERE / "data.js").write_text(js)

html = (HERE / "index.html").read_text()
html = html.replace('<link rel="stylesheet" href="style.css">', "<style>\n" + (HERE / "style.css").read_text() + "\n</style>")
html = re.sub(r'<script src="data.js"></script>', lambda m: "<script>" + js.replace("</", "<\\/") + "</script>", html)
html = re.sub(r'<script type="module" src="app.js"></script>',
              lambda m: '<script type="module">\n' + (HERE / "app.js").read_text().replace("</script", "<\\/script") + "\n</script>", html)
html = re.sub(r'<script[^>]*src="custom-interactions.js"[^>]*></script>',
              lambda m: "<script>\n" + (HERE / "custom-interactions.js").read_text() + "\n</script>", html)
(HERE / "factory-static.html").write_text(html)
print(f"wrote data.js and factory-static.html ({len(html)//1024} KB, {len(data['tasks'])} tasks)")
