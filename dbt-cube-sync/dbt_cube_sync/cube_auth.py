import base64
import hashlib
import hmac
import json
import time


def cube_jwt(secret: str) -> str:
    """Generate a minimal HS256 JWT accepted by Cube.js in production mode."""
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    header  = b64url(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    now     = int(time.time())
    payload = b64url(json.dumps({'iat': now, 'exp': now + 86400}).encode())
    signing = f'{header}.{payload}'
    sig     = b64url(hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest())
    return f'{signing}.{sig}'


def cube_auth_headers(secret: str) -> dict:
    """Return Authorization headers for Cube.js API requests."""
    if not secret:
        return {}
    return {'Authorization': f'Bearer {cube_jwt(secret)}'}
