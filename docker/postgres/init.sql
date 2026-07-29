-- PostgreSQL 扩展初始化。容器首次启动时自动执行。
CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector：向量相似度去重
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- trigram：标题模糊匹配与中文兜底搜索
CREATE EXTENSION IF NOT EXISTS btree_gin;   -- GIN 复合索引
