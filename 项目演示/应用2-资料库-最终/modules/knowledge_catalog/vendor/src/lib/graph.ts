import type { WikiPage } from './wiki.js';

export interface GraphNode {
  slug: string;
  title: string;
  tags: string[];
  linkCount: number;
  incomingCount: number;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export interface GraphAnalysis {
  nodes: GraphNode[];
  edges: GraphEdge[];
  orphans: string[];
  wantedPages: Map<string, string[]>;
  communities: Map<string, string[]>;
  hubs: GraphNode[];
}

/**
 * Build a link graph from wiki pages and analyze it.
 * Identifies communities using a simplified label propagation algorithm.
 */
export function analyzeGraph(pages: WikiPage[]): GraphAnalysis {
  const slugSet = new Set(pages.map(p => p.slug));
  const slugByName = new Map<string, string>();
  for (const p of pages) {
    slugByName.set(p.slug.toLowerCase(), p.slug);
    // Also map by filename (last segment)
    const parts = p.slug.split('/');
    const filename = parts[parts.length - 1].toLowerCase();
    if (!slugByName.has(filename)) {
      slugByName.set(filename, p.slug);
    }
    // Map aliases
    for (const alias of p.aliases) {
      slugByName.set(alias.toLowerCase(), p.slug);
    }
  }

  // Resolve a wikilink target to a slug
  function resolveLink(target: string): string | null {
    const lower = target.toLowerCase().replace(/\.md$/, '');
    return slugByName.get(lower) ?? null;
  }

  const edges: GraphEdge[] = [];
  const incoming = new Map<string, Set<string>>();

  for (const page of pages) {
    for (const link of page.wikilinks) {
      const resolved = resolveLink(link);
      if (resolved && resolved !== page.slug) {
        edges.push({ from: page.slug, to: resolved });
        if (!incoming.has(resolved)) incoming.set(resolved, new Set());
        incoming.get(resolved)!.add(page.slug);
      }
    }
  }

  // Wanted pages: wikilinks that don't resolve to any existing page
  const wantedPages = new Map<string, string[]>();
  for (const page of pages) {
    for (const link of page.wikilinks) {
      if (!resolveLink(link)) {
        if (!wantedPages.has(link)) wantedPages.set(link, []);
        wantedPages.get(link)!.push(page.slug);
      }
    }
  }

  // Build nodes
  const nodes: GraphNode[] = pages.map(p => ({
    slug: p.slug,
    title: p.title,
    tags: p.tags,
    linkCount: p.wikilinks.length,
    incomingCount: incoming.get(p.slug)?.size ?? 0,
  }));

  // Orphans: pages with no incoming links
  const orphans = nodes.filter(n => n.incomingCount === 0).map(n => n.slug);

  // Hubs: top pages by total connections (incoming + outgoing)
  const hubs = [...nodes]
    .sort((a, b) => (b.linkCount + b.incomingCount) - (a.linkCount + a.incomingCount))
    .slice(0, 10);

  // Community detection: simplified label propagation
  const communities = detectCommunities(pages, edges);

  return { nodes, edges, orphans, wantedPages, communities, hubs };
}

function detectCommunities(pages: WikiPage[], edges: GraphEdge[]): Map<string, string[]> {
  // Build adjacency list
  const adj = new Map<string, Set<string>>();
  for (const page of pages) {
    adj.set(page.slug, new Set());
  }
  for (const edge of edges) {
    adj.get(edge.from)?.add(edge.to);
    adj.get(edge.to)?.add(edge.from);
  }

  // Initialize: each node is its own community
  const labels = new Map<string, string>();
  for (const page of pages) {
    labels.set(page.slug, page.slug);
  }

  // Iterate label propagation (max 10 rounds)
  for (let round = 0; round < 10; round++) {
    let changed = false;
    const shuffled = [...pages].sort(() => Math.random() - 0.5);

    for (const page of shuffled) {
      const neighbors = adj.get(page.slug);
      if (!neighbors || neighbors.size === 0) continue;

      // Count neighbor labels
      const labelCounts = new Map<string, number>();
      for (const neighbor of neighbors) {
        const label = labels.get(neighbor)!;
        labelCounts.set(label, (labelCounts.get(label) ?? 0) + 1);
      }

      // Pick most frequent label
      let maxLabel = labels.get(page.slug)!;
      let maxCount = 0;
      for (const [label, count] of labelCounts) {
        if (count > maxCount) {
          maxCount = count;
          maxLabel = label;
        }
      }

      if (labels.get(page.slug) !== maxLabel) {
        labels.set(page.slug, maxLabel);
        changed = true;
      }
    }

    if (!changed) break;
  }

  // Group by label
  const communities = new Map<string, string[]>();
  for (const [slug, label] of labels) {
    if (!communities.has(label)) communities.set(label, []);
    communities.get(label)!.push(slug);
  }

  // Filter out single-node communities
  for (const [label, members] of communities) {
    if (members.length <= 1) communities.delete(label);
  }

  return communities;
}
