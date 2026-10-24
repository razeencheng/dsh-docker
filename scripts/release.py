#!/usr/bin/env python3
"""Plan upstream releases and publish tested images; requires only the stdlib.

All writers must share the workflow's global release concurrency group. The
release-state branch is a durable queue, not an expiring Actions cache.
"""
import argparse
import base64
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

UPSTREAM = 'deepseek-ai/deepseek-harness'
STATE_BRANCH = 'release-state'
IMAGE = 'razeencheng/dsh'
TAG_RE = re.compile(r'dsh-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z')
SHA_RE = re.compile(r'[0-9a-f]{40}\Z')
DIGEST_RE = re.compile(r'sha256:[0-9a-f]{64}\Z')


def version_key(tag):
    match = TAG_RE.fullmatch(tag)
    if not match or len(tag) > 100:
        raise ValueError(f'Unsupported upstream tag: {tag!r}')
    major, minor, patch, pre = match.groups()
    parts = []
    for part in pre.split('.') if pre else []:
        if part.isdigit():
            if len(part) > 1 and part.startswith('0'):
                raise ValueError(f'Invalid prerelease: {tag}')
            parts.append((0, int(part)))
        else:
            parts.append((1, part))
    return (int(major), int(minor), int(patch), pre is None, tuple(parts))


def plan(previous, tags, packaging_sha, manual_tag=None, revision=None, limit=4):
    if not SHA_RE.fullmatch(packaging_sha):
        raise ValueError('Packaging commit must be a full commit SHA')
    if not tags:
        raise ValueError('No supported upstream tags found')
    for tag, sha in tags.items():
        version_key(tag)
        if re.search(r'-r[0-9]+$', tag):
            raise ValueError(f'Upstream tag conflicts with reserved packaging suffix: {tag}')
        if not SHA_RE.fullmatch(sha):
            raise ValueError(f'Invalid upstream commit: {tag}')
    if revision is not None and (revision < 1 or not manual_tag):
        raise ValueError('A positive revision requires an explicit upstream tag')
    state = copy.deepcopy(previous) if previous else {
        'schema': 1, 'observed': {}, 'pending': {}, 'published': {},
        'reserved': {}, 'latest': None,
    }
    if state.get('schema') != 1:
        raise ValueError('Unknown release-state schema')
    for tag, sha in tags.items():
        if tag in state['observed'] and sha != state['observed'][tag]:
            raise ValueError(f'Upstream tag moved: {tag}; investigate before publishing')
    new_tags = set(tags) - set(state['observed'])
    if not previous:
        new_tags = {max(tags, key=version_key)}
    if manual_tag:
        if manual_tag not in tags:
            raise ValueError(f'Upstream tag does not exist: {manual_tag}')
        new_tags.add(manual_tag)
    state['observed'].update(tags)
    attempts = state.setdefault('attempts', {})
    for tag in sorted(new_tags, key=version_key):
        if tag not in state['pending']:
            next_revision = state['reserved'].get(tag, 0) + 1
            chosen = revision if tag == manual_tag and revision is not None else next_revision
            if chosen < next_revision:
                raise ValueError(f'Revision already reserved/published for {tag}; use >= {next_revision}')
            state['reserved'][tag] = chosen
            state['pending'][tag] = {
                'tag': tag, 'version': tag.removeprefix('dsh-v'), 'sha': tags[tag],
                'revision': chosen, 'packaging_sha': packaging_sha,
            }
    for tag, job in state['pending'].items():
        recipe_changed = job['packaging_sha'] != packaging_sha
        explicit_revision = revision if tag == manual_tag else None
        if explicit_revision is not None:
            if explicit_revision != job['revision'] or recipe_changed:
                if explicit_revision <= state['reserved'].get(tag, 0):
                    raise ValueError('Cannot reuse a reserved revision for a different recipe')
                job['revision'] = explicit_revision
                state['reserved'][tag] = explicit_revision
        elif recipe_changed:
            # A different recipe may already have published this reserved tag
            # before a failed state write. Never reuse that immutable name.
            job['revision'] = state['reserved'][tag] + 1
            state['reserved'][tag] = job['revision']
        job['packaging_sha'] = packaging_sha
    jobs = sorted(state['pending'].values(), key=lambda j: version_key(j['tag']), reverse=True)
    jobs.sort(key=lambda job: attempts.get(job['tag'], 0))
    if manual_tag:
        jobs = [state['pending'][manual_tag]]
    selected = jobs[:limit]
    for job in selected:
        attempts[job['tag']] = attempts.get(job['tag'], 0) + 1
    return state, copy.deepcopy(selected)


