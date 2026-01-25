"""Rate limiting utility for controlling API request frequency.

This module provides a thread-safe rate limiter implementation using a leaky bucket
algorithm. It is designed to help prevent API quota exhaustion when making
concurrent requests to external services like Google APIs.
"""

import time
import threading
from typing import Optional

class RateLimiter:
    """Thread-safe rate limiter."""
    
    def __init__(self, requests_per_second: float):
        """Initialize the rate limiter.
        
        Args:
            requests_per_second: Maximum number of requests allowed per second.
        """
        self.rate = requests_per_second
        self.time_per_request = 1.0 / self.rate
        self.last_request_time = 0.0
        self._lock = threading.Lock()
    
    def set_rate(self, requests_per_second: float) -> None:
        """Update the rate limit dynamically."""
        with self._lock:
            self.rate = requests_per_second
            self.time_per_request = 1.0 / self.rate

    def wait(self) -> None:
        """Block until a request can be made."""
        with self._lock:
            now = time.time()
            # Calculate when the next request is allowed
            next_allowed = self.last_request_time + self.time_per_request
            
            if now < next_allowed:
                sleep_time = next_allowed - now
                self.last_request_time = next_allowed
            else:
                sleep_time = 0
                self.last_request_time = now
        
        if sleep_time > 0:
            time.sleep(sleep_time)
