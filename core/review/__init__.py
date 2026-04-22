"""core.review — review task model and queue.

Status: **not yet implemented** (Issue #22).

Planned responsibilities
------------------------
- Maintain a review queue for low-confidence or policy-flagged candidates.
- Define the review task model (segment-level flagging, side-by-side
  comparison, approval state).
- Expose an interface for a local UI to consume review tasks.
- Record review history.

Planned public API
------------------
ReviewTask         A review unit: flagged candidate + context.
ReviewQueue        FIFO queue of pending review tasks.
enqueue(task)      Add a task to the review queue.
dequeue()          Retrieve the next pending task.
approve(task, …)   Mark a task as approved (with optional edits).
"""

from __future__ import annotations

__all__: list = []  # Empty until Issue #22 is implemented.
