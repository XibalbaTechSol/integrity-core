import { execFileSync } from 'node:child_process';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const defaultSource = path.resolve(projectRoot, '..', 'docs', 'wiki');
const sourceRoot = path.resolve(process.env.INTEGRITY_WIKI_SOURCE || defaultSource);
const outputFile = path.join(projectRoot, 'src', 'generated', 'wiki-data.json');
const categories = ['concepts', 'entities', 'architecture', 'guides', 'queries'];
const categoryDirectories = {
  concepts: path.join(sourceRoot, 'concepts'),
  entities: path.join(sourceRoot, 'entities'),
  architecture: path.join(sourceRoot, 'architecture'),
  guides: path.join(sourceRoot, '..', 'guides'),
  queries: path.join(sourceRoot, 'queries'),
};
const categoryPathPrefix = {
  concepts: 'concepts',
  entities: 'entities',
  architecture: 'architecture',
  guides: '../guides',
  queries: 'queries',
};

function parseFrontmatter(markdown) {
  if (!markdown.startsWith('---\n')) return { metadata: {}, body: markdown };
  const end = markdown.indexOf('\n---\n', 4);
  if (end < 0) return { metadata: {}, body: markdown };
  const metadata = {};
  for (const line of markdown.slice(4, end).split('\n')) {
    const match = line.match(/^([a-z_]+):\s*(.*)$/);
    if (!match) continue;
    const value = match[2].trim();
    metadata[match[1]] = value.startsWith('[')
      ? value.slice(1, -1).split(',').map((item) => item.trim()).filter(Boolean)
      : value;
  }
  return { metadata, body: markdown.slice(end + 5).trim() };
}

function plainText(markdown) {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!?\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[`*#>|_-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

async function collectIndexTitles() {
  const titles = new Map();
  try {
    const index = await readFile(path.join(sourceRoot, 'WIKI_INDEX.md'), 'utf8');
    const linkPattern = /\[([^\]]+)\]\(([^)]+\.md)\)/g;
    for (const match of index.matchAll(linkPattern)) {
      titles.set(path.normalize(match[2]).replace(/\\/g, '/'), match[1]);
    }
  } catch { /* A partial source tree can still render generated pages. */ }
  return titles;
}

async function collectPages() {
  const pages = [];
  const indexTitles = await collectIndexTitles();
  const homePath = path.join(sourceRoot, 'index.md');
  try {
    const raw = await readFile(homePath, 'utf8');
    const { metadata, body: parsedBody } = parseFrontmatter(raw);
    const titleMatch = parsedBody.match(/^#\s+(.+)$/m);
    const body = parsedBody.replace(/^#\s+.+\n+/, '');
    pages.push({
      id: 'home',
      path: 'index.md',
      category: 'overview',
      title: metadata.title || titleMatch?.[1] || 'Integrity Protocol Wiki',
      updated: metadata.updated || '',
      confidence: metadata.confidence || 'high',
      tags: metadata.tags || ['overview'],
      sourceFiles: metadata.source_files || [],
      excerpt: plainText(body).slice(0, 190),
      body,
    });
  } catch { /* A mirror without a canonical home can still render articles. */ }
  for (const category of categories) {
    const directory = categoryDirectories[category];
    let entries = [];
    try { entries = await readdir(directory, { withFileTypes: true }); } catch { continue; }
    for (const entry of entries.filter((item) => item.isFile() && item.name.endsWith('.md'))) {
      const relativePath = `${categoryPathPrefix[category]}/${entry.name}`;
      const raw = await readFile(path.join(directory, entry.name), 'utf8');
      const { metadata, body } = parseFrontmatter(raw);
      const titleMatch = body.match(/^#\s+(.+)$/m);
      const fallbackTitle = entry.name.replace(/\.md$/, '').replace(/-/g, ' ');
      pages.push({
        id: `${category}/${entry.name.replace(/\.md$/, '')}`,
        path: relativePath,
        category,
        title: indexTitles.get(relativePath) || metadata.title || titleMatch?.[1] || fallbackTitle.replace(/\b\w/g, (letter) => letter.toUpperCase()),
        updated: metadata.updated || '',
        confidence: metadata.confidence || 'medium',
        tags: metadata.tags || [],
        sourceFiles: metadata.source_files || [],
        excerpt: plainText(body).slice(0, 190),
        body,
      });
    }
  }
  return pages.sort((a, b) => a.id === 'home' ? -1 : b.id === 'home' ? 1 : a.title.localeCompare(b.title));
}

let commit = process.env.INTEGRITY_WIKI_COMMIT || 'local';
let generatedAt = process.env.INTEGRITY_WIKI_UPDATED_AT || new Date(0).toISOString();
try {
  const repositoryRoot = path.resolve(sourceRoot, '..', '..');
  commit = execFileSync('git', ['-C', repositoryRoot, 'rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim();
  generatedAt = execFileSync('git', ['-C', repositoryRoot, 'show', '-s', '--format=%cI', 'HEAD'], { encoding: 'utf8' }).trim();
} catch { /* A downloaded wiki snapshot may not have git metadata. */ }

const pages = await collectPages();
await mkdir(path.dirname(outputFile), { recursive: true });
await writeFile(outputFile, `${JSON.stringify({
  generatedAt,
  source: 'https://github.com/XibalbaTechSol/integrity-core/tree/main/docs/wiki',
  commit,
  pages,
}, null, 2)}\n`);
console.log(`Synced ${pages.length} wiki pages from ${sourceRoot} -> ${outputFile}`);
