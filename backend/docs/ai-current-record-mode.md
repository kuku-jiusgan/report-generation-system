# AI 生成字段的 CURRENT_RECORD 模式 - 按记录生成

## 背景

在分组数据场景中（如定量限试验结果表，按杂质分组），每条记录需要根据**当前记录的数据**生成 AI 结论。例如：

```json
{
  "limit": [
    {
      "impurityName": "杂质A",
      "detectionResults": [...],
      "conclusion": "应该根据本杂质的 detectionResults 生成"
    },
    {
      "impurityName": "杂质B",
      "detectionResults": [...],
      "conclusion": "应该根据本杂质的 detectionResults 生成"
    }
  ]
}
```

## 解决方案：CURRENT_RECORD 模式

在上下文变量中使用 **CURRENT_RECORD** 模式，表示"从当前记录读取字段值"。

### 工作原理

1. **检测**：系统检测到 AI 字段使用了 CURRENT_RECORD 模式
2. **遍历**：自动遍历编组的每条记录
3. **生成**：为每条记录单独调用 AI，传入当前记录的上下文
4. **结果**：返回数组，每个元素对应一条记录的 AI 生成结果

## 配置示例

### 场景：定量限试验结果表

**编组结构**：
- 编组：`limit`（定量限试验结果）
- 字段：
  - `limit.impurityName`（杂质名称）
  - `limit.detectionLimit`（检测限）
  - `limit.quantitationLimit`（定量限）
  - `limit.detectionResults`（检测结果，子数组）
  - `limit.conclusion`（结论，AI 生成）

**AI 规则配置**（字段 `limit.conclusion`）：

```json
{
  "sourceType": "AI",
  "config": {
    "contextVariables": [
      {
        "fieldCode": "limit.impurityName",
        "mode": "CURRENT_RECORD",
        "required": true,
        "defaultValue": ""
      },
      {
        "fieldCode": "limit.detectionLimit",
        "mode": "CURRENT_RECORD",
        "required": true,
        "defaultValue": ""
      },
      {
        "fieldCode": "limit.quantitationLimit",
        "mode": "CURRENT_RECORD",
        "required": true,
        "defaultValue": ""
      },
      {
        "fieldCode": "limit.detectionResults",
        "mode": "CURRENT_RECORD",
        "required": true,
        "defaultValue": ""
      }
    ],
    "promptTemplate": "杂质：{{limit.impurityName}}\n检测限：{{limit.detectionLimit}}\n定量限：{{limit.quantitationLimit}}\n\n检测结果：\n{{limit.detectionResults}}\n\n请根据以上信息生成结论。"
  }
}
```

### 生成过程

#### 第1条记录（杂质A）

**当前记录**：
```json
{
  "impurityName": "杂质A",
  "detectionLimit": "0.05%",
  "quantitationLimit": "0.15%",
  "detectionResults": [
    {"concentration": "0.05%", "result": "合格"},
    {"concentration": "0.10%", "result": "合格"}
  ]
}
```

**AI 收到的提示词**：
```
杂质：杂质A
检测限：0.05%
定量限：0.15%

检测结果：
[
  {
    "concentration": "0.05%",
    "result": "合格"
  },
  {
    "concentration": "0.10%",
    "result": "合格"
  }
]

请根据以上信息生成结论。
```

**AI 生成结果**：`"杂质A的检测限和定量限检测结果均合格。"`

#### 第2条记录（杂质B）

类似地，AI 使用杂质B的数据生成另一个结论。

#### 最终结果

```json
{
  "limit": [
    {
      "impurityName": "杂质A",
      "detectionLimit": "0.05%",
      "quantitationLimit": "0.15%",
      "detectionResults": [...],
      "conclusion": "杂质A的检测限和定量限检测结果均合格。"
    },
    {
      "impurityName": "杂质B",
      "detectionLimit": "0.03%",
      "quantitationLimit": "0.10%",
      "detectionResults": [...],
      "conclusion": "杂质B的检测限和定量限检测结果均合格。"
    }
  ]
}
```

