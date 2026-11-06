"""`lmd_driver.mjs` posts a puzzle to LMD: what a fake LMD receives, and what the driver reads back.

WSL `node` runs the driver against a headless Chromium, as Windows `node.exe` runs it against the stream
browser in real use. Chromium loads a fake LMD: the saved copies of the real upload and submit forms
(`fixtures/`, #1660), served by a local HTTP server that records every request and form it gets and
answers with pages carrying the ids. Chromium is Playwright's headless shell under
`~/.cache/ms-playwright` (or `LMD_TEST_CHROMIUM`); with none found the suite fails rather than skips, so a
green run always drove a browser.
"""
import email.parser
import email.policy
import json
import re
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from glob import glob
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "lmd_driver.mjs"
UPLOAD_PAGE = (HERE / "fixtures" / "lmd-upload.html").read_text(encoding="utf-8")
SUBMIT_PAGE = (HERE / "fixtures" / "lmd-submit.html").read_text(encoding="utf-8")
UPLOAD_PATH = "/Dateien/"
UPLOAD_POST = "/Dateien/index.php"
SUBMIT_PATH = "/Raetselportal/Eigene/einstellen.php"
PUZZLE_PATH = "/Raetselportal/Raetsel/zeigen.php"
LOGIN_PAGE = """<!doctype html><html><body><h1>Login</h1>
<form action="?" method="POST"><input type="text" name="name"><input type="password" name="pwd">
<input type="hidden" name="hiddenaction" value="login"><input type="submit" name="login" value="Anmelden">
</form></body></html>"""
NEW_IMAGE_ID = "0100XY"
NEW_PUZZLE_ID = "000QRS"
FORM_ERROR = "Please enter a name for the puzzle."
# A one-pixel PNG: the bytes the recorded upload must carry.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cfc0f01f0005fe02fea7d6a4"
    "5d0000000049454e44ae426082"
)
TEMPLATE = '<p>Rules here.</p>\n<a href="https://sudokupad.app/x"><img:{{IMAGE_ID}} width="420"></a>\n'
VALUES = {
    "slug": "test-puzzle",
    "title": "Test Puzzle",
    "code": "123456789",
    "difficulty": 4,
    "sudoku": "Ja",
    "labels": [3, 25],
    "freetags": "Killer (Variant), Arrows (Variant)",
    "codedescr_en": "Row 5, left to right.",
}
GERMAN_TEXT = ("htmlcode", "codedescr")
DATE_FIELDS = ("day", "month", "year", "hour", "min", "sec")


def _upload_page(rows):
    """The upload fixture with `rows` (newest first, `(id, name)`) above its two made-up entries."""
    html = "".join(
        f'<tr><td><a href="/Dateien/index.php?id={i}">img</a></td><td>'
        f'<span class="upload_list_gross_name"><a href="/Dateien/index.php?id={i}">{n}</a></span><br>'
        f'<span class="upload_list_gross_id">ID: {i}</span><br></td></tr>'
        for i, n in rows
    )
    return UPLOAD_PAGE.replace('<table class="upload_list_gross">\n<tbody>', '<table class="upload_list_gross">\n<tbody>' + html, 1)


class FakeLmd:
    """The fake LMD's state: what it was sent, and how it answers (set per test)."""

    def __init__(self):
        self.requests = []  # (method, path) for every request
        self.uploads = []  # each a dict of field -> str, or bytes for the file
        self.submits = []  # each a dict of field -> list of str
        self.rows = []  # uploaded files, newest first, (id, name)
        self.upload_mode = "ok"  # ok | noid | login
        self.submit_mode = "ok"  # ok | error | noid | login


