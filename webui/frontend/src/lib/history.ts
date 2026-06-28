/**
 * 通用 localStorage 历史记录工具。
 * createHistory(key, max) 返回 { load, persist } 两个操作,
 * 封装 JSON 读(失败返回 [])、写(截断到 max 条)。
 */
export function createHistory<T>(
  key: string,
  max: number,
): { load(): T[]; persist(items: T[]): void } {
  return {
    load(): T[] {
      try {
        const raw = localStorage.getItem(key);
        return raw ? (JSON.parse(raw) as T[]) : [];
      } catch {
        return [];
      }
    },

    persist(items: T[]): void {
      try {
        localStorage.setItem(key, JSON.stringify(items.slice(0, max)));
      } catch {
        // localStorage 满或被禁,直接吞
      }
    },
  };
}
