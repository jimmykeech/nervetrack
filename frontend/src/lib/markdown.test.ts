// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
  it('returns empty string for null or empty input', () => {
    expect(renderMarkdown(null)).toBe('');
    expect(renderMarkdown('')).toBe('');
  });

  it('renders headings', () => {
    expect(renderMarkdown('## Hello')).toContain('<h2');
  });

  it('renders bold', () => {
    expect(renderMarkdown('**x**')).toContain('<strong>');
  });

  it('renders unordered lists', () => {
    const html = renderMarkdown('- a\n- b');
    expect(html).toContain('<ul>');
    expect((html.match(/<li>/g) ?? []).length).toBe(2);
  });

  it('renders fenced code blocks', () => {
    const html = renderMarkdown('```js\nconst a = 1;\n```');
    expect(html).toContain('<pre><code');
  });

  it('strips script tags (sanitization)', () => {
    const html = renderMarkdown('hello <script>alert(1)</script> world');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('alert(1)');
  });

  it('strips javascript: links (sanitization)', () => {
    const html = renderMarkdown('[click](javascript:alert(1))');
    expect(html).not.toContain('javascript:');
  });

  it('opens links safely in a new tab', () => {
    const html = renderMarkdown('[docs](https://example.com)');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
});
