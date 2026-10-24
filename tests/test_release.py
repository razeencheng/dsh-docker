import copy
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'release.py'
spec = importlib.util.spec_from_file_location('release', SCRIPT)
release = importlib.util.module_from_spec(spec) if SCRIPT.exists() else None
if release:
    spec.loader.exec_module(release)

A = 'a' * 40
B = 'b' * 40
C = 'c' * 40
T1 = 'dsh-v0.1.0-rc.2'
T2 = 'dsh-v0.2.1-rc.3'
T3 = 'dsh-v0.2.1-rc.10'


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(release, 'release planner must exist')

    def test_semver_uses_numeric_components_and_prerelease_order(self):
        versions = ['dsh-v1.0.0', 'dsh-v1.0.0-rc.10', 'dsh-v1.0.0-rc.2',
                    'dsh-v1.0.0-alpha.20', 'dsh-v0.10.0', 'dsh-v0.9.0']
        self.assertEqual(sorted(versions, key=release.version_key), list(reversed(versions)))

    def test_rejects_unsafe_or_unrelated_tags(self):
        for tag in ['master', 'dsh-v1.0.0;id', 'dsh-v01.0.0', '../latest', 'v1.0.0']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.version_key(tag)

    def test_initial_plan_builds_only_newest_and_records_baseline(self):
        state, jobs = release.plan(None, {T1: A, T2: B}, C)
        self.assertEqual([j['tag'] for j in jobs], [T2])
        self.assertEqual(state['observed'], {T1: A, T2: B})
        self.assertEqual(jobs[0]['revision'], 1)

    def test_new_backport_tag_is_built_even_when_lower_than_latest(self):
        state, jobs = release.plan(None, {T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        state, jobs = release.plan(state, {T1: A, T2: B}, C)
        self.assertEqual([j['tag'] for j in jobs], [T1])

    def test_failed_pending_job_is_retried_without_advancing_revision(self):
        state, first = release.plan(None, {T2: B}, C)
        state, retry = release.plan(state, {T2: B}, C)
        self.assertEqual(retry, first)

    def test_successful_jobs_not_rebuilt_on_schedule(self):
        state, jobs = release.plan(None, {T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        _, jobs = release.plan(state, {T2: B}, A)
        self.assertEqual(jobs, [])

    def test_changed_recipe_reserves_new_revision_for_pending_build(self):
        state, jobs = release.plan(None, {T2: B}, C)
        state, jobs = release.plan(state, {T2: B}, A)
        self.assertEqual(jobs[0]['revision'], 2)
        self.assertEqual(jobs[0]['packaging_sha'], A)

    def test_manual_historical_build_and_packaging_revision(self):
        state, jobs = release.plan(None, {T1: A, T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '2' * 64)
        state, jobs = release.plan(state, {T1: A, T2: B}, C, manual_tag=T1)
        self.assertEqual(jobs[0]['tag'], T1)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        state, jobs = release.plan(state, {T1: A, T2: B}, C, manual_tag=T1)
        self.assertEqual(jobs[0]['revision'], 2)

    def test_cannot_overwrite_published_revision(self):
        state, jobs = release.plan(None, {T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        with self.assertRaises(ValueError):
            release.plan(state, {T2: B}, C, manual_tag=T2, revision=1)

    def test_changed_upstream_tag_fails_closed(self):
        state, _ = release.plan(None, {T2: B}, C)
        with self.assertRaises(ValueError):
            release.plan(state, {T2: A}, C)

    def test_old_version_does_not_regress_latest(self):
        state, jobs = release.plan(None, {T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '2' * 64)
        state, jobs = release.plan(state, {T1: A, T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        self.assertEqual(state['latest']['tag'], T2)

    def test_new_packaging_revision_advances_latest_for_same_version(self):
        state, jobs = release.plan(None, {T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        state, jobs = release.plan(state, {T2: B}, C, manual_tag=T2)
        release.complete(state, jobs[0], 'sha256:' + '2' * 64)
        self.assertEqual(state['latest']['revision'], 2)

    def test_batch_limit_leaves_remaining_tags_pending(self):
        state, jobs = release.plan(None, {T1: A}, C)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        state, jobs = release.plan(state, {T1: A, T2: B, T3: C}, C, limit=1)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(state['pending']), 2)

    def test_registry_latest_prevents_rollback_after_state_write_failed(self):
        state, jobs = release.plan(None, {T1: A}, C)
        old_job = jobs[0]
        remote = {'tag': T2, 'revision': 1, 'digest': 'sha256:' + '2' * 64}
        release.reconcile_latest(state, remote)
        self.assertFalse(release.advances_latest(state, old_job))
        release.complete(state, old_job, 'sha256:' + '1' * 64)
        self.assertEqual(state['latest'], remote)

    def test_registry_does_not_override_newer_durable_state(self):
        state, jobs = release.plan(None, {T2: B}, C)
        release.complete(state, jobs[0], 'sha256:' + '2' * 64)
        remote = {'tag': T1, 'revision': 1, 'digest': 'sha256:' + '1' * 64}
        release.reconcile_latest(state, remote)
        self.assertEqual(state['latest']['tag'], T2)

    def test_explicit_revision_is_not_incremented_again_on_recipe_change(self):
        state, _ = release.plan(None, {T2: B}, C)
        _, jobs = release.plan(state, {T2: B}, A, manual_tag=T2, revision=5)
        self.assertEqual(jobs[0]['revision'], 5)

    def test_explicit_pending_revision_cannot_be_reused_for_new_recipe(self):
        state, _ = release.plan(None, {T2: B}, C)
        with self.assertRaises(ValueError):
            release.plan(state, {T2: B}, A, manual_tag=T2, revision=1)

    def test_failed_batch_does_not_starve_other_new_tags(self):
        state, jobs = release.plan(None, {T1: A}, C)
        release.complete(state, jobs[0], 'sha256:' + '1' * 64)
        tags = {T1: A, **{f'dsh-v1.{n}.0': B for n in range(1, 6)}}
        state, first = release.plan(state, tags, C)
        state, second = release.plan(state, tags, C)
        self.assertNotIn('dsh-v1.1.0', [j['tag'] for j in first])
        self.assertIn('dsh-v1.1.0', [j['tag'] for j in second])

    def test_upstream_tag_cannot_collide_with_immutable_revision_name(self):
        with self.assertRaises(ValueError):
            release.plan(None, {'dsh-v1.0.0': A, 'dsh-v1.0.0-r1': B}, C)

    def test_plan_does_not_mutate_input_on_error(self):
        state, _ = release.plan(None, {T2: B}, C)
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            release.plan(state, {T2: A}, C)
        self.assertEqual(state, before)

    def test_annotated_tag_is_peeled_to_commit(self):
        calls = []
        def request(path):
            calls.append(path)
            return {'object': {'type': 'commit', 'sha': B}}
        self.assertEqual(release.peel_tag({'type': 'tag', 'sha': A}, request), B)
        self.assertEqual(calls, ['git/tags/' + A])

    def test_incomplete_architecture_artifacts_are_not_publishable(self):
        job = {'tag': T2, 'version': '0.2.1-rc.3', 'sha': B, 'revision': 1, 'packaging_sha': C}
        self.assertFalse(release.artifacts_complete(job, {}))
        self.assertFalse(release.artifacts_complete(job, {'amd64': {}}))


if __name__ == '__main__':
    unittest.main()
