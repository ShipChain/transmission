import logging
from calendar import monthrange
from datetime import datetime
from influxdb_metrics.loader import log_metric

from rest_framework import throttling

LOG = logging.getLogger('transmission')


# pylint: disable=attribute-defined-outside-init, super-init-not-called
class MonthlyRateThrottle(throttling.SimpleRateThrottle):
    def __init__(self):
        month = datetime.now().month
        year = datetime.now().year
        self.duration = monthrange(year, month)[1] * 86400
        # Rate limit is dynamically extracted from JWT

    def get_cache_key(self, request, view):
        if not request.user.is_authenticated:
            return None

        return request.user.token.get('organization_id', None)

    def allow_request(self, request, view):
        LOG.debug('Checking request for throttling')

        if request.method == 'GET':
            return True

        self.key = cache_key = self.get_cache_key(request, view)

        if not self.key:
            return True

        self.history = self.cache.get(cache_key, [])
        self.now = datetime.now().timestamp()
        self.num_requests = request.user.token.get('monthly_rate_limit', None)

        if not self.num_requests:
            return True

        # Drop any requests from the history which have now passed the
        # throttle duration
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if not self.num_requests:
            log_metric('transmission.info', tags={'method': 'throttling.MonthlyRateThrottle', 'module': __name__,
                                                  'organization_id': self.key, 'success': True})
            return self.throttle_success()
        if len(self.history) >= self.num_requests:
            log_metric('transmission.info', tags={'method': 'throttling.MonthlyRateThrottle', 'module': __name__,
                                                  'organization_id': self.key, 'success': False})
            return self.throttle_failure()
        log_metric('transmission.info', tags={'method': 'throttling.MonthlyRateThrottle', 'module': __name__,
                                              'organization_id': self.key, 'success': True})
        return self.throttle_success()