def advances_latest(state, job):
    current = state.get('latest')
    return current is None or (version_key(job['tag']), job['revision']) > (
        version_key(current['tag']), current['revision'])


def reconcile_latest(state, registry_latest):
    """Recover when an alias push succeeded but the durable state write failed."""
    if registry_latest and advances_latest(state, registry_latest):
        state['latest'] = copy.deepcopy(registry_latest)


def complete(state, job, digest):
    if not DIGEST_RE.fullmatch(digest):
        raise ValueError('Invalid manifest digest')
    if state['pending'].get(job['tag']) != job:
        raise ValueError('Release plan changed while building')
    result = {**job, 'digest': digest}
    state['published'].setdefault(job['tag'], {})[str(job['revision'])] = result
    if advances_latest(state, job):
        state['latest'] = result
    del state['pending'][job['tag']]


def peel_tag(obj, request):
    for _ in range(10):
        if obj['type'] == 'commit' and SHA_RE.fullmatch(obj['sha']):
            return obj['sha']
        if obj['type'] != 'tag' or not SHA_RE.fullmatch(obj['sha']):
            raise ValueError('Tag does not resolve to a valid commit')
        obj = request('git/tags/' + obj['sha'])['object']
    raise ValueError('Excessively nested annotated tag')


class GitHub:
    def __init__(self, repo):
        self.repo = repo
        self.token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')

    def request(self, path, method='GET', data=None):
        headers = {'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'dsh-docker'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(f'https://api.github.com/repos/{self.repo}/{path}',
                      data=json.dumps(data).encode() if data is not None else None,
                      headers=headers, method=method)
        with urlopen(req, timeout=60) as response:
            return json.load(response)

    def tags(self):
        result = {}
        for ref in self.request('git/matching-refs/tags/dsh-v'):
            tag = ref['ref'].removeprefix('refs/tags/')
            try:
                version_key(tag)
            except ValueError:
                continue
            result[tag] = peel_tag(ref['object'], self.request)
        return result

    def load_state(self):
        try:
            result = self.request(f'contents/state.json?ref={STATE_BRANCH}')
        except HTTPError as exc:
            if exc.code != 404:
                raise
            try:
                self.request(f'git/ref/heads/{STATE_BRANCH}')
            except HTTPError as branch_error:
                if branch_error.code == 404:
                    return None, None
                raise
            raise ValueError('State branch exists but state.json is missing') from exc
        return json.loads(base64.b64decode(result['content'])), result['sha']

    def save_state(self, state, blob_sha):
        content = json.dumps(state, indent=2, sort_keys=True) + '\n'
        message = 'chore: record upstream image release state'
        if blob_sha:
            response = self.request('contents/state.json', 'PUT', {
                'message': message, 'branch': STATE_BRANCH, 'sha': blob_sha,
                'content': base64.b64encode(content.encode()).decode(),
            })
            return response['content']['sha']
        tree = self.request('git/trees', 'POST', {'tree': [{
            'path': 'state.json', 'mode': '100644', 'type': 'blob', 'content': content,
        }]})
        commit = self.request('git/commits', 'POST', {
            'message': message, 'tree': tree['sha'], 'parents': [],
        })
        self.request('git/refs', 'POST', {
            'ref': f'refs/heads/{STATE_BRANCH}', 'sha': commit['sha'],
        })
        return self.load_state()[1]


