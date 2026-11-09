from auth import REMEMBER_SECONDS, remember_token, token_expiry


def test_remember_token_is_signed_expires_and_is_revoked_by_password_change():
    password = 'test-password-long-enough'
    token = remember_token(password, now=1000)
    assert token_expiry(token, password, now=1001) == 1000 + REMEMBER_SECONDS
    assert not token_expiry(token, password, now=1000 + REMEMBER_SECONDS)
    assert not token_expiry(token, 'different-password', now=1001)
    assert not token_expiry('9' + token[1:], password, now=1001)
    for invalid in (None, '', 'invalid', '1.x.y', 'x' * 200, token[:-1] + 'é'):
        assert not token_expiry(invalid, password, now=1001)
