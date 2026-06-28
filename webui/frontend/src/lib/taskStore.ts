/**
 * 轻量全局 store(模块级单例 + 显式订阅)。
 *
 * 用途:把"流式任务"(ASR 分段/说话人分离、TTS 批量、Vision 分段)的状态与 fetch
 * 从页面组件里提到模块级单例。这样切换路由标签时,组件虽然卸载,但 store 与正在跑
 * 的 fetch 都还在;切回时组件重新订阅,实时进度与结果原样恢复——不会"切走就中断"。
 *
 * 订阅用经典的 useState + useEffect:组件挂载时订阅、并立即同步一次(捕获切走期间
 * 累积的更新);任一次 set 都会通知所有当前挂载的订阅者重渲染。比 useSyncExternalStore
 * 在"卸载→重挂"场景更稳,不会出现重挂后 set 不再触发追加渲染的边界问题。
 *
 * 每页一个 store 实例 + 对应的 run 函数(在各自 *.store.ts 里),组件只负责订阅渲染。
 */
import { useEffect, useState } from "react";

export interface Store<S> {
  get: () => S;
  /** 传对象做浅合并(像 setState),传函数做整体替换 */
  set: (patch: Partial<S> | ((prev: S) => S)) => void;
  subscribe: (listener: () => void) => () => void;
  /** React hook:订阅并返回当前快照 */
  use: () => S;
}

export function createStore<S extends object>(initial: S): Store<S> {
  let state = initial;
  const listeners = new Set<() => void>();

  const get = () => state;

  const set: Store<S>["set"] = (patch) => {
    state =
      typeof patch === "function"
        ? (patch as (prev: S) => S)(state)
        : { ...state, ...patch };
    // 复制一份再遍历,避免监听器在回调中增删导致迭代异常
    for (const l of Array.from(listeners)) l();
  };

  const subscribe: Store<S>["subscribe"] = (listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  };

  const use = () => {
    const [snapshot, setSnapshot] = useState(state);
    useEffect(() => {
      const sync = () => setSnapshot(get());
      const unsub = subscribe(sync);
      // 订阅建立前 store 可能已更新(如切走期间累积的流式进度),立即同步一次,
      // 之后每次 set 通过 sync 触发重渲染。
      sync();
      return unsub;
    }, []);
    return snapshot;
  };

  return { get, set, subscribe, use };
}
