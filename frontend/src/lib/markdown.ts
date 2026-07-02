// Parse markdown to sanitized HTML for rendering LLM output in the chat UI.
// Pure and UI-free so it is unit-testable (see markdown.test.ts). LLM output
// is untrusted, so the marked-produced HTML is always run through DOMPurify.
import DOMPurify from 'dompurify';
import { marked } from 'marked';

marked.setOptions({ gfm: true, breaks: true });

// Force links to open in a new tab and drop the opener reference.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

export function renderMarkdown(md: string | null): string {
  if (!md) return '';
  const rawHtml = marked.parse(md, { async: false }) as string;
  return DOMPurify.sanitize(rawHtml);
}