def _handler(lmd):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body, status=200, headers=()):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            lmd.requests.append(("GET", self.path))
            if path in (UPLOAD_PATH, UPLOAD_POST):
                return self._send(LOGIN_PAGE if lmd.upload_mode == "login" else _upload_page(lmd.rows))
            if path == SUBMIT_PATH:
                return self._send(LOGIN_PAGE if lmd.submit_mode == "login" else SUBMIT_PAGE)
            if path == PUZZLE_PATH:
                return self._send("<!doctype html><html><body><h1>Test Puzzle</h1><a href='?aktivieren=1'>Aktivieren</a></body></html>")
            return self._send("not found", 404)

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            lmd.requests.append(("POST", self.path))
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if path == UPLOAD_POST:
                msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                    b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body
                )
                fields = {}
                for part in msg.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    payload = part.get_payload(decode=True)
                    fields[name] = payload if part.get_filename() else payload.decode("utf-8")
                lmd.uploads.append(fields)
                if lmd.upload_mode == "ok":
                    lmd.rows.insert(0, (NEW_IMAGE_ID, fields.get("name", "")))
                return self._send(_upload_page(lmd.rows))
            if path == SUBMIT_PATH:
                lmd.submits.append(urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True))
                if lmd.submit_mode == "ok":
                    return self._send("", 302, [("Location", f"{PUZZLE_PATH}?id={NEW_PUZZLE_ID}")])
                if lmd.submit_mode == "error":
                    return self._send(f"<!doctype html><html><body><p class='fehler'>{FORM_ERROR}</p></body></html>")
                return self._send("<!doctype html><html><body><p>Thanks.</p></body></html>")
            return self._send("not found", 404)

    return Handler


