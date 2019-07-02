from calendar import monthrange
from datetime import datetime
from rest_framework import throttling


# pylint: disable=attribute-defined-outside-init
class MonthlyRateThrottle(throttling.SimpleRateThrottle):
    scope = 'user'

    def parse_rate(self, rate):
        month = datetime.now().month
        year = datetime.now().year
        duration = monthrange(year, month)[1] * 86400
        return (None, duration)

    def get_cache_key(self, request, view):
        if not request.user.is_authenticated:
            return None

        return request.user.token.get('organization_id', None)

    def allow_request(self, request, view):

        if request.method == 'GET':
            return True

        self.key = cache_key = self.get_cache_key(request, view)

        if not self.key:
            return True

        self.history = self.cache.get(cache_key, [])
        # self.now = datetime.now().day * 86400
        self.now = datetime.now().timestamp()
        self.num_requests = request.user.token.get('monthly_rate_limit', None)

        # Drop any requests from the history which have now passed the
        # throttle duration
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if not self.num_requests:
            return self.throttle_success()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()
