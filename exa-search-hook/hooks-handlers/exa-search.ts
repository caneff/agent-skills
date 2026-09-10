import type { Register } from "claude-code";
// Experimental function hooks (need CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1). Both fail-open:
// if the replacement errors, the hook is skipped and the built-in tool runs.
export const register: Register = (on, options) => {
  // WebSearch -> exa MCP search. The exa result has to be reshaped into WebSearch's
  // own output schema ({ query, results, durationSeconds, searchCount }) — returning
  // exa's result as-is fails the engine's output-shape check and errors the call.
  on("tool.call", { tool: "WebSearch" }, async ($, e, next) => {
    const started = Date.now();
    const { query } = e as any;
    const out: any = await $.tool.call({
      tool: "mcp__exa__web_search_exa", query, numResults: 5,
    });
    // $.tool.call may answer with a string, or with { text } / { result }.
    const text = typeof out === "string" ? out
      : typeof out?.text === "string" && out.text ? out.text
      : typeof out?.result === "string" ? out.result
      : JSON.stringify(out?.result ?? out);
    if (!text) throw new Error("exa returned nothing");
    // WebSearch's results array takes hit objects or plain text commentary; exa's
    // prose block goes in as commentary so the whole payload survives.
    return {
      result: {
        query,
        results: [text],
        durationSeconds: (Date.now() - started) / 1000,
        searchCount: 1,
      },
      text: "",
    };
  });

  // WebFetch -> local crawl4ai container (docker: crawl4ai, port 11235), readability-fit markdown
  on("tool.call", { tool: "WebFetch" }, async ($, e, next) => {
    const { url, prompt } = e as any;
    const res = await $.http.fetch("http://localhost:11235/md", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, f: "fit" }),
    });
    if (!res.ok) throw new Error("crawl4ai " + res.status);
    const md = JSON.parse(res.text).markdown;
    if (!md) throw new Error("crawl4ai empty markdown");
    const text = `Fetched via crawl4ai (raw page markdown, not a summary). Prompt: ${prompt}\n\n---\n${md}`;
    return { result: { bytes: md.length, code: 200, codeText: "OK", result: text, durationMs: 0, url }, text: "" };
  });
};
