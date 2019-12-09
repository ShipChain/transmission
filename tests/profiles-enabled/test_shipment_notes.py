#  Copyright 2019 ShipChain, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


from datetime import datetime
import hashlib

import pytest
import pytz
from dateutil.parser import parse as dt_parse
from dateutil.relativedelta import relativedelta
from rest_framework import status
from rest_framework.reverse import reverse
from shipchain_common.test_utils import datetimeAlmostEqual

from apps.shipments.models import TransitState
from apps.shipments.serializers import ActionType


# Less than 500 characters
MESSAGE_1 = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et ' \
            'dolore magna aliqua. Nisl purus in mollis nunc sed id semper risus. Nulla facilisi etiam dignissim diam.'

# More than 500 characters
MESSAGE_2 = MESSAGE_1 + 'Eu mi bibendum neque egestas. Dui faucibus in ornare quam viverra. Adipiscing elit' \
                                 ' duis tristique sollicitudin. Faucibus pulvinar elementum integer enim. Sed risus ' \
                                 'pretium quam vulputate dignissim suspendisse in est ante. Sit amet cursus sit amet ' \
                                 'dictum sit amet justo. Laoreet sit amet cursus sit amet dictum sit amet justo. ' \
                                 'Scelerisque in dictum non consectetur a erat nam at lectus. Porttitor rhoncus ' \
                                 'dolor purus non enim.'

# Contains special word "ShipChain"
MESSAGE_3 = MESSAGE_1 + 'ShipChain'


