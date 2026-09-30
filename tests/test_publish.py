"""Episode-cap pruning + upload retry — against a fake show that behaves like Spotify."""
import json
import stat

import pytest

from briefing.publish.spotify import (
    DEFAULT_MAX_EPISODES,
    MAX_DELETES_PER_RUN,
    PublishError,
    cli_runner,
    is_episode_limit,
    max_episodes,
    prune,
    publish,
    upload,
)

LIMIT_ERR = ('API error (429): {"error_code":"RESOURCE_EXHAUSTED","message":"You\'ve reached the '
             'episode limit. Delete existing episodes to create new ones."}')
RATE_ERR = 'API error (429): {"message":"Too many requests, retry later"}'
SHOW = "spotify:show:TEST"


class FakeShow:
    """In-memory show: refuses uploads at `hard` episodes like Spotify does at 60."""

    def __init__(self, n, hard=60, fail_list=False, fail_delete=(), upload_errors=()):
        self.eps = [{"episode_uri": f"spotify:episode:e{i:03d}", "title": f"Day {i}",
                     "created_at": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}Z"} for i in range(n)]
        self.hard, self.fail_list, self.fail_delete = hard, fail_list, set(fail_delete)
        self.upload_errors = list(upload_errors)   # forced errors for successive uploads
        self.calls, self.deleted = [], []

    def __call__(self, args):
        self.calls.append(args[0] if args[0] != "episodes" else f"episodes {args[1]}")
        if args[0] == "episodes" and args[1] == "--show-id":
            if self.fail_list:
                raise PublishError("API error (500): boom")
            return {"episodes": list(reversed(self.eps))}      # deliberately not oldest-first
        if args[:2] == ["episodes", "delete"]:
            if args[2] in self.fail_delete:
                raise PublishError("API error (500): delete failed")
            self.eps = [e for e in self.eps if not e["episode_uri"].endswith(args[2])]
            self.deleted.append(args[2])
            return {"episode_id": args[2], "status": "deleted"}
        if args[0] == "upload":
            if self.upload_errors:
                raise PublishError(self.upload_errors.pop(0))
            if len(self.eps) >= self.hard:
                raise PublishError(LIMIT_ERR)
            self.eps.append({"episode_uri": "spotify:episode:new", "title": "today",
                             "created_at": "2099-01-01T00:00:00Z"})
            return {"episode_uri": "spotify:episode:new"}
        raise AssertionError(args)


def _publish(show, limit=55):
    return publish(show, "a.mp3", "T", "S", SHOW, limit)


def test_under_cap_deletes_nothing():
    show = FakeShow(40)
    assert _publish(show)["episode_uri"] == "spotify:episode:new"
    assert show.deleted == [] and len(show.eps) == 41


def test_full_show_pruned_oldest_first_to_cap():
    show = FakeShow(60)                                  # today's real situation
    _publish(show)
    assert show.deleted == [f"e{i:03d}" for i in range(6)]   # the six oldest, in order
    assert len(show.eps) == 55                           # never more than the cap after upload


def test_exactly_at_cap_makes_room_for_one():
    show = FakeShow(55)
    _publish(show)
    assert show.deleted == ["e000"] and len(show.eps) == 55


def test_steady_state_stays_at_cap_over_many_days():
    show = FakeShow(50)
    for _ in range(30):
        _publish(show)
        assert len(show.eps) <= 55
    assert len(show.eps) == 55


def test_deletes_are_capped_per_run():
    show = FakeShow(60)
    prune(show, SHOW, 5)                                 # would need 56 deletes
    assert len(show.deleted) == MAX_DELETES_PER_RUN


def test_dry_run_deletes_nothing():
    show = FakeShow(60)
    would = prune(show, SHOW, 55, dry_run=True)
    assert len(would) == 6 and show.deleted == [] and len(show.eps) == 60


def test_list_failure_still_uploads():
    show = FakeShow(10, fail_list=True)
    assert _publish(show)["episode_uri"] == "spotify:episode:new"
    assert show.deleted == []


def test_one_failed_delete_does_not_stop_the_rest_or_the_upload():
    show = FakeShow(56, fail_delete={"e000"})
    _publish(show)
    assert show.deleted == ["e001"]                      # e000 failed, e001 still went
    assert show.eps[-1]["episode_uri"] == "spotify:episode:new"


def test_missing_timestamp_refuses_to_prune_but_uploads():
    show = FakeShow(58)
    show.eps[3]["created_at"] = ""
    _publish(show)
    assert show.deleted == []                            # can't know the oldest → touch nothing


def test_episode_limit_429_frees_one_slot_and_retries_once():
    show = FakeShow(59, upload_errors=[LIMIT_ERR])       # e.g. pruning was skipped
    result = upload(show, "a.mp3", "T", "S", SHOW)
    assert result["episode_uri"] == "spotify:episode:new"
    assert show.deleted == ["e000"]
    assert show.calls.count("upload") == 2


def test_rate_limit_429_never_deletes():
    show = FakeShow(59, upload_errors=[RATE_ERR])
    with pytest.raises(PublishError, match="Too many requests"):
        upload(show, "a.mp3", "T", "S", SHOW)
    assert show.deleted == [] and show.calls.count("upload") == 1


def test_episode_limit_twice_gives_up_after_one_retry():
    show = FakeShow(59, upload_errors=[LIMIT_ERR, LIMIT_ERR])
    with pytest.raises(PublishError, match="episode limit"):
        upload(show, "a.mp3", "T", "S", SHOW)
    assert show.deleted == ["e000"] and show.calls.count("upload") == 2


def test_is_episode_limit_matches_only_the_show_full_error():
    assert is_episode_limit(LIMIT_ERR)
    assert not is_episode_limit(RATE_ERR)
    assert not is_episode_limit("API error (500): episode limit")   # wrong status


@pytest.mark.parametrize("raw,expected", [
    (None, DEFAULT_MAX_EPISODES), (55, 55), ("40", 40), (60, 60),
    (0, DEFAULT_MAX_EPISODES), (61, DEFAULT_MAX_EPISODES), ("lots", DEFAULT_MAX_EPISODES),
])
def test_max_episodes_config(raw, expected):
    cfg = {"spotify": {} if raw is None else {"max_episodes": raw}}
    assert max_episodes(cfg) == expected


def _fake_cli(tmp_path, stdout, code):
    p = tmp_path / "save-to-spotify"
    p.write_text(f"#!/bin/sh\ncat <<'EOF'\n{stdout}\nEOF\nexit {code}\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def test_cli_runner_surfaces_the_real_error_text(tmp_path):
    run = cli_runner(_fake_cli(tmp_path, json.dumps({"error": LIMIT_ERR}), 1))
    with pytest.raises(PublishError) as exc:
        run(["upload", "a.mp3"])
    assert is_episode_limit(str(exc.value))


def test_cli_runner_returns_json_on_success(tmp_path):
    run = cli_runner(_fake_cli(tmp_path, '{"episode_uri":"spotify:episode:x"}', 0))
    assert run(["upload", "a.mp3"]) == {"episode_uri": "spotify:episode:x"}


def test_cli_runner_rejects_garbage_output(tmp_path):
    run = cli_runner(_fake_cli(tmp_path, "not json", 0))
    with pytest.raises(PublishError, match="unparseable"):
        run(["episodes", "--show-id", SHOW])
