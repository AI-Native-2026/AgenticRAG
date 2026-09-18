# v2 09 admin 平台化

> 本节回答：怎么把"运维动作"变成"管理员能自助执行的工具"。

## 9.1 为什么需要 admin CLI

v2 把运维动作（建租户、配配额、看报表、跑回归）做成**一条命令**，
而不是让人去改代码/Mongo：
- **自助**：管理员不用懂代码
- **可重复**：同样的命令任何时候跑出同样结果
- **可审计**：谁执行了什么有据可查（日志）

生产上这一层是 Web 门户；v2 资源有限，**CLI 是门户的"最小替代"**，
接口设计（参数化、可脚本化）与门户一致。

## 9.2 CLI 清单与实现

```
scripts/admin/
├── create_tenant.py      # 建租户 + 配额
├── list_tenants.py       # 列出租户与配额
├── report.py             # 观测报表 + 告警
└── check_regression.py   # 评测回归门禁
```

### create_tenant.py（参数化）

```python
parser.add_argument("--tenant", required=True)
parser.add_argument("--tokens", type=int, default=100000, help="每日 token 预算")
parser.add_argument("--storage", type=int, default=10000, help="存储节点上限")

qm.create_tenant(args.tenant, quota_tokens_per_day=args.tokens,
                 quota_storage_nodes=args.storage)
```

**为什么参数化 + 默认值**：缺省就能跑（教学友好），改配额只加参数不动代码。
生产上这就是"自助门户的表单字段"。

### report.py（把观测变成人话）

```python
events = get_sink().read_all(days=args.days)
metrics = aggregate(events)
print(format_report(metrics))
hits = check(metrics, load_rules())
```

**为什么 CLI 直接读事件文件而不是调 API 的 /v1/metrics**：
管理员在服务器本机，直接读数据源更快更可靠；API 的 /metrics 是给
外部监控系统/负载均衡用的。两条路径共享同一套 aggregate/check 函数。

## 9.3 API 侧的管理能力（`/v1/metrics`）

```python
@app.get("/v1/metrics")
def metrics(request):
    user = _get_bearer(request)
    if user["role"] != "admin":
        raise AppError(403, "FORBIDDEN", "仅 admin 可查看指标")
    ...
```

**为什么 API 管理接口要校验 admin 角色**：
CLI 在服务器本机（信任），API 暴露给网络（不信任）。
角色校验防止"member 偷看全系统指标"——**同一数据，两条暴露路径，
安全边界不同**。

## 9.4 平台化的完整形态（v2 → 生产对照）

| 能力 | v2（CLI） | 生产（门户） |
|---|---|---|
| 建租户 | `create_tenant.py --tenant x` | 门户表单 + 审批流 |
| 配额调整 | CLI 参数 | 门户 + 变更审计 |
| 报表 | `report.py` | 看板 + 定时邮件 |
| 回归 | `check_regression.py` | CI 门禁自动阻断 |
| 自助接入 | 手动 | 上传文档→自动建索引/评测集/API key |

**演进路径**：CLI → 把命令包装成 HTTP 管理 API → 套一层前端页面 → 加审批/审计。
**v2 停在哪**：CLI + 管理 API 已具备"可脚本化、可审计"，够教学和使用。

## 9.5 运行与验证

```bash
# 建租户 + 列出
python scripts/admin/create_tenant.py --tenant tech --tokens 100000 --storage 10000
python scripts/admin/create_tenant.py --tenant finance --tokens 50000 --storage 5000
python scripts/admin/list_tenants.py

# 报表 + 告警
python scripts/admin/report.py --days 1
```

预期：
```
租户          每日token     存储节点上限
----------------------------------------
tech        100000       10000
finance     50000        5000
...
[告警] ⚠ generate_too_slow: ...（如果 p95 超阈值）
```

## 9.6 思考题

❓ 问题：CLI 和 API 管理接口为什么不合并成一个？
💡 为什么这么问：理解"信任边界"驱动的设计。
🔍 参考思路：CLI 在服务器本机执行（信任），可读文件、可跑脚本；
   API 暴露给网络（不信任），必须鉴权 + 限流。两条路径职责不同，
   共享核心函数但暴露方式不同。

❓ 问题：如果给 CLI 也加鉴权，会带来什么好处和成本？
💡 为什么这么问：运维安全的纵深。
🔍 参考思路：好处：多人共用服务器时防止误操作/越权；成本：CLI 也要
   管理 token/凭据，操作变繁琐。生产常用"堡垒机 + 命令白名单"方案。

❓ 问题：配额参数（tokens/storage）设成全局默认值有什么隐患？
💡 为什么这么问：配额默认值是"安全兜底"还是"越权口子"取决于值的大小。
🔍 参考思路：默认值太宽松 = 忘了设配额也等于没设；太紧 = 新租户被误伤。
   正确做法：默认值取"安全下限"，并强制显式设置关键配额。

---

**v2 结业**：至此你已掌握 Agentic RAG 的完整生产增强链路——
API 化、可观测、队列化、网关加固、安全多租户、工具治理、数据治理、
评测回归、平台化。把这套能力迁移到真实业务 = 在 v1 骨架上换掉
"单机简版"，换成你需要的生产组件即可。
