"""`lmd_driver.mjs` posts a puzzle to LMD: what a fake LMD receives, and what the driver reads back.

This is #1659's end-to-end test: it drives the driver, the half of the skill that posts, through every
acceptance criterion it carries, and `bash tests/all.sh` runs it. WSL `node` runs the driver against a
headless Chromium, as Windows `node.exe` runs it against the stream browser in real use. Chromium loads a
fake LMD: the saved copies of the real upload and submit forms (`fixtures/`, #1660), served by a local
HTTP server that records every request and form it gets and answers with pages carrying the ids. Each
field the driver must set starts in the fake's forms at the value it must not send, so a field the
driver leaves alone shows in what the fake receives. Chromium is Playwright's headless shell, found in
Playwright's browser cache under the user's home directory as `node` is found on PATH: a tool the
machine has, read and never written. With none found the suite fails rather than skips, so a green run
always drove a browser.

Blind to: LMD changing its markup after the fixtures were saved, the real stream browser (Windows
`node.exe`, port 9334, the rig's profile) and its LMD login.
"""
import base64
import email.parser
import email.policy
import hashlib
import json
import pwd
import os
import re
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


def _swap(html, old, new):
    """`html` with its one `old` replaced by `new`; a fixture that lost `old` fails here, not in a test."""
    assert html.count(old) == 1, (old, html.count(old))
    return html.replace(old, new)


# The saved forms, with each field the driver must set started at the value it must not send: "others may
# use" checked, German text present, a timed activation chosen.
UPLOAD_PAGE = _swap((HERE / "fixtures" / "lmd-upload.html").read_text(encoding="utf-8"),
                    '<input type="checkbox" name="offen">', '<input type="checkbox" name="offen" checked>')
SUBMIT_PAGE = (HERE / "fixtures" / "lmd-submit.html").read_text(encoding="utf-8")
for _old, _new in [
    ('<textarea name="htmlcode" cols="60" rows="15"></textarea>', '<textarea name="htmlcode" cols="60" rows="15">Rätsel</textarea>'),
    ('<textarea name="codedescr" cols="60" rows="5"></textarea>', '<textarea name="codedescr" cols="60" rows="5">Zeile 5</textarea>'),
    ('<option value="ja">Yes, on:</option>\n<option value="nein" selected="">No</option>',
     '<option value="ja" selected="">Yes, on:</option>\n<option value="nein">No</option>'),
]:
    SUBMIT_PAGE = _swap(SUBMIT_PAGE, _old, _new)
# A form check of the kind LMD may run: it stops the submit with an alert, which blocks the page's script.
ALERT_TEXT = "Bitte einen Namen eingeben."
ALERT_PAGE = _swap(SUBMIT_PAGE, "</body>", f"""<script>
document.querySelector('input[name=einstellen]').form.addEventListener('submit', (e) => {{
  e.preventDefault(); alert({json.dumps(ALERT_TEXT)}); }});
</script></body>""")
UPLOAD_PATH = "/Dateien/"
UPLOAD_POST = "/Dateien/index.php"
SUBMIT_PATH = "/Raetselportal/Eigene/einstellen.php"
PUZZLE_PATH = "/Raetselportal/Raetsel/zeigen.php"
OWN_PUZZLES_PATH = "/Raetselportal/Eigene/"
LOGIN_PAGE = """<!doctype html><html><body><h1>Login</h1>
<form action="?" method="POST"><input type="text" name="name"><input type="password" name="pwd">
<input type="hidden" name="hiddenaction" value="login"><input type="submit" name="login" value="Anmelden">
</form></body></html>"""
NEW_IMAGE_ID = "0100XY"
NEW_PUZZLE_ID = "000QRS"
FORM_ERROR = "Please enter a name for the puzzle."
UPLOAD_ERROR = "Die Datei ist zu groß."
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


UPLOAD_FORM = re.compile(r'<form class="upload".*?</form>', re.S)
assert len(UPLOAD_FORM.findall(UPLOAD_PAGE)) == 1


def _upload_page(rows, form=True):
    """The upload fixture with `rows` (newest first, `(id, name)`) above its two made-up entries; without
    its upload form when `form` is false, as live LMD serves /Dateien/ right after an upload (#1659's
    closing check, Check-In: the reload showed only the file list)."""
    html = "".join(
        f'<tr><td><a href="/Dateien/index.php?id={i}">img</a></td><td>'
        f'<span class="upload_list_gross_name"><a href="/Dateien/index.php?id={i}">{n}</a></span><br>'
        f'<span class="upload_list_gross_id">ID: {i}</span><br></td></tr>'
        for i, n in rows
    )
    page = UPLOAD_PAGE if form else UPLOAD_FORM.sub("", UPLOAD_PAGE)
    return page.replace('<table class="upload_list_gross">\n<tbody>', '<table class="upload_list_gross">\n<tbody>' + html, 1)


