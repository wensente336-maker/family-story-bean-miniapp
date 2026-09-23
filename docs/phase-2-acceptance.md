# 阶段 2 验收记录：技术底座与数据契约

验收日期：2026-09-17  
确认日期：2026-09-18  
阶段状态：已确认

## 目的

建立 API、异步 Worker、PostgreSQL、Redis、小程序数据服务之间的统一工程底座，并冻结后续登录、上传、转写与生成流程使用的数据契约。

## 交付物

- FastAPI 服务、统一成功/错误响应及请求追踪 ID。
- Celery Worker 与 Redis 契约烟雾任务。
- PostgreSQL 九张首版数据表及可逆迁移。
- OpenAPI、故事板 JSON Schema、任务状态机和 API 约定。
- 小程序 Mock 数据服务、字段适配层和首页接入。
- Python 3.12 环境模板、Docker Compose 与启动说明。

## 验收结果

- Python 自动化测试：12 项通过。
- 小程序数据契约测试：2 项通过。
- JavaScript 与 JSON 语法/格式校验：通过。
- API 真实进程：`/health` 和 `/v1/mock/home` 均返回 HTTP 200。
- Worker 真实进程：通过 Redis 返回 `CONTRACT_OK`，pipeline 版本为 `storyboard-v1`。
- PostgreSQL：迁移正向执行成功、全量回滚后 public 表为 0、再次执行成功。
- Redis：健康检查通过，`PING` 返回 `PONG`。
- 核心内容实体：具有 UUID、家庭归属、创建与更新时间字段。

## 当前边界与已知问题

- 微信登录、真实鉴权和家庭隔离属于阶段 3，本阶段仅冻结鉴权头约定。
- 真实对象存储上传属于阶段 4，本地配置先使用可替换的兼容端点占位。
- ASR、高光发现、漫画和播客生成尚未实现，按阶段 6–9 开发。
- 测试存在一条第三方 Starlette `TestClient` 的弃用警告，不影响测试结果或运行。
- 小程序开发环境默认启用内置 Mock；切换真实 API 只需修改环境配置。

## 门禁结论

阶段 2 完成标准已满足，并已获得用户明确确认。阶段 3 可以开始。
