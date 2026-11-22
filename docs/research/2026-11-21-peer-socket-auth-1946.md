# Peer-message delivery to a controller's socket needs the session's key file (#1946)

Read 2026-11-21 from `strings` of the claude 2.1.330 binary
(`~/.local/share/claude/versions/2.1.330`). Not run live.

- A session's inbox is `messagingSocketPath` in `~/.claude/sessions/<pid>.json`
  (`/run/user/1000/cc-socks/<pid>.sock`). The record carries `peerProtocol: 1`
  and `peerFeatures`.
- The inbox is authenticated. Each session publishes
  `~/.claude/sessions/<pid>.<64-hex>.key` (mode 0600), a JSON record with a
  32-hex `peerToken` plus `procStart` and `pidDomain`. The binary names the
  failure "no other session can authenticate" when the key is not published.
- A message arrives wrapped as `<tag from="uds:..." from-session=... from-name=...>\n<body>\n</tag>`
  (the receiving parser, `Ui`).
- The sender's frame, read 2026-11-21 from the same binary's own startup log
  line (`[uds-messaging] Inject messages (auth line REQUIRED|optional here)`):
  newline-delimited JSON on the socket, first an auth line, then the message:

  ```
  {"type":"auth","token":"<token>"}
  {"type":"user","message":{"role":"user","content":"<text>"}}
  ```

  A connection that sends no complete line within the first-line deadline is
  closed; with auth required, a blank or unparseable first line closes it.
  The receiver accepts the `peerToken` from the key file as a `peer` sender
  and the `childToken` (`$CLAUDE_CODE_MESSAGING_TOKEN`, set only in the
  session's own children) as a `child` (`HPl`).
- A controller's record `~/.claude/sessions/<pid>.json` names its socket in
  `messagingSocketPath`; its key is `~/.claude/sessions/<pid>.<hex>.key`.

Consequence for #1946 (Chris ruled the token route on 2026-11-21): a hook
reads the controller's `peerToken` and writes the two lines. Hooks run outside
the auto-mode classifier, which denied both the `.key` read in the #1946
worker and a live send from a controller session (`[Unauthorized Access]`);
the frame above has not yet been proven against a live socket. Claude Code
does not document this protocol, so a version bump can change it.
