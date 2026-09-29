# mapping-engine

字段映射引擎库：把各家 HRIS 的员工数据按 JSON 规则集转换成标准员工结构。
纯 Python 库，由上层集成网关直接调用，无接口层；规则集按连接器存 SQLite。

## 快速开始

```python
from mapping_engine import RuleSetStore, transform_batch

store = RuleSetStore("rules.db")

# 保存规则集（保存前整体校验，有任何问题整份拒收，旧版本继续生效）
store.save("acme", [
    {"target": "employee_id", "source": "emp.id", "transform": "id_string"},
    {"target": "first_name", "source": "name.first"},
    {"target": "last_name", "source": "name.last"},
    {"target": "email", "source": "contact.email"},
    {"target": "status", "conditions": [
        {"source": "state", "equals": "A", "value": "active"},
        {"source": "state", "equals": "T", "value": "terminated"},
    ], "default": "inactive"},
    {"target": "weekly_hours", "source": "hours", "transform": "int", "default": 40},
    {"target": "dept_norm", "source": "dept"},              # 中间字段
    {"target": "department", "source": "$dept_norm"},        # 引用中间字段
])

# 每批开始时取一次当前版本：转换进行中有人保存新版本，本批仍按旧版本跑完
ruleset = store.get_current("acme")
batch = transform_batch(ruleset, records)   # 一批最多 1000 条
for r in batch.results:
    if r.ok:
        handle(r.employee)      # 只含标准字段，中间字段不出现
    else:
        log(r.errors)           # 该条的全部错误：字段、规则位置、原因
```

## 规则 JSON 格式

| 键 | 说明 |
|---|---|
| `target` | 标准字段名，或自定义中间字段名（供其他规则用 `$名字` 引用） |
| `source` | 源记录路径，`.` 分隔，数字段为数组下标；路径中途断掉算缺值 |
| `transform` | 可选类型转换：`string`/`id_string`/`int`/`bool`/`date`/`status` |
| `default` | 缺值时填入；只在缺值时生效，缺值本身不做类型转换 |
| `conditions` | 有序条件分支，先中先用；`equals` 按去首尾空白文本、区分大小写比较 |

目标为标准字段时，输出自动按该字段的标准类型归一；条件全不中且没写
`default` 时报错，绝不原样透传。

## 类型规则摘要

- **date**：接受 `YYYY-MM-DD`、`M/D/YYYY`（月日可省前导零）、8 位
  `YYYYMMDD`（字符串或整数）、带时区的 ISO 8601（取 UTC 当天）。
  不存在的日期、不带时区的时间报错。输出 `YYYY-MM-DD`。
- **bool**：整数只认 0/1；字符串去空白后不分大小写只认
  `true/false/yes/no/1/0`；其余报错，不当 false。
- **int**：`"0042"`→42，`"3.0"`→3，`"3.5"` 报错，布尔不当整数。
- **id_string**（employee_id/manager_id）：输出字符串保留前导零，
  数字 1001→`"1001"`，非整数数字报错；manager_id 不能等于本人 employee_id。
- **status**：只认 `active`/`inactive`/`terminated`/`on_leave`。

## 保存时校验（任一不满足即整份拒收并列出全部问题及位置）

- 规则数超过 500
- 同一字段被定义两次
- 引用未定义字段（`$名字`）
- 引用成环（含自引用）
- 未知转换类型
- 默认值或条件映射结果不合目标字段类型

## 运行测试

```bash
python3 -m pytest tests/ -q
```
