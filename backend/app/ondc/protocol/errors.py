
"""Supported discovery failures mapped to the pinned Seller App error list."""
class DiscoveryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.safe_message = message
