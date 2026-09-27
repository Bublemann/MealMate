"""Business rules, permissions and transactions (plan § 5.1).

Each public function runs its own unit of work (`async with session.begin()`); write
transactions stay short and never wait on the network or on bcrypt.
"""
