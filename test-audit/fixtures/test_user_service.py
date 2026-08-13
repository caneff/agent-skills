"""Fixture: user-service tests.

Deliberately mixed quality — see ../answer-key.md for the expected bucket
of each test. Do not "fix" these in place; they exist to be judged.
"""

import random
import time

from user_service import UserService, ValidationError, validate_email

# db is a module-level global opened once at import time and reused by
# whatever test happens to run first; it is not passed to or built by the
# test below, and this fixture set has no conftest that owns it either.
from db import db


def test_user_repository_save_and_fetch():
    # REWRITE — mystery guest / resource optimism. The test reads and
    # writes through the ambient `db` import instead of an explicit local
    # fixture, so it silently depends on whatever rows a previous test left
    # behind. It fails when test order changes, though nothing about
    # save/fetch broke; it also cannot fail from a real regression that a
    # clean row would have caught. The round-trip behavior is real — rewrite
    # it against an explicit, isolated in-memory store.
    user = db.get_user(id=1)

    assert user.name == "whatever was inserted last"


def test_user_onboarding_flow():
    # REWRITE — eager test. One test body drives create, profile update,
    # welcome-email send, and audit-log count in a single run. When it
    # fails, the failure only says "onboarding broke somewhere," not which
    # of four behaviors regressed — so it fails for four different real
    # reasons collapsed into one. Each behavior is real; split into four
    # focused tests.
    service = UserService()
    user = service.create_user(name="Ada", email="ada@example.com")
    service.update_profile(user.id, bio="Mathematician")
    assert user.id is not None
    assert service.get_profile(user.id).bio == "Mathematician"
    assert service.email_log.count(user.email) == 1
    assert service.audit_log.count("user_created") == 1


def test_create_user_returns_expected_user():
    # REWRITE — sensitive equality. Asserting the whole object equal to a
    # literal locks in `id` and `created_at`, values the caller doesn't
    # control and this behavior doesn't promise. It fails whenever the
    # clock or the id sequence changes, though nothing a user cares about
    # broke. The real behavior — created user carries the name and email
    # you gave it — is worth keeping; assert only those two fields.
    service = UserService()

    user = service.create_user(name="Ada", email="ada@example.com")

    assert user == {
        "id": 42,
        "name": "Ada",
        "email": "ada@example.com",
        "created_at": "2026-08-13T00:00:00Z",
    }


def test_rejects_invalid_email():
    # REWRITE — name/behavior mismatch, and the only test that touches the
    # reject path. The name promises invalid addresses get rejected, but
    # the body only checks that the returned error object carries a default
    # `code` attribute — it would pass even if validate_email stopped
    # rejecting anything at all. Ordinarily a mismatch this total is a Cut;
    # here it is the sole guard on validate_email's reject branch, so
    # cutting it opens a silent coverage gap. Rewrite it to actually assert
    # invalid addresses raise ValidationError.
    error = ValidationError()

    assert error.code == "default"


def test_user_model_default_role_is_member():
    # CUT — library-default test. This proves the dataclass's own default
    # argument works, which the standard library already guarantees; it
    # cannot fail from anything this codebase does. Deleting it loses no
    # coverage of app behavior.
    from user_service import User

    user = User(name="Ada", email="ada@example.com")

    assert user.role == "member"


def test_retry_eventually_succeeds():
    # REWRITE — flakiness-by-construction. Real time.sleep and unseeded
    # random.random() decide, run to run, whether this passes — it can fail
    # when retry logic is correct (bad luck) and pass when retry logic is
    # broken (good luck). The behavior — retry keeps trying until success —
    # is real and worth guarding; rewrite with a mocked clock and a seeded
    # or injected random source so the outcome is deterministic.
    attempts = 0

    def flaky_call():
        nonlocal attempts
        attempts += 1
        time.sleep(0.01)
        if random.random() < 0.7:
            raise ConnectionError("transient")
        return "ok"

    service = UserService()
    result = service.call_with_retry(flaky_call, max_attempts=10)

    assert result == "ok"
