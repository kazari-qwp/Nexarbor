import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveComponents, ComponentRuntime} from '../adapters/harness/framework/components.js';

test('a disabled dependency closes explicitly enabled dependents without changing profile', () => {
  const catalog = new Map([
    ['base', {requires: []}],
    ['feature', {requires: ['base']}],
    ['consumer', {requires: ['feature']}],
  ]);
  const profile = {base: false, feature: true, consumer: true};
  assert.deepEqual([...resolveComponents(catalog, profile)], []);
  assert.equal(profile.feature, true);
  assert.deepEqual([...resolveComponents(catalog, {...profile, base: true})], ['base', 'feature', 'consumer']);
});

test('runtime removal releases dependent subscriptions and closes their execution gates', () => {
  const catalog = new Map([['base', {requires: []}], ['feature', {requires: ['base']}]]);
  const runtime = new ComponentRuntime({}, catalog, new Set(catalog.keys()));
  runtime.modules = new Map();
  runtime.runtime = {};
  const released = [];
  runtime.track('base', () => released.push('base'));
  runtime.track('feature', () => released.push('feature'));
  runtime.tools.set('retained_tool', 'feature');
  assert.equal(runtime.allows('retained_tool'), true);
  assert.deepEqual(runtime.disable('base'), ['feature', 'base']);
  assert.deepEqual(released, ['feature', 'base']);
  assert.equal(runtime.owner('retained_tool'), 'feature');
  assert.equal(runtime.allows('retained_tool'), false);
});
