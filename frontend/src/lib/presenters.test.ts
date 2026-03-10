import { describe, expect, test } from 'vitest';
import { firstDomain } from './presenters';

describe('firstDomain', () => {
	test('skips placeholders loopback and code-like tokens', () => {
		expect(
			firstDomain([
				'0.0.0.0',
				'127.0.0.1',
				'${okta_domain}',
				'--collector.filesystem',
				'apihealth.statuscode',
				'api.example.com',
				'fonts.gstatic.com'
			])
		).toBe('api.example.com');
	});

	test('falls back when no external domain is present', () => {
		expect(firstDomain(['0.0.0.0', '127.0.0.1', '${accountid}.r2.cloudflarestorage.com`'])).toBe(
			'No external domain extracted'
		);
	});
});