## 前端配置步骤

1. 进入"系统标准字段" → 选择 `limit.conclusion` 字段
2. 在"提取规则"中选择"AI 生成"
3. 点击"配置规则"
4. 在"上下文变量"中：
   - 点击"添加变量"
   - 选择字段：`limit.impurityName`
   - **取值方式**：选择"**当前记录**"
   - 勾选"必填"
5. 重复步骤4，添加其他需要的字段（`limit.detectionLimit`、`limit.quantitationLimit`、`limit.detectionResults`）
6. 在"提示词模板"中使用 `{{limit.字段名}}` 引用这些变量
7. 保存规则

## 注意事项

### 字段必须属于编组

使用 CURRENT_RECORD 模式的 AI 字段必须属于某个编组，否则系统会报错：

```
AI字段 xxx 使用 CURRENT_RECORD 模式但不属于任何编组
```

### 编组数据必须是数组

编组的 `cardinality` 必须是 `MANY`（多行），数据必须是数组格式，否则报错：

```
编组 xxx 的数据不是数组，无法按记录生成
```

### 字段路径的处理

上下文变量中的字段路径（如 `limit.impurityName`）会自动提取相对键名（最后一个点之后的部分），即 `impurityName`，然后从当前记录中读取。

### 性能考虑

按记录生成意味着每条记录都会调用一次 AI 服务。如果编组有10条记录，就会调用10次 AI。请注意：
- AI 服务的调用次数和成本
- 生成时间会比一次性生成更长

## 混合使用

可以在同一个 AI 规则中混合使用不同的取值模式：

```json
{
  "contextVariables": [
    {
      "fieldCode": "project.name",
      "mode": "FIRST",
      "required": true
    },
    {
      "fieldCode": "limit.impurityName",
      "mode": "CURRENT_RECORD",
      "required": true
    }
  ],
  "promptTemplate": "项目：{{project.name}}\n当前杂质：{{limit.impurityName}}\n\n请生成结论。"
}
```

- `project.name` 使用 FIRST 模式：从全局 values 读取
- `limit.impurityName` 使用 CURRENT_RECORD 模式：从当前记录读取

## 其他取值模式对比

| 模式 | 用途 | 数据来源 | 适用场景 |
|------|------|---------|---------|
| FIRST | 取第一个值 | 全局 values | 单值字段 |
| JOIN_UNIQUE | 去重拼接 | 全局 values | 多值字段，需要拼成文本 |
| COUNT_UNIQUE | 去重计数 | 全局 values | 统计数量 |
| **CURRENT_RECORD** | 当前记录 | 当前记录 | **编组内按记录生成** |

## 技术实现

### 检测需要按记录生成

```python
def needs_per_record_generation(config: dict[str, Any]) -> bool:
    """检查AI规则是否需要按记录生成"""
    for variable in context_variables(config):
        if str(variable.get("mode") or "").upper() == "CURRENT_RECORD":
            return True
    return False
```

### 按记录遍历生成

```python
if source_type == "AI" and needs_per_record_generation(config):
    # 按记录生成：遍历编组的每条记录
    collection_code = field.get("collectionCode")
    records = values.get(collection_code)

    generated_values = []
    for record in records:
        if isinstance(record, dict):
            record_value = generate_ai_text(field_code, rule, values, record)
            generated_values.append(record_value)

    value = generated_values
```

### 上下文解析

```python
if mode == "CURRENT_RECORD":
    if not current_record:
        # 没有当前记录上下文
        if variable.get("required", True):
            missing.append(code)
        text = str(variable.get("defaultValue") or "")
    else:
        # 从当前记录中读取字段（相对路径）
        relative_key = field_code.split(".")[-1]
        record_value = current_record.get(relative_key)
        text = _format_context(record_value, variable) or str(variable.get("defaultValue") or "")
```

## 完整示例

见 `backend/tests/test_ai_current_record.py` 中的测试用例。
