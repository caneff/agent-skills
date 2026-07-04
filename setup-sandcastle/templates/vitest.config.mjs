import { defineConfig } from "vitest/config";

// Dev-home test config: runs the orchestrator's pure-function tests. These do
// NOT ship into target repos (the skill copies .sandcastle/ minus tests/).
export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: [".sandcastle/tests/**/*.test.mjs"],
  },
});