class FakeLmd:
    """The fake LMD's state: what it was sent, and how it answers (set per test)."""

    def __init__(self):
        self.requests = []  # (method, path) for every request
        self.uploads = []  # each a dict of field -> str, or bytes for the file
        self.submits = []  # each a dict of field -> list of str
        self.rows = []  # uploaded files, newest first, (id, name)
        self.upload_mode = "ok"  # ok | noid | login | nolist (the page after the upload has no file list)
        self.submit_mode = "ok"  # ok | error | noid | elsewhere | alert | login


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
                if lmd.upload_mode == "login":
                    return self._send(LOGIN_PAGE)
                if lmd.uploads and lmd.upload_mode == "nolist":
                    return self._send("<!doctype html><html><body><p>Wartungsarbeiten.</p></body></html>")
                return self._send(_upload_page(lmd.rows, form=not lmd.uploads))
            if path == SUBMIT_PATH:
                return self._send({"login": LOGIN_PAGE, "alert": ALERT_PAGE}.get(lmd.submit_mode, SUBMIT_PAGE))
            if path == OWN_PUZZLES_PATH:
                return self._send("<!doctype html><html><body><h1>Your puzzles</h1></body></html>")
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
                    return self._send(_upload_page(lmd.rows, form=False))
                return self._send(f"<!doctype html><html><body><p class='fehler'>{UPLOAD_ERROR}</p></body></html>")
            if path == SUBMIT_PATH:
                lmd.submits.append(urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True))
                if lmd.submit_mode == "ok":
                    return self._send("", 302, [("Location", f"{PUZZLE_PATH}?id={NEW_PUZZLE_ID}")])
                if lmd.submit_mode == "elsewhere":
                    # an id on a page that is not the puzzle's: not the landing "Create" leads to
                    return self._send("", 302, [("Location", f"{OWN_PUZZLES_PATH}?id={NEW_PUZZLE_ID}")])
                if lmd.submit_mode == "error":
                    return self._send(f"<!doctype html><html><body><p class='fehler'>{FORM_ERROR}</p></body></html>")
                return self._send("<!doctype html><html><body><p>Thanks.</p></body></html>")
            return self._send("not found", 404)

    return Handler


def _chromium():
    """The newest Playwright headless shell. The home directory comes from the user's account, not from
    HOME, so the lookup does not turn on what the shell exports."""
    cache = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache" / "ms-playwright"
    found = sorted(glob(str(cache / "chromium_headless_shell-*" / "chrome-headless-shell-linux64" / "chrome-headless-shell")))
    if not found:
        pytest.fail(f"no headless Chromium under {cache}: install Playwright's chromium_headless_shell")
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


