# 新版阶段 8：MVP 发布门禁与回滚清单

## 1. 发布前检查

- [x] 阶段 1～7 已由产品逐阶段确认。
- [x] 后端单元、契约、集成、隐私和故障注入测试全量通过。
- [x] 前端单元测试和生产构建通过。
- [x] 30 次完整编排回放达到成功率和时延门槛。
- [x] 幽默、温馨、成长三类故事均通过事实与追溯校验。
- [x] 撤销、过期、跨家庭访问和公开字段白名单测试通过。
- [x] 灰度开关、监控接口、版本回退和测试分享清理接口就绪。
- [ ] 公网 HTTPS 域名及社交平台爬虫验证（本地 MVP 不具备公网条件）。

## 2. 灰度配置

后端环境变量：

```text
PODCAST_ROLLOUT_MODE=allowlist
PODCAST_ROLLOUT_USER_IDS=<测试用户 UUID，多个用逗号分隔>
PODCAST_CREATION_ENABLED=true
PODCAST_SHARING_ENABLED=true
```

前端环境变量：

```text
VITE_ENABLE_PODCAST_CREATION=true
```

放量顺序：影子验证 → 白名单 → 小范围灰度 → 全量 `open`。每次扩大范围前检查 `/v1/ops/podcast-metrics`。

## 3. 立即停止条件

出现以下任意情况，停止新增和分享：

- 跨家庭读取成功一次。
- 分享撤销或过期后仍可重新取得媒体签名。
- 家庭原声与用户确认文本错配。
- 连续三次生成失败。
- 任意 P0/P1 缺陷。

## 4. 回滚步骤

1. 后端设置 `PODCAST_CREATION_ENABLED=false`、`PODCAST_SHARING_ENABLED=false`、`PODCAST_ROLLOUT_MODE=off` 并重启 API/Worker。
2. 前端设置 `VITE_ENABLE_PODCAST_CREATION=false` 后重新构建；新建入口隐藏。
3. 调用 `POST /v1/ops/podcast-shares/revoke-all-test`，请求体确认值为 `REVOKE_ALL_TEST_SHARES`。
4. 对质量异常的录音调用 `POST /v1/ops/recordings/{recording_id}/rollback`，确认值为 `ROLLBACK_TO_PREVIOUS_COMPLETED`。
5. 验证旧播客的成品页、签名播放地址和 MP3 下载仍可用。
6. 检查监控中的活动分享为 0，并记录回滚原因。

## 5. 恢复步骤

1. 修复后执行全量测试和 30 次回放门禁。
2. 先恢复 `allowlist`，观察成功率、P95、降级率和失败原因。
3. 无 P0/P1 且指标持续达标后恢复 `open`。

## 6. 本地运行地址

- Web：`http://127.0.0.1:4173/`
- API 文档：`http://127.0.0.1:8000/docs`
- 发布指标：`http://127.0.0.1:8000/v1/ops/podcast-metrics`
