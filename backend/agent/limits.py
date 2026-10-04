"""A single source for turn, lease and place-provider budgets."""
TURN_SECONDS=180
TURN_LEASE_SECONDS=190
SEARCH_SECONDS=145
FINAL_REPLY_RESERVE=15
STAGE_LIMITS={'web':(6,35),'extract':(6,15),'page':(16,5)}
PIPELINE_VERSION='geolonia-web-coordinates-v3'

class SearchLimit(Exception):
    """The shared search deadline or request count has been reached."""