def run_driver(endpoint, lmd, tmp_path, values=None, template=TEMPLATE, png=PNG, timeout_ms=15000, extra=()):
    (tmp_path / "board.png").write_bytes(png)
    (tmp_path / "page.html").write_text(template, encoding="utf-8")
    (tmp_path / "values.json").write_text(json.dumps(values if values is not None else VALUES), encoding="utf-8")
    return subprocess.run(
        ["node", str(DRIVER), "--endpoint", endpoint, "--base-url", lmd.base, "--png", str(tmp_path / "board.png"),
         "--template", str(tmp_path / "page.html"), "--values", str(tmp_path / "values.json"), "--timeout-ms", str(timeout_ms), *extra],
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


def _assert_refused(result, *needles, posted=None):
    """`posted`: the {"uploaded", "image_id", "submitted"} record a failure once an image is on LMD prints on
    stdout; None, none."""
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    if posted is None:
        assert result.stdout == ""
    else:
        record = json.loads(result.stdout)
        assert {k: record[k] for k in ("uploaded", "image_id", "submitted")} == posted
        assert record["failed"] in result.stderr
    for needle in needles:
        assert needle in result.stderr, result.stderr


def test_a_form_error_page_after_create_exits_with_its_text(endpoint, lmd, tmp_path):
    lmd.submit_mode = "error"
    _assert_refused(run_driver(endpoint, lmd, tmp_path), 'no puzzle id after "Create"', FORM_ERROR,
                    posted={"uploaded": True, "image_id": NEW_IMAGE_ID, "submitted": True})


def test_no_puzzle_id_after_create_exits_non_zero(endpoint, lmd, tmp_path):
    lmd.submit_mode = "noid"
    _assert_refused(run_driver(endpoint, lmd, tmp_path), 'no puzzle id after "Create"', "Thanks.",
                    posted={"uploaded": True, "image_id": NEW_IMAGE_ID, "submitted": True})


@pytest.mark.parametrize("page", ["upload", "submit"])
def test_a_login_page_exits_before_anything_is_sent(endpoint, lmd, tmp_path, page):
    setattr(lmd, f"{page}_mode", "login")
    _assert_refused(run_driver(endpoint, lmd, tmp_path), "login page", "not logged in",
                    posted=None if page == "upload" else {"uploaded": True, "image_id": NEW_IMAGE_ID, "submitted": False})
    assert lmd.submits == []
    assert len(lmd.uploads) == (0 if page == "upload" else 1)


def test_no_new_image_id_after_upload_exits_before_the_submit(endpoint, lmd, tmp_path):
    lmd.upload_mode = "noid"
    lmd.rows = [("0099ZZ", "test-puzzle")]  # an earlier upload under the same name is not this one
    _assert_refused(run_driver(endpoint, lmd, tmp_path), 'no new image named "test-puzzle"', UPLOAD_ERROR,
                    posted={"uploaded": True, "image_id": None, "submitted": False})
    assert len(lmd.uploads) == 1
    assert not any(p.startswith(SUBMIT_PATH) for _, p in lmd.requests)


def test_a_failure_after_the_upload_post_records_the_upload(endpoint, lmd, tmp_path):
    # The POST went out, so an image may be on LMD with no id read: the record says so, or a rerun uploads twice.
    lmd.upload_mode = "nolist"
    _assert_refused(run_driver(endpoint, lmd, tmp_path), "upload list", "Wartungsarbeiten.",
                    posted={"uploaded": True, "image_id": None, "submitted": False})
    assert len(lmd.uploads) == 1 and lmd.submits == []


def test_image_id_reuses_an_uploaded_image_and_uploads_nothing(endpoint, lmd, tmp_path):
    result = run_driver(endpoint, lmd, tmp_path, extra=("--image-id", "001626"))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert (out["image_id"], out["puzzle_id"]) == ("001626", NEW_PUZZLE_ID)
    [submit] = lmd.submits
    assert '<img:001626 width="420">' in submit["htmlcode_en"][0]
    assert lmd.uploads == [] and not any(p.startswith(UPLOAD_PATH) for _, p in lmd.requests)


def test_a_failure_with_a_reused_image_records_it(endpoint, lmd, tmp_path):
    lmd.submit_mode = "error"
    _assert_refused(run_driver(endpoint, lmd, tmp_path, extra=("--image-id", "001626")), FORM_ERROR,
                    posted={"uploaded": False, "image_id": "001626", "submitted": True})


@pytest.mark.parametrize("bad", ["", "00 16", "<img:1>"])
def test_a_malformed_image_id_is_a_usage_error(endpoint, lmd, tmp_path, bad):
    result = run_driver(endpoint, lmd, tmp_path, extra=("--image-id", bad))
    assert result.returncode == 2 and "--image-id" in result.stderr, result.stderr
    assert lmd.requests == []


def test_a_code_with_characters_lmd_strips_exits_before_any_upload(endpoint, lmd, tmp_path):
    _assert_refused(run_driver(endpoint, lmd, tmp_path, values={**VALUES, "code": "12_3.4"}), "would strip", '"_."')
    assert lmd.requests == []


def test_no_cdp_endpoint_exits_non_zero(lmd, tmp_path):
    _assert_refused(run_driver("http://127.0.0.1:9", lmd, tmp_path), "no CDP endpoint at http://127.0.0.1:9")


@pytest.mark.parametrize("mode", ["ok", "error", "alert"])
def test_the_driver_closes_its_tab(endpoint, lmd, tmp_path, mode):
    lmd.submit_mode = mode
    run_driver(endpoint, lmd, tmp_path)
    with urllib.request.urlopen(f"{endpoint}/json/list") as r:
        urls = [t["url"] for t in json.load(r)]
    assert lmd.requests and not [u for u in urls if u.startswith(lmd.base)]


def test_the_driver_imports_only_node_builtins():
    imports = re.findall(r'^import .* from "([^"]+)";', DRIVER.read_text(encoding="utf-8"), re.M)
    assert imports and all(m.startswith("node:") for m in imports), imports


def test_sudoku_nein_is_the_choice_sent(endpoint, lmd, tmp_path):
    result = run_driver(endpoint, lmd, tmp_path, values={**VALUES, "sudoku": "Nein"})
    assert result.returncode == 0, result.stderr
    [submit] = lmd.submits
    assert submit["Sudoku_JaNein"] == ["Nein"]


def test_an_id_on_a_page_other_than_the_puzzles_is_a_refusal(endpoint, lmd, tmp_path):
    lmd.submit_mode = "elsewhere"
    _assert_refused(run_driver(endpoint, lmd, tmp_path), 'no puzzle id after "Create"', "Your puzzles",
                    posted={"uploaded": True, "image_id": NEW_IMAGE_ID, "submitted": True})


def test_an_alert_on_the_page_is_dismissed_and_is_a_refusal(endpoint, lmd, tmp_path):
    lmd.submit_mode = "alert"
    _assert_refused(run_driver(endpoint, lmd, tmp_path), "alert dialog, dismissed unanswered", ALERT_TEXT)
    assert lmd.submits == []


@pytest.mark.parametrize(
    "values, template, png, message",
    [
        (VALUES, TEMPLATE, PNG + bytes(4194304 - len(PNG) + 1), "over LMD's upload limit of 4194304"),
        (VALUES, "<p>No image.</p>", PNG, "no {{IMAGE_ID}} placeholder"),
        ({**VALUES, "difficulty": 0}, TEMPLATE, PNG, "values.difficulty must be 1-5, got 0"),
        ({**VALUES, "difficulty": 6}, TEMPLATE, PNG, "values.difficulty must be 1-5, got 6"),
        *[({k: v for k, v in VALUES.items() if k != key}, TEMPLATE, PNG, f'the values file has no "{key}"')
          for key in ("sudoku", "labels", "freetags")],
    ],
    ids=["png-over-4MiB", "no-placeholder", "difficulty-0", "difficulty-6", "no-sudoku", "no-labels", "no-freetags"],
)
def test_bad_inputs_exit_before_any_request(endpoint, lmd, tmp_path, values, template, png, message):
    _assert_refused(run_driver(endpoint, lmd, tmp_path, values=values, template=template, png=png), message)
    assert lmd.requests == []


def test_a_label_the_form_lacks_exits_before_the_submit(endpoint, lmd, tmp_path):
    _assert_refused(run_driver(endpoint, lmd, tmp_path, values={**VALUES, "labels": [3, 999]}), "no label 999",
                    posted={"uploaded": True, "image_id": NEW_IMAGE_ID, "submitted": False})
    assert lmd.submits == []


class FakeCdp:
    """A CDP endpoint that hands out one tab and then stalls: the websocket handshake never completes
    (`handshake`), or it completes and no command is ever answered (`commands`); or /json/new answers
    with a body that is not JSON (`notjson`)."""

    def __init__(self, mode):
        self.mode = mode
        self.requests = []


def _cdp_handler(cdp):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _hold(self):
            """Keep the connection open, saying nothing, until the driver hangs up."""
            while self.rfile.read(1):
                pass

        def do_PUT(self):
            """/json/new: the one tab."""
            cdp.requests.append(urllib.parse.urlsplit(self.path).path)
            port = self.server.server_port
            body = (b"<html>not a tab</html>" if cdp.mode == "notjson" else json.dumps(
                {"id": "T1", "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/T1"}).encode())
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            cdp.requests.append(path)
            if path == "/devtools/page/T1":
                if cdp.mode == "commands":
                    accept = base64.b64encode(hashlib.sha1(
                        (self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
                    self.wfile.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                                     b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
                    self.wfile.flush()
                return self._hold()
            self.send_response(200)  # /json/close/<id>
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


@pytest.mark.parametrize("mode, message", [
    ("handshake", "did not open within 1000 ms"),
    ("commands", "CDP Page.enable got no answer within 1000 ms"),
    ("notjson", "answered with a body that is not JSON: <html>not a tab</html>"),
])
def test_a_stalled_or_garbled_cdp_endpoint_exits_and_closes_the_tab(lmd, tmp_path, mode, message):
    cdp = FakeCdp(mode)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _cdp_handler(cdp))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        started = time.monotonic()
        result = run_driver(f"http://127.0.0.1:{server.server_port}", lmd, tmp_path, timeout_ms=1000)
        _assert_refused(result, message)
        assert time.monotonic() - started < 10  # the 1 s deadline held, not run_driver's 60 s kill
        assert ("/json/close/T1" in cdp.requests) == (mode != "notjson")
    finally:
        server.shutdown()
        server.server_close()
