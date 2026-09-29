# field_mapper — 字段映射引擎

把各家 HRIS 的员工数据按 JSON 映射规则统一成标准员工结构的 Python 库，
由上层集成网关直接调用（无接口层）。规则集按连接器保存在 SQLite 中。

## 快速开始

```python
from field_mapper import Engine, RuleSetStore

store = RuleSetStore("rules.db")

# 保存规则集（保存前整体校验，有任何问题整份拒收、旧版本继续生效）
store.save("workday", [
    {"target": "employee_id", "source": "worker.id", "convert": "id"},
    {"target": "first_name", "source": "worker.name.given"},
    {"target": "status", "source": "worker.status_code", "conditions": [
        {"equals": "A", "value": "active"},
        {"when": "worker.leave", "equals": "Y", "value": "on_leave"},
    ], "otherwise": "inactive"},
    {"target": "weekly_hours", "source": "worker.hours", "convert": "int", "default": 40},
])

# 批次开始时加载一次规则集 —— 整批都按这个版本转换，
# 中途有人保存新版本也不影响正在跑的批
engine = Engine(store.load("workday"))
results = engine.transform_batch(list_of_source_records)  # 一批最多 1000 条
for result in results:
    if result.ok:
        handle(result.employee)       # 标准员工结构，中间字段已被剔除
    else:
        for err in result.errors:     # 该记录的全部错误，不止第一个
            log(err.field, err.rule_index, err.reason)
```

## 标准员工结构

| 字段 | 类型 | 必填 |
|---|---|---|
| `employee_id` | id（字符串，保留前导零） | 是 |
| `first_name` / `last_name` / `email` | string | 是 |
| `status` | active / inactive / terminated / on_leave | 是 |
| `department` / `title` | string | 否 |
| `start_date` | date（输出 `YYYY-MM-DD`） | 否 |
| `manager_id` | id（不能等于本人 `employee_id`） | 否 |
| `is_contractor` | bool | 否 |
| `weekly_hours` | int | 否 |

## 规则 JSON 结构

规则集是一个数组，顺序即执行顺序。每条规则：

```json
{
  "target": "weekly_hours",     // 标准字段名，或自定义中间字段名
  "source": "worker.hours",     // 源路径；@ 开头表示引用其他规则的输出
  "convert": "int",             // 可选：date/bool/int/id/status/string
  "default": 40                 // 可选：缺值时兜底（本身须符合目标类型）
}
```

条件映射（与 `convert`/`default` 互斥，用 `otherwise` 兜底）：

```json
{
  "target": "status",
  "source": "worker.status_code",
  "conditions": [
    {"when": "worker.status_code", "equals": "A", "value": "active"},
    {"when": "worker.leave", "equals": "Y", "value": "on_leave"}
  ],
  "otherwise": "inactive"
}
```

- `when` 可省略，省略时判断本条规则的 `source`；可指向源记录任意字段。
- 比较按去掉首尾空白的文本、区分大小写；按顺序先中先用。
- 都不中且没写 `otherwise`：转换时报错，**不会**原样透传。

## 语义要点

- **路径**：`a.b[0].c` 支持嵌套对象和数组下标；路径中途断掉算缺值。
- **缺值**：字段不存在、为 `null`、只有空白字符都算缺值。默认值只在缺值时生效，缺值不做类型转换；必填字段最终缺值报错。
- **中间字段**：`target` 不是标准字段名即为中间字段，可被其他规则用 `@名字`（含 `@名字.子路径`）引用，不出现在结果里。
- **日期**：接受 `YYYY-MM-DD`、`MM/DD/YYYY`（月日可省前导零）、8 位数字 `YYYYMMDD`（字符串或整数）、带时区的 ISO 8601 时间（取 UTC 当天）。不存在的日期和不带时区的时间报错。
- **布尔**：整数只认 0/1；字符串去空白后不分大小写，只认 true/false/yes/no/1/0；其余报错，不会当成 false。
- **整数**：`"0042"`→42，`"3.0"`→3，`"3.5"` 报错，布尔不能当整数。
- **id**：输出字符串，保留前导零；数字 `1001`→`"1001"`，非整数数字报错。
- **保存校验**（任一不满足即整份拒收，并列出全部问题及规则位置）：不超过 500 条；字段不重复定义；`@` 引用必须已定义且无环；转换类型已知；默认值/条件结果本身符合目标字段类型。
- **转换**：逐条记录进行，单条失败列出全部错误（字段、规则位置、原因），依赖失败字段的字段报"上游失败"，其他记录不受影响。一批最多 1000 条。

## 测试

```bash
python3 -m pytest tests/ -q
```
