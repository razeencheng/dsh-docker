"""Exercise release recovery through the real publisher, without network access."""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'release.py'
SPEC = importlib.util.spec_from_file_location('release_recovery', SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)

OLD = 'dsh-v1.0.0'
MIDDLE = 'dsh-v1.1.0'
NEWEST = 'dsh-v1.2.0'
UPSTREAM_SHA = 'a' * 40
PACKAGING_SHA = 'b' * 40


class MemoryRegistry:
    """The Docker CLI boundary, including non-atomic writes of multiple tags."""

    def __init__(self):
        self.refs = {}
        self.objects = {}
        self.latest_writes = []
        self.index_creates = 0
        self.fail_after_latest_once = False
        self.drop_index_annotations = False
        self.arch_digests = {
            arch: self.store({'platform': {'os': 'linux', 'architecture': arch}})
            for arch in ('amd64', 'arm64')
        }

    def store(self, manifest):
        digest = 'sha256:' + hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
        self.objects[digest] = manifest
        return digest

    def write_tag(self, ref, digest):
        self.refs[ref] = digest
        if ref == release.IMAGE + ':latest':
            self.latest_writes.append(digest)

    def regctl(self, *args):
        if args[:2] != ('index', 'create'):
            raise AssertionError(f'Unexpected regctl operation: {args}')
        translated = ['buildx', 'imagetools', 'create', '--tag', args[2]]
        arguments = iter(args[3:])
        for argument in arguments:
            value = next(arguments)
            if argument == '--media-type':
                if value != 'application/vnd.oci.image.index.v1+json':
                    raise AssertionError('Release index must use OCI media type')
            elif argument == '--annotation':
                translated.extend(['--annotation', 'index:' + value])
            elif argument == '--digest':
                translated.append(release.IMAGE + '@' + value)
            else:
                raise AssertionError(f'Unexpected regctl argument: {argument}')
        return self.docker(*translated)

    def docker(self, *args):
        if args[:2] != ('buildx', 'imagetools'):
            raise AssertionError(f'Unexpected Docker operation: {args}')
        if args[2] == 'inspect':
            ref = args[3]
            digest = ref.split('@', 1)[1] if '@' in ref else self.refs.get(ref)
            if digest not in self.objects:
                raise subprocess.CalledProcessError(1, args, stderr='manifest unknown')
            result = self.objects[digest] if '--raw' in args else {'digest': digest}
            return json.dumps(result)
        if args[2] != 'create':
            raise AssertionError(f'Unexpected Docker operation: {args}')

        annotations, targets, sources = {}, [], []
        arguments = iter(args[3:])
        for argument in arguments:
            if argument == '--tag':
                targets.append(next(arguments))
            elif argument == '--annotation':
                key, value = next(arguments).removeprefix('index:').split('=', 1)
                annotations[key] = value
            else:
                sources.append(argument.split('@', 1)[1])
        if annotations:
            digest = self.store({
                'mediaType': 'application/vnd.oci.image.index.v1+json',
                'annotations': {} if self.drop_index_annotations else annotations,
                'manifests': [
                    {'digest': source, 'platform': self.objects[source]['platform']}
                    for source in sources
                ],
            })
            self.index_creates += 1
        else:
            if len(sources) != 1:
                raise AssertionError('Alias publication must reference one existing index')
            digest = sources[0]

        latest = release.IMAGE + ':latest'
        if self.fail_after_latest_once and latest in targets:
            self.fail_after_latest_once = False
            self.write_tag(latest, digest)
            raise subprocess.CalledProcessError(
                1, args, stderr='Injected failure after latest, before other alias writes')
        for target in targets:
            self.write_tag(target, digest)
        return ''


class MemoryStateStore:
    """The GitHub state boundary, with a failed write leaving durable state intact."""

    def __init__(self, state, fail_once):
        self.state = copy.deepcopy(state)
        self.fail_once = fail_once
        self.blob = 'initial-blob'
        self.writes = 0

    def load_state(self):
        return copy.deepcopy(self.state), self.blob

    def save_state(self, state, blob_sha):
        if blob_sha != self.blob:
            raise AssertionError('Publisher reused a stale state blob SHA')
        if self.fail_once:
            self.fail_once = False
            error = HTTPError('https://example.invalid/state', 500, 'Injected state write failure', {}, None)
            error.close()
            raise error
        self.state = copy.deepcopy(state)
        self.writes += 1
        self.blob = f'saved-blob-{self.writes}'
        return self.blob


