# Agent Note: sitemap 使用页面自身的实质内容修改日期

Status: implemented

## Problem

组织站 sitemap 没有逐页 lastmod。文章已有 published_on、updated_on，指南和比较页已有 checked_on，并把修改日期写入本页 Article / TechArticle JSON-LD。用构建时间会让没有改动的页面也宣称更新。

## Decision

finalizeSite 从目标 URL 自己的 Article / TechArticle dateModified 读取日期并写入 sitemap，不从其他节点、datePublished、文件 mtime 或构建时钟推断。日期缺失的页面省略 lastmod。校验有效的 YYYY-MM-DD 日历日期及同页日期一致性。保留已有发布日期、HTML、canonical、hreflang 与路由。

## Alternatives considered

- 使用构建时间：实现简单，但无法证明页面实质内容改变，舍弃。
- sitemap 另建一份日期表：可覆盖全部页面，但会与页面 JSON-LD 和可见日期产生第三份维护源，舍弃。

## Consequences

新增 lastmod 与既有页面 dateModified 一致；无日期页面不会填虚构日期。维护者仍须在实质正文、方法、来源或重要链接修改时更新对应 updated_on / checked_on，保留 published_on；例行构建和纯排版调整不刷新日期。读取每个已生成页面增加少量构建 I/O，非法或冲突日期使构建失败。lastmod 是爬取提示，不保证索引或排名。

日期语义依据：[Google sitemap 文档](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)。
