"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cx } from "./ui";

export function Markdown({ children, dark, className }: { children: string; dark?: boolean; className?: string }) {
  return (
    <div className={cx("md", dark && "md-dark", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