class ReleaseRecoveryTests(unittest.TestCase):
    def artifacts(self, job, registry):
        return {
            arch: {**job, 'arch': arch, 'digest': digest}
            for arch, digest in registry.arch_digests.items()
        }

    def test_missing_index_metadata_cannot_advance_aliases(self):
        registry = MemoryRegistry()
        registry.drop_index_annotations = True
        state, jobs = release.plan(None, {OLD: UPSTREAM_SHA}, PACKAGING_SHA)
        job = jobs[0]
        with patch.object(release, 'docker', side_effect=registry.docker), \
                patch.object(release, 'regctl', side_effect=registry.regctl):
            with self.assertRaisesRegex(ValueError, 'metadata'):
                release.publish(job, self.artifacts(job, registry), state)
        self.assertEqual(registry.latest_writes, [])
        self.assertNotIn(release.IMAGE + ':1.0.0', registry.refs)

    def test_retry_reuses_tested_immutable_index_when_rebuild_digests_change(self):
        registry = MemoryRegistry()
        registry.fail_after_latest_once = True
        state, jobs = release.plan(None, {OLD: UPSTREAM_SHA}, PACKAGING_SHA)
        job = jobs[0]
        with patch.object(release, 'docker', side_effect=registry.docker), \
                patch.object(release, 'regctl', side_effect=registry.regctl):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(job, self.artifacts(job, registry), state)
            original = registry.refs[release.IMAGE + ':1.0.0-r1']
            registry.arch_digests = {
                arch: registry.store({'platform': {'os': 'linux', 'architecture': arch}, 'rebuilt': True})
                for arch in ('amd64', 'arm64')
            }
            restored = release.publish(job, self.artifacts(job, registry), state)
        self.assertEqual(restored, original)
        self.assertEqual(registry.index_creates, 1)
        self.assertEqual(registry.refs[release.IMAGE + ':1.0.0'], original)

    def exercise_recovery(self, failure):
        registry = MemoryRegistry()
        state, initial_jobs = release.plan(None, {OLD: UPSTREAM_SHA}, PACKAGING_SHA)
        initial = initial_jobs[0]

        with patch.object(release, 'docker', side_effect=registry.docker), \
                patch.object(release, 'regctl', side_effect=registry.regctl):
            digest = release.publish(initial, self.artifacts(initial, registry), state)
            release.complete(state, initial, digest)
        registry.latest_writes.clear()
        state, jobs = release.plan(
            state, {tag: UPSTREAM_SHA for tag in (OLD, MIDDLE, NEWEST)}, PACKAGING_SHA)
        store = MemoryStateStore(state, fail_once=failure == 'state-write')
        registry.fail_after_latest_once = failure == 'partial-alias-push'

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / 'plan.json'
            plan_path.write_text(json.dumps(jobs))
            for job in jobs:
                for arch, artifact in self.artifacts(job, registry).items():
                    path = root / f"{job['version']}-r{job['revision']}-{arch}.json"
                    path.write_text(json.dumps(artifact))
            args = argparse.Namespace(plan=str(plan_path), artifacts=str(root))
            with patch.object(release, 'GitHub', return_value=store), \
                    patch.object(release, 'docker', side_effect=registry.docker), \
                    patch.object(release, 'regctl', side_effect=registry.regctl), \
                    patch.dict(os.environ, {'GITHUB_REPOSITORY': 'example/dsh-docker'}, clear=True), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'Unpublished releases remain pending'):
                    release.finalize(args)

                newest_digest = registry.refs[release.IMAGE + ':1.2.0-r1']
                self.assertEqual(registry.latest_writes, [newest_digest])
                self.assertEqual(release.read_registry_latest()['tag'], NEWEST)
                self.assertEqual(store.state['latest']['tag'], NEWEST)
                self.assertEqual(set(store.state['pending']), {NEWEST})
                self.assertIn('1', store.state['published'][MIDDLE])
                if failure == 'partial-alias-push':
                    self.assertNotIn(release.IMAGE + ':1.2.0', registry.refs)

                # Rerun the same plan: reuse the immutable index, repair aliases,
                # and skip the release whose completion was already persisted.
                creates_before_retry = registry.index_creates
                release.finalize(args)
                self.assertEqual(registry.index_creates, creates_before_retry)
                self.assertEqual(store.state['pending'], {})
                self.assertIn('1', store.state['published'][NEWEST])
                self.assertEqual(store.state['latest']['digest'], newest_digest)
                self.assertEqual(registry.latest_writes, [newest_digest])
                for alias in ('1.2.0-r1', '1.2.0', NEWEST, 'latest'):
                    self.assertEqual(registry.refs[f'{release.IMAGE}:{alias}'], newest_digest)

    def test_state_write_failure_does_not_regress_latest_and_retry_completes(self):
        self.exercise_recovery('state-write')

    def test_partial_alias_push_does_not_regress_latest_and_retry_repairs_aliases(self):
        self.exercise_recovery('partial-alias-push')


if __name__ == '__main__':
    unittest.main()
