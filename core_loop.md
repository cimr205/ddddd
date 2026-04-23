## CORE LOOP

This loop runs for EVERY task in the system. It is mandatory and cannot be skipped.

```
┌─────────────────────────────────────────────┐
│                  CORE LOOP                  │
├─────────────────────────────────────────────┤
│                                             │
│  1. OBSERVE                                 │
│     → What is the current state?            │
│     → What data do we have?                 │
│     → What is missing?                      │
│                                             │
│  2. THINK                                   │
│     → What is the exact goal?               │
│     → What is the fastest path?             │
│     → Which agent handles this?             │
│                                             │
│  3. ACT                                     │
│     → Execute actions (batched)             │
│     → Target: 5–20 actions per loop         │
│     → Never 1 action if multiple possible   │
│                                             │
│  4. EVALUATE                                │
│     → QA Agent scores the result            │
│     → SUCCESS ≥ 0.9 → deliver output        │
│     → SUCCESS < 0.8 → retry immediately     │
│                                             │
└─────────────────────────────────────────────┘
         ↓ repeat until SUCCESS ≥ 0.9
```

### Context Management Per Loop

Keep only:
- Current goal
- Latest 3 actions and results
- Critical extracted data

Discard:
- Full action history older than 3 steps
- Redundant page content
- Intermediate reasoning chains

### Self-Correction Triggers

If any of the following occur, change strategy immediately:

1. Same action repeated 2+ times with no progress
2. Page stuck loading > 10 seconds
3. Expected element not found after 2 attempts
4. QA score drops below 0.6 twice in a row