def artifacts_complete(job, artifacts):
    for arch in ('amd64', 'arm64'):
        artifact = artifacts.get(arch, {})
        if any(artifact.get(key) != value for key, value in job.items()):
            return False
        if artifact.get('arch') != arch or not DIGEST_RE.fullmatch(artifact.get('digest', '')):
            return False
    return True


def docker(*args):
    return subprocess.run(['docker', *args], check=True, text=True, capture_output=True).stdout


def regctl(*args):
    try:
        return subprocess.run(['regctl', *args], check=True, text=True, capture_output=True).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f'OCI index publication failed: {exc.stderr.strip()}') from exc


def inspect_manifest(ref, optional=False):
    try:
        return json.loads(docker('buildx', 'imagetools', 'inspect', ref, '--format', '{{json .Manifest}}'))
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.lower()
        if optional and ('not found' in message or 'manifest unknown' in message):
            return None
        raise RuntimeError(f'Cannot inspect {ref}: {exc.stderr.strip()}') from exc


def read_registry_latest():
    manifest = inspect_manifest(f'{IMAGE}:latest', optional=True)
    if not manifest:
        return None
    raw = json.loads(docker('buildx', 'imagetools', 'inspect', f"{IMAGE}@{manifest['digest']}", '--raw'))
    annotations = raw.get('annotations', {})
    version = annotations.get('org.opencontainers.image.version', '')
    match = re.fullmatch(r'(.+)-r([1-9][0-9]*)', version)
    if not match:
        # Legacy images from before this release system have no revision metadata.
        return None
    tag = 'dsh-v' + match[1]
    version_key(tag)
    return {'tag': tag, 'version': match[1], 'revision': int(match[2]),
            'digest': manifest['digest'],
            'sha': annotations.get('io.dsh-docker.upstream-sha', ''),
            'packaging_sha': annotations.get('io.dsh-docker.packaging-sha', '')}


def publish(job, artifacts, state):
    immutable = f"{IMAGE}:{job['version']}-r{job['revision']}"
    expected_annotations = {
        'io.dsh-docker.upstream-sha': job['sha'],
        'io.dsh-docker.upstream-tag': job['tag'],
        'io.dsh-docker.packaging-sha': job['packaging_sha'],
        'org.opencontainers.image.version': f"{job['version']}-r{job['revision']}",
    }
    existing = inspect_manifest(immutable, optional=True)
    if existing:
        raw = json.loads(docker('buildx', 'imagetools', 'inspect', immutable, '--raw'))
        if any(raw.get('annotations', {}).get(k) != v for k, v in expected_annotations.items()):
            raise ValueError(f'Immutable revision already exists with different metadata: {immutable}')
    else:
        # Buildx chooses a Docker list for all-Docker children and drops OCI
        # annotations. Create only the OCI index, preserving tested manifests
        # and their Docker-specific configuration (including Healthcheck).
        arguments = ['index', 'create', immutable,
                     '--media-type', 'application/vnd.oci.image.index.v1+json']
        for key, value in expected_annotations.items():
            arguments.extend(['--annotation', f'{key}={value}'])
        for arch in ('amd64', 'arm64'):
            arguments.extend(['--digest', artifacts[arch]['digest']])
        regctl(*arguments)
    manifest = inspect_manifest(immutable)
    digest = manifest['digest']
    raw = json.loads(docker('buildx', 'imagetools', 'inspect', immutable, '--raw'))
    if raw.get('mediaType') != 'application/vnd.oci.image.index.v1+json' or any(
            raw.get('annotations', {}).get(k) != v for k, v in expected_annotations.items()):
        raise ValueError(f'Published index metadata missing or invalid: {immutable}')
    platforms = {(m.get('platform', {}).get('os'), m.get('platform', {}).get('architecture'), m.get('digest'))
                 for m in raw.get('manifests', [])}
    if len(raw.get('manifests', [])) != 2 or {(os_name, arch) for os_name, arch, _ in platforms} != {
            ('linux', 'amd64'), ('linux', 'arm64')}:
        raise ValueError(f'Incomplete published manifest: {immutable}')
    expected_platforms = {('linux', arch, artifacts[arch]['digest']) for arch in ('amd64', 'arm64')}
    # A retry may rebuild different bytes from the same source (e.g. apt
    # updates). Reuse the original tested index when its identity matches;
    # never replace an immutable revision with the retry's new image bytes.
    if not existing and platforms != expected_platforms:
        raise ValueError(f'Published manifest differs from tested architectures: {immutable}')
    reconcile_latest(state, read_registry_latest())
    args = ['buildx', 'imagetools', 'create', '--tag', f"{IMAGE}:{job['version']}",
            '--tag', f"{IMAGE}:{job['tag']}"]
    if advances_latest(state, job):
        args.extend(['--tag', f'{IMAGE}:latest'])
    args.append(f'{IMAGE}@{digest}')
    docker(*args)
    # Verify each alias before marking the queue entry complete.
    aliases = [job['version'], job['tag']]
    if advances_latest(state, job):
        aliases.append('latest')
    for alias in aliases:
        if inspect_manifest(f'{IMAGE}:{alias}')['digest'] != digest:
            raise ValueError(f'Alias verification failed: {alias}')
    return digest


