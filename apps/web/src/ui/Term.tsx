import type { ReactNode } from "react";
import { Tooltip } from "./Tooltip";
import { glossaryEntry } from "./glossary";

// 页面内联术语解释（roadmap Phase 3.3）。
//
// 用法：<Term id="capsule">证据包</Term>
//
// 可见文案由调用方决定（各页对同一概念的中文措辞可能不同），悬浮/聚焦时才展开
// 术语表里的定义与英文原名 —— 所以正文保持干净，需要解释的人随时能拿到解释。
//
// 未知 id 一律原样渲染 children，不包一层提示、不编造定义：缺一句解释是诚实的，
// 编一句错的解释会把用户带偏。未知 id 属于开发者失误，由 glossary.test.ts 锁定。
export interface TermProps {
  id: string;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}

export function Term(props: TermProps): JSX.Element {
  const { id, children, side = "top" } = props;
  const entry = glossaryEntry(id);
  if (!entry) return <>{children}</>;

  return (
    <span className="ui-term">
      <Tooltip
        side={side}
        content={
          <span className="ui-term-tip">
            <strong className="ui-term-label">{entry.label}</strong>
            {entry.definition}
            {entry.en ? <span className="ui-term-en">{entry.en}</span> : null}
          </span>
        }
      >
        <span className="ui-term-text" tabIndex={0}>
          {children}
        </span>
      </Tooltip>
    </span>
  );
}
