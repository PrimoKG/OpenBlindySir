import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Only pure functions are unit-tested: no DOM emulation needed.
    environment: "node",
    include: ["tests/**/*.test.ts"],
    passWithNoTests: true,
  },
});
