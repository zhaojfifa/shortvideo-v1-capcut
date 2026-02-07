from gateway.app.services.status_policy.apollo_avatar import ApolloAvatarStatusPolicy


def test_policy_does_not_override_explicit_failure() -> None:
    policy = ApolloAvatarStatusPolicy()
    task = {"publish_key": "default/default/abc/deliver/publish/capcut_pack.zip"}
    updates = {"status": "failed", "error_reason": "simulate_fail"}

    out = policy.reconcile_after_step(task, step="post", updates=updates, force=False)

    assert out.get("status") == "failed"
    assert out.get("error_reason") == "simulate_fail"


def test_policy_sets_ready_when_publish_key_exists_and_no_explicit_status() -> None:
    policy = ApolloAvatarStatusPolicy()
    task = {"publish_key": "default/default/abc/deliver/publish/capcut_pack.zip"}
    updates = {"subtitles_status": "failed"}

    out = policy.reconcile_after_step(task, step="post", updates=updates, force=False)

    assert out.get("status") == "ready"
    assert out.get("publish_status") == "ready"
    assert out.get("subtitles_status") == "failed"
