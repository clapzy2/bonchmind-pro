"use client";

import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders an LLM answer written in Markdown (Stage 7e). Summaries and chat
 * replies come back with #, **, lists and the occasional table; before this
 * they were shown as raw text in a <pre>, so the syntax leaked into the UI.
 *
 * Styling is done with explicit Tailwind classes per element (the project has
 * no @tailwindcss/typography plugin), tuned for the dark surfaces these
 * answers sit on. react-markdown does not use dangerouslySetInnerHTML and we
 * pass no raw-HTML plugin, so user/LLM content can't inject markup.
 */

type MarkdownProps = {
  children: string;
};

export function Markdown({ children }: MarkdownProps) {
  return (
    <div className="bm-markdown text-sm leading-7 text-slate-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => <h2 className="mt-5 mb-2 text-xl font-bold text-white first:mt-0" {...props} />,
          h2: (props) => <h2 className="mt-5 mb-2 text-lg font-bold text-white first:mt-0" {...props} />,
          h3: (props) => <h3 className="mt-4 mb-2 text-base font-bold text-white first:mt-0" {...props} />,
          h4: (props) => <h4 className="mt-4 mb-1 text-sm font-bold text-white first:mt-0" {...props} />,
          p: (props) => <p className="mb-3 last:mb-0" {...props} />,
          ul: (props) => <ul className="mb-3 ml-5 list-disc space-y-1 last:mb-0" {...props} />,
          ol: (props) => <ol className="mb-3 ml-5 list-decimal space-y-1 last:mb-0" {...props} />,
          li: (props) => <li className="leading-6" {...props} />,
          strong: (props) => <strong className="font-semibold text-white" {...props} />,
          em: (props) => <em className="italic" {...props} />,
          a: (props) => (
            <a className="text-brand underline underline-offset-2 hover:opacity-80" target="_blank" rel="noopener noreferrer" {...props} />
          ),
          blockquote: (props) => (
            <blockquote className="mb-3 border-l-2 border-white/20 pl-4 text-muted last:mb-0" {...props} />
          ),
          code: ({ className, ...props }: ComponentPropsWithoutRef<"code">) => {
            const isBlock = (className ?? "").includes("language-");
            if (isBlock) {
              return <code className="font-mono text-xs text-slate-200" {...props} />;
            }
            return <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-xs text-slate-100" {...props} />;
          },
          pre: (props) => (
            <pre className="mb-3 overflow-x-auto rounded-lg border border-white/10 bg-[#0d1117] p-3 last:mb-0" {...props} />
          ),
          hr: () => <hr className="my-4 border-white/10" />,
          table: (props) => (
            <div className="mb-3 overflow-x-auto last:mb-0">
              <table className="w-full border-collapse text-left text-xs" {...props} />
            </div>
          ),
          th: (props) => <th className="border border-white/10 bg-white/5 px-3 py-2 font-semibold text-white" {...props} />,
          td: (props) => <td className="border border-white/10 px-3 py-2 align-top" {...props} />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
