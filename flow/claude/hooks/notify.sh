#!/bin/bash
# Away-notifier (Notification hook).
#
# Agent view is a pull surface: nothing in it reaches out, so the only way to
# learn that a background session is blocked is to go and look at it. That
# trains staring at the dashboard. This hook pushes instead — one Windows
# toast per notification — so agent view can stay closed.
#
# Claude Code raises its own desktop notification only in Ghostty, Kitty and
# iTerm2. This is WSL2, so the toast goes out through powershell.exe on the
# Windows side. No daemon, no external service, nothing leaves the machine.
#
# Which events arrive here is the matcher's job, not this script's: it toasts
# whatever Notification payload it is handed. See the "Notification" entry in
# ~/.claude/settings.json for the current matcher.
#
# Never exits nonzero and never blocks: a notifier that breaks the session is
# worse than a missed toast.
set -uo pipefail

PS=${NOTIFY_PS:-powershell.exe}
command -v "$PS" >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)
# Payload shape (from the CLI's own hook schema): hook_event_name, message,
# title (optional), notification_type. It is flat — there is no nested object.
msg=$(printf '%s' "$INPUT" | jq -r '.message // .notification_type // "needs you"' 2>/dev/null)
dir=$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
[ -n "${msg:-}" ] || msg="needs you"

# The payload's cwd is the session that raised the notification, not the
# background job it is about, so it names the same project every time. The job
# is named in the message instead: the CLI builds "<label> finished",
# "<label> failed" and "<label> needs your input: <detail>". Split there, so
# the toast's first line says which job and what happened to it.
where="Claude Code"
[ -n "${dir:-}" ] && where="Claude Code · $(basename "$dir")"

case "$msg" in
  *" needs your input: "*)
    title="${msg%% needs your input: *} needs you"
    msg="${msg#* needs your input: }" ;;
  *" needs your input")
    title="${msg% needs your input} needs you"
    msg="$where" ;;
  *" finished" | *" failed")
    title="$msg"
    msg="$where" ;;
  *)
    title="$where" ;;
esac

# A toast shows two short lines and nothing more, so flatten and bound the text.
title=$(printf '%s' "$title" | tr '\n\r\t' '   ' | cut -c1-70)
msg=$(printf '%s' "$msg" | tr '\n\r\t' '   ' | cut -c1-180)

# PowerShell single-quoted literals escape a quote by doubling it.
psq() { printf '%s' "${1//\'/\'\'}"; }

timeout 20 "$PS" -NoProfile -Command - <<PSCRIPT >/dev/null 2>&1
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
\$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
\$n = \$t.GetElementsByTagName('text')
\$n.Item(0).AppendChild(\$t.CreateTextNode('$(psq "$title")')) | Out-Null
\$n.Item(1).AppendChild(\$t.CreateTextNode('$(psq "$msg")')) | Out-Null
\$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(\$app).Show([Windows.UI.Notifications.ToastNotification]::new(\$t))
PSCRIPT

exit 0
