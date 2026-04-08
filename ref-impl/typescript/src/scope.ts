import { Scope, ScopeKind } from "./models.js";

/**
 * Normalize a file path:
 * - Remove leading ./
 * - Collapse multiple /
 * - Remove trailing /
 */
function normalizePath(path: string): string {
  // Remove leading ./
  let normalized = path.replace(/^\.\//, "");
  // Collapse multiple slashes
  normalized = normalized.replace(/\/+/g, "/");
  // Remove trailing slash (except for root)
  if (normalized !== "/" && normalized.endsWith("/")) {
    normalized = normalized.slice(0, -1);
  }
  return normalized;
}

/**
 * Check if two string sets have any intersection
 */
function setsIntersect(setA: string[], setB: string[]): boolean {
  const bSet = new Set(setB);
  for (const item of setA) {
    if (bSet.has(item)) {
      return true;
    }
  }
  return false;
}

/**
 * Check if two resources overlap (with path normalization)
 */
function resourcesOverlap(filesA: string[], filesB: string[]): boolean {
  const normalizedA = filesA.map(normalizePath);
  const normalizedB = filesB.map(normalizePath);
  return setsIntersect(normalizedA, normalizedB);
}

/**
 * Check if two entity sets overlap (exact match)
 */
function entitiesOverlap(entitiesA: string[], entitiesB: string[]): boolean {
  return setsIntersect(entitiesA, entitiesB);
}

/**
 * Check if two task id sets overlap (exact match)
 */
function taskIdsOverlap(tasksA: string[], tasksB: string[]): boolean {
  return setsIntersect(tasksA, tasksB);
}

/**
 * Detect if two scopes overlap
 * Returns true if there is any overlap, false if no overlap, conservative true for unknown kinds
 */
export function scopeOverlap(a: Scope, b: Scope): boolean {
  // Same kind comparison
  if (a.kind === b.kind) {
    switch (a.kind) {
      case ScopeKind.FILE_SET:
        if (a.resources && b.resources) {
          return resourcesOverlap(a.resources, b.resources);
        }
        break;
      case ScopeKind.ENTITY_SET:
        if (a.entities && b.entities) {
          return entitiesOverlap(a.entities, b.entities);
        }
        break;
      case ScopeKind.TASK_SET:
        if (a.task_ids && b.task_ids) {
          return taskIdsOverlap(a.task_ids, b.task_ids);
        }
        break;
    }
  }

  // Different kinds or unknown: conservative approach (assume overlap)
  return true;
}

/**
 * Check if *test* scope is fully contained within *container* scope.
 * Returns true when every item in test also appears in container.
 * For different scope kinds: conservative true (assume contained).
 */
export function scopeContains(container: Scope, test: Scope): boolean {
  if (container.kind !== test.kind) return true; // Conservative

  switch (container.kind) {
    case ScopeKind.FILE_SET: {
      const cSet = new Set((container.resources ?? []).map(normalizePath));
      return (test.resources ?? []).every((r) => cSet.has(normalizePath(r)));
    }
    case ScopeKind.ENTITY_SET: {
      const cSet = new Set(container.entities ?? []);
      return (test.entities ?? []).every((e) => cSet.has(e));
    }
    case ScopeKind.TASK_SET: {
      const cSet = new Set(container.task_ids ?? []);
      return (test.task_ids ?? []).every((t) => cSet.has(t));
    }
  }
  return true; // Unknown kind: conservative
}

/**
 * Check if scope is valid (has at least one non-empty set)
 */
export function isValidScope(scope: Scope): boolean {
  switch (scope.kind) {
    case ScopeKind.FILE_SET:
      return Array.isArray(scope.resources) && scope.resources.length > 0;
    case ScopeKind.ENTITY_SET:
      return Array.isArray(scope.entities) && scope.entities.length > 0;
    case ScopeKind.TASK_SET:
      return Array.isArray(scope.task_ids) && scope.task_ids.length > 0;
    default:
      return false;
  }
}
