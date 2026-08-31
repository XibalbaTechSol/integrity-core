import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Boxes, ChevronDown, ChevronRight, CircleHelp, Copy, ExternalLink, FileText, GitBranch, Layers3, Menu, Search, ShieldCheck, X } from 'lucide-react';
import wikiData from '../generated/wiki-data.json';
import './WikiPage.css';

type WikiPageRecord = (typeof wikiData.pages)[number];
type TocHeading = { id: string; title: string; level: 2 | 3 };
type WikiNavigate = (page: WikiPageRecord, heading?: string) => void;

let mermaidReady: Promise<(typeof import('mermaid'))['default']> | null = null;

function loadMermaid() {
  if (!mermaidReady) {
    mermaidReady = import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'dark',
        themeVariables: {
          background: '#0b1723',
          primaryColor: '#172b3c',
          primaryTextColor: '#edf3f8',
          primaryBorderColor: '#c8a96b',
          lineColor: '#8293a2',
          secondaryColor: '#102232',
          tertiaryColor: '#0f1d2a',
        },
      });
      return mermaid;
    });
  }
  return mermaidReady;
}

function MermaidDiagram({ source }: { source: string }) {
  const reactId = useId();
  const [svg, setSvg] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const render = async () => {
      try {
        const mermaid = await loadMermaid();
        const id = `wiki-mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`;
        const result = await mermaid.render(id, source);
        if (!cancelled) setSvg(result.svg);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Unable to render diagram');
      }
    };
    render();
    return () => { cancelled = true; };
  }, [reactId, source]);

  if (error) return <div className="wiki-diagram-error" role="alert"><strong>Diagram could not be rendered.</strong><span>{error}</span><pre><code>{source}</code></pre></div>;
  if (!svg) return <div className="wiki-diagram-loading" role="status">Rendering diagram…</div>;
  return <figure className="wiki-diagram" aria-label="Protocol diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}

const categoryMeta = {
  overview: { label: 'Overview', icon: ShieldCheck },
  concepts: { label: 'Concepts', icon: BookOpen },
  entities: { label: 'Entities', icon: Boxes },
  architecture: { label: 'Architecture', icon: Layers3 },
  guides: { label: 'Guides', icon: FileText },
  queries: { label: 'Open queries', icon: CircleHelp },
} as const;

const protocolTocSections = [
  { number: '00', title: 'Start Here', pages: ['home', 'architecture/ecosystem-dependencies', 'concepts/integrity-specification', 'concepts/foundational-primitives'] },
  { number: '01', title: 'Identity & Agent Foundation', pages: ['concepts/agent-primitives', 'concepts/agent-memory', 'concepts/did', 'concepts/identity-ceiling', 'concepts/xibalba-agent-operating-model'] },
  { number: '02', title: 'Trust, Scoring & Telemetry', pages: ['concepts/ais', 'concepts/telemetry-ingestion', 'concepts/local-metrology', 'concepts/observability-vtl', 'concepts/ais-api-spec'] },
  { number: '03', title: 'Commitments & Cryptography', pages: ['concepts/bcc', 'concepts/merkle-batching', 'concepts/zkp'] },
  { number: '04', title: 'Compliance, Governance & Markets', pages: ['concepts/compliance-gate', 'concepts/smart-baa', 'concepts/integrity-market', 'concepts/governance'] },
  { number: '05', title: 'Implementation Packages', pages: ['entities/contracts', 'entities/integrity-oracle', 'entities/integrity-sdk', 'entities/integrity-cli', 'entities/bcc_middleware', 'entities/integrity-dashboard', 'entities/integrity-userapi', 'entities/integrity-zkp'] },
  { number: '06', title: 'Build, Test & Operate', pages: ['concepts/testing-strategy', 'guides/smart-contract-development', 'guides/multi-domain-guardrails-design', 'queries/gas-tracking'] },
  { number: '07', title: 'Roadmap & Research', pages: ['concepts/persistent-memory', 'concepts/cross-chain-spec', 'concepts/a2a-negotiation-spec', 'concepts/zk-ml-spec'] },
] as const;