def _chromium():
    path = os.environ.get("LMD_TEST_CHROMIUM")
    if path:
        return path
    found = sorted(glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")))
    if not found:
        pytest.fail("no headless Chromium: set LMD_TEST_CHROMIUM or install Playwright's chromium_headless_shell")
    return found[-1]


@pytest.fixture(scope="module")
def endpoint():
    """One headless Chromium for the module; its CDP endpoint. It resolves no host but loopback, so the
    fixtures' jQuery links fail fast instead of reaching the network."""
    profile = tempfile.mkdtemp(prefix="lmd-driver-chromium-")
    proc = subprocess.Popen(
        [_chromium(), "--remote-debugging-port=0", f"--user-data-dir={profile}", "--no-sandbox",
         # basic: no Linux secret store, whose D-Bus activation opens a keyring dialog on the WSLg desktop.
         "--no-first-run", "--password-store=basic", "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    port_file = Path(profile) / "DevToolsActivePort"
    deadline = time.monotonic() + 20
    while not (port_file.exists() and port_file.read_text().strip()):
        if time.monotonic() > deadline or proc.poll() is not None:
            proc.kill()
            pytest.fail("headless Chromium did not open its debug port within 20s")
        time.sleep(0.1)
    port = port_file.read_text().split()[0]
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(10)
    shutil.rmtree(profile, ignore_errors=True)


@pytest.fixture
def lmd():
    state = FakeLmd()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.base = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()


def run_driver(endpoint, lmd, tmp_path, values=None, template=TEMPLATE, png=PNG):
    (tmp_path / "board.png").write_bytes(png)
    (tmp_path / "page.html").write_text(template, encoding="utf-8")
    (tmp_path / "values.json").write_text(json.dumps(values if values is not None else VALUES), encoding="utf-8")
    return subprocess.run(
        ["node", str(DRIVER), "--endpoint", endpoint, "--base-url", lmd.base, "--png", str(tmp_path / "board.png"),
         "--template", str(tmp_path / "page.html"), "--values", str(tmp_path / "values.json"), "--timeout-ms", "15000"],
        capture_output=True, text=True, timeout=60,
    )


def test_upload_carries_the_png_author_created_and_the_unchecked_box(endpoint, lmd, tmp_path):
    result = run_driver(endpoint, lmd, tmp_path)
    assert result.returncode == 0, result.stderr
    [upload] = lmd.uploads
    assert upload["datei"] == PNG
    assert upload["anmerkung"] == "author created"
    assert upload["name"] == "test-puzzle"
    assert "offen" not in upload


def test_submit_fills_english_fields_only_with_the_values_given(endpoint, lmd, tmp_path):
    result = run_driver(endpoint, lmd, tmp_path)
    assert result.returncode == 0, result.stderr
    [submit] = lmd.submits
    one = {k: v[0] for k, v in submit.items() if len(v) == 1}
    assert one["htmlcode_en"] == TEMPLATE.replace("{{IMAGE_ID}}", NEW_IMAGE_ID).replace("\n", "\r\n")
    assert one["codedescr_en"] == "Row 5, left to right."
    assert [one[k] for k in GERMAN_TEXT] == ["", ""]
    assert one["frei"] == "nein"
    assert [one[k] for k in DATE_FIELDS] == [""] * 6
    assert (one["name"], one["code"], one["dif"], one["Sudoku_JaNein"]) == ("Test Puzzle", "123456789", "4", "Ja")
    assert sorted(k for k in submit if k.startswith("label_")) == ["label_25", "label_3"]
    assert one["freetags"] == "Killer (Variant), Arrows (Variant)"
    assert one["einstellen"] == "Create"


def test_prints_the_ids_lmd_issued_and_the_page_html_and_never_activates(endpoint, lmd, tmp_path):
    result = run_driver(endpoint, lmd, tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert (out["image_id"], out["puzzle_id"]) == (NEW_IMAGE_ID, NEW_PUZZLE_ID)
    assert f'<img:{NEW_IMAGE_ID} width="420">' in out["html"]
    assert not any("aktiv" in p.lower() for _, p in lmd.requests)


def _assert_refused(result, *needles):
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stdout == ""
    for needle in needles:
        assert needle in result.stderr, result.stderr


def test_a_form_error_page_after_create_exits_with_its_text(endpoint, lmd, tmp_path):
    lmd.submit_mode = "error"
    _assert_refused(run_driver(endpoint, lmd, tmp_path), 'no puzzle id after "Create"', FORM_ERROR)


def test_no_puzzle_id_after_create_exits_non_zero(endpoint, lmd, tmp_path):
    lmd.submit_mode = "noid"
    _assert_refused(run_driver(endpoint, lmd, tmp_path), 'no puzzle id after "Create"', "Thanks.")


@pytest.mark.parametrize("page", ["upload", "submit"])
def test_a_login_page_exits_before_anything_is_sent(endpoint, lmd, tmp_path, page):
    setattr(lmd, f"{page}_mode", "login")
    _assert_refused(run_driver(endpoint, lmd, tmp_path), "login page", "not logged in")
    assert lmd.submits == []
    assert len(lmd.uploads) == (0 if page == "upload" else 1)


def test_no_new_image_id_after_upload_exits_before_the_submit(endpoint, lmd, tmp_path):
    lmd.upload_mode = "noid"
    lmd.rows = [("0099ZZ", "test-puzzle")]  # an earlier upload under the same name is not this one
    _assert_refused(run_driver(endpoint, lmd, tmp_path), 'no new image named "test-puzzle"')
    assert len(lmd.uploads) == 1
    assert not any(p.startswith(SUBMIT_PATH) for _, p in lmd.requests)


def test_a_code_with_characters_lmd_strips_exits_before_any_upload(endpoint, lmd, tmp_path):
    _assert_refused(run_driver(endpoint, lmd, tmp_path, values={**VALUES, "code": "12_3.4"}), "would strip", '"_."')
    assert lmd.requests == []


def test_no_cdp_endpoint_exits_non_zero(lmd, tmp_path):
    _assert_refused(run_driver("http://127.0.0.1:9", lmd, tmp_path), "no CDP endpoint at http://127.0.0.1:9")


@pytest.mark.parametrize("mode", ["ok", "error"])
def test_the_driver_closes_its_tab(endpoint, lmd, tmp_path, mode):
    lmd.submit_mode = mode
    run_driver(endpoint, lmd, tmp_path)
    with urllib.request.urlopen(f"{endpoint}/json/list") as r:
        urls = [t["url"] for t in json.load(r)]
    assert lmd.requests and not [u for u in urls if u.startswith(lmd.base)]


def test_the_driver_imports_only_node_builtins():
    imports = re.findall(r'^import .* from "([^"]+)";', DRIVER.read_text(encoding="utf-8"), re.M)
    assert imports and all(m.startswith("node:") for m in imports), imports
