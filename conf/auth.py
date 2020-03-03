import os
import base64
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import load_pem_public_key


SESSION_COOKIE_NAME = os.environ.get(
    'SESSION_COOKIE_NAME', 'txm-sessionid'
)

OIDC_PUBLIC_KEY_PEM_BASE64 = os.environ.get('OIDC_PUBLIC_KEY_PEM_BASE64', 'LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0NCk1JR2ZN\
QTBHQ1NxR1NJYjNEUUVCQVFVQUE0R05BRENCaVFLQmdRQ2FmTDBXVVRObFdteTJJdlRPQ2xpNHdqZFMNClk1cWJNaXNQcHlrNVFkamRNMEFuY2gvbm5qTGJ\
aVzAwakw0V0lXM0YzOHZjNThQSzExNzB3OG9maGF1TEJSMEgNCjBsRTZoTTlsV2l3TjZOODFNVWZ5cG1HME9ReG1vYW5XN2Y1ano2Z2tCRkNzc21pQWZxSF\
Z1TTJtSmlJdGJZTVUNCm8vcmtxcm9zQnVadmFKSnJEUUlEQVFBQg0KLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t')

SIMPLE_JWT = {
    'VERIFYING_KEY': load_pem_public_key(
        data=base64.b64decode(OIDC_PUBLIC_KEY_PEM_BASE64.strip()),
        backend=default_backend()
    ),
    'ALGORITHM': 'RS256',
    'AUTH_HEADER_TYPES': ('JWT',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.UntypedToken',),
    'USER_ID_CLAIM': 'sub',
    'TOKEN_USER_CLASS': 'shipchain_common.authentication.PermissionedTokenUser',
}
