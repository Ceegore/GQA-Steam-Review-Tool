"""Interface layer: Protocol-based contracts between modules.

Every interface here is a ``typing.Protocol`` so callers depend on
shape, not on a specific implementation. This is the "D" in SOLID.
"""