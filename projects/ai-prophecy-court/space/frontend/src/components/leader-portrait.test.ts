import { describe, expect, it } from "vitest";

import { leaderInitials } from "./leader-portrait";

describe("leader portrait helpers", () => {
  it("uses the first two name parts for stable court sigils", () => {
    expect(leaderInitials("Clement Delangue")).toBe("CD");
    expect(leaderInitials("  Jensen   Huang  ")).toBe("JH");
  });
});
