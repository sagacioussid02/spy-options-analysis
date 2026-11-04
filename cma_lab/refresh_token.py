"""Refresh the Robinhood token and sync the CMA vault credential.

Run at the start of each scheduled run (see run_basket.sh) so the hosted agents
always hold the current, un-rotated token pair. Exits non-zero if refresh fails.
"""
import sys

from lab import refresh_robinhood_token

sys.exit(0 if refresh_robinhood_token() else 1)
