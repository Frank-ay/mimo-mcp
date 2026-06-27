/**
 * 轻量全局 store(React 18 useSyncExternalStore)。
 *
 * 用途:把"流式任务"(ASR 分段/说话人分离、TTS 批量、Vision 分段)的状态与 fetch
 * 从页面组件里提到模块级单例。这样切换路由标签时,组件虽然卸载,但 store 与正在跑
 * 的 fetch 都还在;切回时组件重新订阅,实时进度与结果原样恢复——不会"切走就中断"。
 *
 * 每页一个 store 实例 + 对应的 run 函数(在各自 *.store.ts 里),组件只负责订阅渲染。
 */
import { useSyncExternalStore } from "react";

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
    for (const l of listeners) l();
  };

  const subscribe: Store<S>["subscribe"] = (listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  };

  const use = () => useSyncExternalStore(subscribe, get, get);

  return { get, set, subscribe, use };
}
