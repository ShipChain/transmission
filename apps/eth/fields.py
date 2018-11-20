"""
Copyright 2018 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from django.core.validators import RegexValidator
from django.db import models


NULL_ADDRESS = "0x0"
ADDRESS_REGEX = RegexValidator(regex=r'^0x([A-Fa-f0-9]{40})$', message="Invalid address.")
HASH_REGEX = RegexValidator(regex=r'^0x([A-Fa-f0-9]{64})$', message="Invalid hash.")


class AddressField(models.CharField):
    description = "An Ethereum address"

    def __init__(self, *args, **kwargs):
        if 'max_length' not in kwargs:
            kwargs['max_length'] = 42
        if 'blank' not in kwargs:
            kwargs['blank'] = False
        if 'default' not in kwargs:
            kwargs['default'] = NULL_ADDRESS
        if 'validators' not in kwargs:
            kwargs['validators'] = [ADDRESS_REGEX]
        super().__init__(*args, **kwargs)


class HashField(models.CharField):
    description = "An Ethereum (Keccak SHA256) hash"

    def __init__(self, *args, **kwargs):
        if 'max_length' not in kwargs:
            kwargs['max_length'] = 66
        if 'blank' not in kwargs:
            kwargs['blank'] = False
        if 'default' not in kwargs:
            kwargs['default'] = ""
        if 'validators' not in kwargs:
            kwargs['validators'] = [HASH_REGEX]
        super().__init__(*args, **kwargs)