def prepare(args):
    github = GitHub(os.environ['GITHUB_REPOSITORY'])
    previous, blob_sha = github.load_state()
    packaging_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    state, jobs = plan(previous, GitHub(UPSTREAM).tags(), packaging_sha,
                       manual_tag=args.tag or None, revision=args.revision)
    if state != previous:
        github.save_state(state, blob_sha)
    Path('release-plan.json').write_text(json.dumps(jobs, indent=2) + '\n')
    matrix = {'include': [{**job, 'arch': arch, 'runner': runner}
                          for job in jobs for arch, runner in
                          [('amd64', 'ubuntu-24.04'), ('arm64', 'ubuntu-24.04-arm')]]}
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('matrix=' + json.dumps(matrix, separators=(',', ':')) + '\n')
        output.write('has_work=' + str(bool(jobs)).lower() + '\n')
        output.write('packaging_sha=' + packaging_sha + '\n')
    print(f'Planned {len(jobs)} release(s): ' + ', '.join(j['tag'] for j in jobs))


def finalize(args):
    github = GitHub(os.environ['GITHUB_REPOSITORY'])
    state, blob_sha = github.load_state()
    jobs = json.loads(Path(args.plan).read_text())
    failed = []
    for job in jobs:
        artifacts = {}
        for arch in ('amd64', 'arm64'):
            path = Path(args.artifacts) / f"{job['version']}-r{job['revision']}-{arch}.json"
            if path.exists():
                artifacts[arch] = json.loads(path.read_text())
        if not artifacts_complete(job, artifacts):
            failed.append(job['tag'])
            print(f"::warning::Both tested architectures are required for {job['tag']}; retained for retry")
            continue
        if state['pending'].get(job['tag']) != job:
            # A rerun of only the publish job after a successful state commit.
            prior = state['published'].get(job['tag'], {}).get(str(job['revision']))
            if prior and all(prior.get(k) == v for k, v in job.items()):
                continue
            raise ValueError('State changed since this release was planned')
        try:
            digest = publish(job, artifacts, state)
            complete(state, job, digest)
            blob_sha = github.save_state(state, blob_sha)
        except (ValueError, RuntimeError, subprocess.CalledProcessError, HTTPError) as exc:
            print(f"::error::Failed to publish {job['tag']}: {exc}")
            # A failed state write must not let later jobs use a stale blob SHA.
            state, blob_sha = github.load_state()
            failed.append(job['tag'])
            continue
        print(f"Published {IMAGE}:{job['version']}-r{job['revision']} @ {digest}")
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a') as out:
                out.write(f"- `{IMAGE}:{job['version']}-r{job['revision']}` — `{digest}`\n")
    if failed:
        raise RuntimeError('Unpublished releases remain pending: ' + ', '.join(failed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--tag', default='')
    prep.add_argument('--revision', type=int)
    final = sub.add_parser('finalize')
    final.add_argument('--plan', default='release-plan.json')
    final.add_argument('--artifacts', default='digests')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args)
    else:
        finalize(args)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, HTTPError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
