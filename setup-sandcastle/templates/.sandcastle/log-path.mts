// The per-run log filename, split out of main.mts's logging() so the contract
// can be tested without running a sandbox. Sibling to log-retention.mts.
//
// This mirrors sandcastle's own default filename — <sanitized-branch>-<slugged-
// name>.log under the logs dir — so existing `tail -f` paths keep working. The
// two sanitizers are the contract: the branch loses filename-hostile characters,
// the name lowercases and slugs. Drift here silently breaks a human's tail path,
// which is why it earns a test. Host-coupled; keep it matching sandcastle's default.
export function logFilePath(
  name: string,
  branch: string,
  dir = ".sandcastle/logs"
): string {
  const sanitized = branch.replace(/[/\\:*?"<>|]/g, "-");
  const suffix = name.toLowerCase().replace(/[^a-z0-9_.-]/g, "-");
  return `${dir}/${sanitized}-${suffix}.log`;
}
