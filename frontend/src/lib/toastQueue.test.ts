import { describe, expect, test } from "vitest";
import { MAX_TOASTS, pushToast, type QueuedToast } from "./toastQueue";

function makeToast(overrides: Partial<QueuedToast> = {}): QueuedToast {
  return {
    id: Math.random().toString(36).substring(2, 9),
    title: "API ERROR",
    description: "An unexpected error occurred",
    variant: "destructive",
    ...overrides,
  };
}

describe("pushToast", () => {
  test("appends a toast to an empty queue", () => {
    const t = makeToast();
    expect(pushToast([], t)).toEqual([t]);
  });

  test("appends distinct toasts up to the cap", () => {
    let queue: QueuedToast[] = [];
    for (let i = 0; i < MAX_TOASTS; i++) {
      queue = pushToast(queue, makeToast({ description: `error ${i}` }));
    }
    expect(queue).toHaveLength(MAX_TOASTS);
  });

  test("drops the oldest toast when the cap is exceeded", () => {
    let queue: QueuedToast[] = [];
    for (let i = 0; i < MAX_TOASTS + 3; i++) {
      queue = pushToast(queue, makeToast({ description: `error ${i}` }));
    }
    expect(queue).toHaveLength(MAX_TOASTS);
    expect(queue[0].description).toBe("error 3");
    expect(queue[queue.length - 1].description).toBe(`error ${MAX_TOASTS + 2}`);
  });

  test("does not stack a duplicate error toast (poller spam)", () => {
    const first = makeToast(); // destructive by default
    const dup = makeToast(); // same title/description/variant, different id
    const queue = pushToast(pushToast([], first), dup);
    expect(queue).toHaveLength(1);
    expect(queue[0].id).toBe(first.id);
  });

  test("stacks duplicate user-action (non-error) toasts", () => {
    // Two identical success confirmations from two real actions must both show.
    const first = makeToast({ variant: "default", title: "Success", description: "Standard deleted" });
    const second = makeToast({ variant: "default", title: "Success", description: "Standard deleted" });
    const queue = pushToast(pushToast([], first), second);
    expect(queue).toHaveLength(2);
  });

  test("treats different descriptions as distinct toasts", () => {
    const a = makeToast({ description: "Feed poll failed" });
    const b = makeToast({ description: "Worker offline" });
    expect(pushToast(pushToast([], a), b)).toHaveLength(2);
  });

  test("treats different variants of the same message as distinct", () => {
    const a = makeToast({ variant: "destructive" });
    const b = makeToast({ variant: "default" });
    expect(pushToast(pushToast([], a), b)).toHaveLength(2);
  });
});