function headingSlug(value: string) {
  return value.replace(/<[^>]+>/g, '').replace(/[`*_]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

function resolveWikiLink(currentPage: WikiPageRecord, href: string) {
  if (href.startsWith('#')) return { href: `/wiki?page=${encodeURIComponent(currentPage.id)}${href}`, page: currentPage, heading: href.slice(1) };
  if (/^(https?:|mailto:)/.test(href) || href.startsWith('/')) return { href };
  const resolved = new URL(href, `https://canonical.invalid/docs/wiki/${currentPage.path}`);
  const wikiPrefix = '/docs/wiki/';
  const guidesPrefix = '/docs/guides/';
  if (resolved.pathname.startsWith(wikiPrefix)) {
    const path = decodeURIComponent(resolved.pathname.slice(wikiPrefix.length));
    const page = wikiData.pages.find((candidate) => candidate.path === path);
    if (page) return { href: `/wiki?page=${encodeURIComponent(page.id)}${resolved.hash}`, page, heading: resolved.hash.slice(1) || undefined };
  }
  if (resolved.pathname.startsWith(guidesPrefix)) {
    const path = `../guides/${decodeURIComponent(resolved.pathname.slice(guidesPrefix.length))}`;
    const page = wikiData.pages.find((candidate) => candidate.path === path);
    if (page) return { href: `/wiki?page=${encodeURIComponent(page.id)}${resolved.hash}`, page, heading: resolved.hash.slice(1) || undefined };
  }
  const repositoryPath = resolved.pathname.replace(/^\//, '');
  return { href: `https://github.com/XibalbaTechSol/integrity-core/blob/main/${repositoryPath}${resolved.hash}` };
}

function inlineMarkup(value: string, currentPage: WikiPageRecord, onNavigate: WikiNavigate) {
  const segments = value.split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g);
  return segments.map((segment, index) => {
    const link = segment.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      const target = resolveWikiLink(currentPage, link[2]);
      return <a key={index} href={target.href} target={target.href.startsWith('http') ? '_blank' : undefined} rel={target.href.startsWith('http') ? 'noreferrer' : undefined} onClick={target.page ? (event) => { event.preventDefault(); onNavigate(target.page!, target.heading); } : undefined}>{link[1]}</a>;
    }
    if (segment.startsWith('**') && segment.endsWith('**')) return <strong key={index}>{segment.slice(2, -2)}</strong>;
    if (segment.startsWith('`') && segment.endsWith('`')) return <code key={index}>{segment.slice(1, -1)}</code>;
    return segment;
  });
}

function markdownList(items: Array<{ text: string; depth: number }>, key: string, currentPage: WikiPageRecord, onNavigate: WikiNavigate) {
  const roots: Array<{ text: string; children: string[] }> = [];
  for (const item of items) {
    if (item.depth && roots.length) roots[roots.length - 1].children.push(item.text);
    else roots.push({ text: item.text, children: [] });
  }
  return <ul key={key}>{roots.map((item, index) => <li key={index}>
    {inlineMarkup(item.text, currentPage, onNavigate)}
    {item.children.length ? <ul>{item.children.map((child, childIndex) => <li key={childIndex}>{inlineMarkup(child, currentPage, onNavigate)}</li>)}</ul> : null}
  </li>)}</ul>;
}

function splitTableRow(row: string) {
  const trimmed = row.trim();
  const withoutEdges = trimmed.replace(/^\|/, '').replace(/\|$/, '');
  return withoutEdges.split('|').map((cell) => cell.trim());
}

function isTableSeparator(row: string) {
  return splitTableRow(row).every((cell) => /^:?-{3,}:?$/.test(cell));
}

function markdownTable(rows: string[], key: string, currentPage: WikiPageRecord, onNavigate: WikiNavigate) {
  if (rows.length < 2 || !isTableSeparator(rows[1])) {
    return <p key={key}>{inlineMarkup(rows.join(' '), currentPage, onNavigate)}</p>;
  }

  const headers = splitTableRow(rows[0]);
  const bodyRows = rows.slice(2).map(splitTableRow);

  return <div className="wiki-table-wrap" key={key}>
    <table>
      <thead>
        <tr>{headers.map((header, index) => <th key={index}>{inlineMarkup(header, currentPage, onNavigate)}</th>)}</tr>
      </thead>
      <tbody>
        {bodyRows.map((row, rowIndex) => <tr key={rowIndex}>
          {headers.map((_, cellIndex) => <td key={cellIndex}>{inlineMarkup(row[cellIndex] || '', currentPage, onNavigate)}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}

function getHeadings(body: string): TocHeading[] {
  const counts = new Map<string, number>();
  return [...body.matchAll(/^(##|###)\s+(.+)$/gm)].filter((match) => match[2].replace(/[`*_]/g, '').toLowerCase() !== 'table of contents').map((match) => {
    const title = match[2].replace(/[`*_]/g, '');
    const base = headingSlug(title);
    const count = counts.get(base) || 0;
    counts.set(base, count + 1);
    return { id: count ? `${base}-${count}` : base, title, level: match[1].length as 2 | 3 };
  });
}

function MarkdownArticle({ body, currentPage, onNavigate }: { body: string; currentPage: WikiPageRecord; onNavigate: WikiNavigate }) {
  const lines = body.split('\n');
  const nodes: React.ReactNode[] = [];
  let paragraph: string[] = [];
  let list: Array<{ text: string; depth: number }> = [];
  let quote: string[] = [];
  let table: string[] = [];
  let code: string[] | null = null;
  let codeLanguage = '';
  const headingCounts = new Map<string, number>();
  const flush = () => {
    if (paragraph.length) nodes.push(<p key={`p-${nodes.length}`}>{inlineMarkup(paragraph.join(' '), currentPage, onNavigate)}</p>);
    if (list.length) nodes.push(markdownList(list, `l-${nodes.length}`, currentPage, onNavigate));
    if (quote.length) nodes.push(<blockquote key={`q-${nodes.length}`}>{inlineMarkup(quote.join(' '), currentPage, onNavigate)}</blockquote>);
    if (table.length) nodes.push(markdownTable(table, `t-${nodes.length}`, currentPage, onNavigate));
    paragraph = []; list = []; quote = []; table = [];
  };
  lines.forEach((line) => {
    if (line.startsWith('```')) {
      if (code) {
        const source = code.join('\n');
        nodes.push(codeLanguage === 'mermaid'
          ? <MermaidDiagram key={`c-${nodes.length}`} source={source} />
          : <pre key={`c-${nodes.length}`}><code>{source}</code></pre>);
        code = null; codeLanguage = '';
      }
      else { flush(); code = []; codeLanguage = line.slice(3).trim().toLowerCase(); }
      return;
    }
    if (code) { code.push(line); return; }
    const heading = line.match(/^(#{2,4})\s+(.+)$/);
    if (heading) {
      flush(); const level = heading[1].length; const base = headingSlug(heading[2]);
      const count = headingCounts.get(base) || 0; headingCounts.set(base, count + 1); const id = count ? `${base}-${count}` : base;
      if (level === 2) nodes.push(<h2 id={id} key={id}>{inlineMarkup(heading[2], currentPage, onNavigate)}</h2>);
      else nodes.push(<h3 id={id} key={id}>{inlineMarkup(heading[2], currentPage, onNavigate)}</h3>);
    } else if (/^\s*[-*]\s+/.test(line)) {
      const indent = line.match(/^\s*/)?.[0].length || 0;
      if (paragraph.length || quote.length || table.length) flush();
      list.push({ text: line.replace(/^\s*[-*]\s+/, ''), depth: Math.floor(indent / 2) });
    }
    else if (line.startsWith('>')) { if (table.length || list.length) flush(); paragraph = []; quote.push(line.replace(/^>\s?/, '')); }
    else if (line.startsWith('|')) { if (paragraph.length || list.length || quote.length) flush(); table.push(line); }
    else if (!line.trim()) flush();
    else if (!/^---+$/.test(line)) paragraph.push(line.trim());
  });
  flush();
  return <>{nodes}</>;
}

export default function WikiPage() {
  const requestedPage = new URLSearchParams(window.location.search).get('page');
  const home = wikiData.pages.find((page) => page.id === 'home') || wikiData.pages.find((page) => page.id === 'concepts/foundational-primitives') || wikiData.pages[0];
  const initial = wikiData.pages.find((page) => page.id === requestedPage) || home;
  const [active, setActive] = useState<WikiPageRecord>(initial);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [tocOpen, setTocOpen] = useState(false);
  const [expandedPages, setExpandedPages] = useState<Set<string>>(() => new Set([initial.id]));
  const [activeHeading, setActiveHeading] = useState('article-top');
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(() => new Set());
  const searchRef = useRef<HTMLInputElement>(null);
  const lastSynced = useMemo(() => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(wikiData.generatedAt)), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); setSearchOpen(true); setTimeout(() => searchRef.current?.focus(), 0);
      }
      if (event.key === 'Escape') setSearchOpen(false);
    };
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey);
  }, []);

  const results = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    if (!normalized) return wikiData.pages.slice(0, 6);
    return wikiData.pages.filter((page) => `${page.title} ${page.excerpt} ${page.tags.join(' ')}`.toLowerCase().includes(normalized)).slice(0, 8);
  }, [query]);
  const headings = useMemo(() => getHeadings(active.body), [active.body]);
  const masterHeadings = useMemo(() => new Map(wikiData.pages.map((page) => [page.id, getHeadings(page.body).filter((heading) => heading.title.toLowerCase() !== 'table of contents')])), []);
  const pageById = useMemo(() => new Map(wikiData.pages.map((page) => [page.id, page])), []);
  const orderedTocPages = useMemo(() => {
    const seen = new Set<string>();
    const ordered: WikiPageRecord[] = [];
    protocolTocSections.forEach((section) => section.pages.forEach((pageId) => {
      const page = pageById.get(pageId);
      if (page && !seen.has(page.id)) { seen.add(page.id); ordered.push(page); }
    }));
    wikiData.pages.forEach((page) => { if (!seen.has(page.id)) ordered.push(page); });
    return ordered;
  }, [pageById]);
  const activeIndex = useMemo(() => orderedTocPages.findIndex((page) => page.id === active.id), [active.id, orderedTocPages]);
  const previousPage = activeIndex > 0 ? orderedTocPages[activeIndex - 1] : null;
  const nextPage = activeIndex >= 0 && activeIndex < orderedTocPages.length - 1 ? orderedTocPages[activeIndex + 1] : null;

  useEffect(() => {
    setActiveHeading('article-top');
    setCollapsedSections(new Set());
    const elements = headings.map((heading) => document.getElementById(heading.id)).filter((element): element is HTMLElement => Boolean(element));
    if (!elements.length) return;
    let frame = 0;
    const updateActiveHeading = () => {
      frame = 0;
      let current = 'article-top';
      for (const element of elements) {
        if (element.getBoundingClientRect().top <= 118) current = element.id;
        else break;
      }
      setActiveHeading(current);
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(updateActiveHeading); };
    updateActiveHeading();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => { window.removeEventListener('scroll', onScroll); if (frame) cancelAnimationFrame(frame); };
  }, [active.id, headings]);

  const selectPage = (page: WikiPageRecord, heading?: string) => {
    setActive(page);
    setActiveHeading(heading || 'article-top');
    setExpandedPages((current) => {
      if (current.has(page.id)) return current;
      const next = new Set(current); next.add(page.id); return next;
    });
    setSearchOpen(false); setQuery(''); setNavOpen(false); setTocOpen(false);
    history.replaceState(null, '', `/wiki?page=${encodeURIComponent(page.id)}${heading ? `#${heading}` : ''}`);
    if (heading) requestAnimationFrame(() => requestAnimationFrame(() => {
      document.getElementById(heading)?.scrollIntoView({ behavior: 'auto', block: 'start' });
      setActiveHeading(heading);
    }));
    else window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const togglePageOutline = (pageId: string) => setExpandedPages((current) => {
    const next = new Set(current); if (next.has(pageId)) next.delete(pageId); else next.add(pageId); return next;
  });
  const visitHeading = (id: string) => {
    setActiveHeading(id); setTocOpen(false); history.replaceState(null, '', `/wiki?page=${encodeURIComponent(active.id)}#${id}`);
    if (id === 'article-top') window.scrollTo({ top: 0, behavior: 'smooth' });
    else document.getElementById(id)?.scrollIntoView({ behavior: 'auto', block: 'start' });
    requestAnimationFrame(() => requestAnimationFrame(() => setActiveHeading(id)));
  };
  const toggleSection = (id: string) => setCollapsedSections((current) => {
    const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next;
  });

  return <div className="wiki-shell">
    <header className="wiki-topbar">
      <div className="wiki-brand"><a className="wiki-brand-link" href="/" aria-label="Go to Xibalba Solutions landing page"><img src="/logo.png" alt="Xibalba Solutions" /></a><time className="wiki-last-synced" dateTime={wikiData.generatedAt}>Last updated {lastSynced}</time></div>
      <button className="wiki-search-trigger" onClick={() => { setSearchOpen(true); setTimeout(() => searchRef.current?.focus(), 0); }}><Search size={17} /><span>Search the protocol</span><kbd>⌘ K</kbd></button>
      <div className="wiki-top-actions"><a href={wikiData.source} target="_blank" rel="noreferrer" aria-label="Open source on GitHub"><GitBranch size={20} /></a><button onClick={() => setNavOpen(true)} aria-label="Open knowledge map"><Menu size={21} /></button></div>
    </header>

    <div className="wiki-grid">
      <aside className={`wiki-nav ${navOpen ? 'is-open' : ''}`}>
        <div className="wiki-mobile-rail-title"><span>Protocol TOC</span><button onClick={() => setNavOpen(false)} aria-label="Close protocol TOC"><X size={18} /></button></div>
        <div className="wiki-toc-heading"><p className="wiki-rail-label">Protocol TOC</p><span>{orderedTocPages.length} articles</span></div>
        <nav className="wiki-master-toc" aria-label="Protocol wiki table of contents">
          {protocolTocSections.map((section) => {
            const pages = section.pages.map((pageId) => pageById.get(pageId)).filter((page): page is WikiPageRecord => Boolean(page));
            if (!pages.length) return null;
            return <section className="wiki-toc-section" key={section.number}>
              <div className="wiki-toc-section-title"><span>{section.number}</span><strong>{section.title}</strong></div>
              <div className="wiki-nav-pages" id={`wiki-master-${section.number}`}>
                {pages.map((page) => {
                  const pageHeadings = masterHeadings.get(page.id) || [];
                  const expanded = expandedPages.has(page.id);
                  const CategoryIcon = categoryMeta[page.category as keyof typeof categoryMeta]?.icon || FileText;
                  return <div className="wiki-nav-page" key={page.id}>
                    <div className="wiki-nav-page-row">
                      <button aria-current={page.id === active.id ? 'page' : undefined} className={`wiki-page-link ${page.id === active.id ? 'active' : ''}`} onClick={() => selectPage(page)}><CategoryIcon size={13} /><span>{page.title}</span></button>
                      {pageHeadings.length ? <button className="wiki-page-toggle" aria-label={`${expanded ? 'Collapse' : 'Expand'} ${page.title} sections`} aria-expanded={expanded} onClick={() => togglePageOutline(page.id)}>{expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button> : null}
                    </div>
                    {expanded && pageHeadings.length ? <div className="wiki-nav-sections" aria-label={`${page.title} sections`}>
                      {pageHeadings.map((heading) => <button key={heading.id} className={`level-${heading.level} ${page.id === active.id && activeHeading === heading.id ? 'active' : ''}`} onClick={() => selectPage(page, heading.id)}>{heading.title}</button>)}
                    </div> : null}
                  </div>;
                })}
              </div>
            </section>;
          })}
        </nav>
      </aside>

      <main className="wiki-reader">
        <div className="wiki-mobile-controls"><button onClick={() => setNavOpen(true)}><Menu size={17} /> Protocol TOC</button><button onClick={() => setTocOpen(true)}>On this page <ChevronRight size={16} /></button></div>
        <article id="article-top">
          <div className="wiki-article-meta"><span>{categoryMeta[active.category as keyof typeof categoryMeta]?.label || active.category}</span><span>Updated {active.updated || 'from source'}</span></div>
          <h1>{active.title}</h1>
          <p className="wiki-deck">{active.excerpt}</p>
          <div className="wiki-rule" />
          <MarkdownArticle body={active.body} currentPage={active} onNavigate={selectPage} />
          <nav className="wiki-article-pagination" aria-label="Article navigation">
            {previousPage ? <button onClick={() => selectPage(previousPage)}><ArrowLeft size={17} /><span><small>Previous</small>{previousPage.title}</span></button> : <span />}
            {nextPage ? <button className="next" onClick={() => selectPage(nextPage)}><span><small>Next</small>{nextPage.title}</span><ArrowRight size={17} /></button> : <span />}
          </nav>
        </article>
      </main>

      <aside className={`wiki-toc ${tocOpen ? 'is-open' : ''}`}>
        <div className="wiki-mobile-rail-title"><span>On this page</span><button onClick={() => setTocOpen(false)}><X size={18} /></button></div>
        <p className="wiki-rail-label">On this page</p>
        <nav className="wiki-toc-tree" aria-label="Table of contents">
          <button className={activeHeading === 'article-top' ? 'active level-1' : 'level-1'} onClick={() => visitHeading('article-top')}>{active.title}</button>
          {headings.map((heading, index) => {
            const parent = heading.level === 3 ? [...headings.slice(0, index)].reverse().find((item) => item.level === 2) : null;
            if (parent && collapsedSections.has(parent.id)) return null;
            return <div className={`wiki-toc-row level-${heading.level}`} key={heading.id}>
              <button className={activeHeading === heading.id ? 'active' : ''} onClick={() => visitHeading(heading.id)}>{heading.title}</button>
              {heading.level === 2 && headings[index + 1]?.level === 3 ? <button className="wiki-toc-collapse" aria-label={`${collapsedSections.has(heading.id) ? 'Expand' : 'Collapse'} ${heading.title}`} aria-expanded={!collapsedSections.has(heading.id)} onClick={() => toggleSection(heading.id)}>{collapsedSections.has(heading.id) ? <ChevronRight size={13} /> : <ChevronDown size={13} />}</button> : null}
            </div>;
          })}
        </nav>
        <div className="wiki-provenance">
          <p className="wiki-rail-label">Source provenance</p>
          <a href={wikiData.source} target="_blank" rel="noreferrer"><GitBranch size={17} /> integrity-core/docs/wiki <ExternalLink size={13} /></a>
          <label>Git commit</label><button className="wiki-commit" onClick={() => navigator.clipboard?.writeText(wikiData.commit)}><code>{wikiData.commit}</code><Copy size={14} /></button>
          <label>Snapshot generated</label><time>{new Date(wikiData.generatedAt).toLocaleString()}</time>
          <div className="wiki-verified"><ShieldCheck size={20} /><div><strong>Canonical mirror</strong><span>Read-only snapshot of integrity-core/docs/wiki—the same files published to GitHub Wiki.</span></div></div>
        </div>
      </aside>
    </div>

    {searchOpen && <div className="wiki-search-backdrop" onMouseDown={() => setSearchOpen(false)}>
      <div className="wiki-command" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Search wiki">
        <div className="wiki-command-input"><Search size={20} /><input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search the protocol" /><button onClick={() => setSearchOpen(false)}><X size={18} /></button></div>
        <div className="wiki-command-results">{results.length ? results.map((page, index) => <button key={page.id} onClick={() => selectPage(page)}><div><strong>{page.title}</strong><span>{page.category} · {page.excerpt}</span></div><kbd>⌘ {index + 1}</kbd></button>) : <p>No knowledge matched that search.</p>}</div>
      </div>
    </div>}
  </div>;
}
