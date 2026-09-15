# AI 上下文变量 CURRENT_RECORD 模式 - 实现总结

## 需求回顾

用户场景：定量限试验结果表按杂质分组，每个杂质有多条检测记录和一个AI生成的结论。问题是：**AI生成结论时，如何引用"当前杂质"的数据？**

## 解决方案

实现了 **CURRENT_RECORD（当前记录）** 取值模式，让AI字段可以按编组的每条记录单独生成。

## 核心实现

### 1. 前端修改

#### `SystemContextVariables.vue`
- 添加 `CURRENT_RECORD` 模式到取值方式列表
- 更新提示文本，说明用途："用于AI字段在编组内部，按每条记录生成"

### 2. 后端核心修改

#### `ai_field_generator.py`

**新增函数**：
```python
def needs_per_record_generation(config: dict[str, Any]) -> bool:
    """检查AI规则是否需要按记录生成（有 CURRENT_RECORD 模式的上下文变量）"""
```

**修改函数签名**，支持传入当前记录：
```python
def resolve_context_values(config, values, current_record=None)
def render_ai_prompt(config, values, current_record=None)
def generate_ai_text(field_code, rule, values, current_record=None)
```

**扩展 `_format_context()`**：
- 当 mode 为 CURRENT_RECORD 时，直接格式化当前记录的值
- 支持嵌套数据（序列化为JSON）

**扩展 `resolve_context_values()`**：
- 当 mode 为 CURRENT_RECORD 时：
  - 如果有 current_record，从中读取字段值（提取相对键名）
  - 如果没有 current_record，标记为缺失或使用默认值

#### `system_field_resolver.py`

**修改 `_rule_value()`**：
- 添加 `current_record` 参数
- LIMS 类型字段：如果在按记录生成上下文中，从当前记录读取
- AI 和 CALCULATED 类型：传递 `current_record` 给生成函数

**修改 `resolve_system_fields()` 主循环**：
- 检测 AI 字段是否需要按记录生成（`needs_per_record_generation()`）
- 如果需要：
  - 获取编组的记录数组
  - 遍历每条记录，调用 `generate_ai_text()` 并传入 `current_record`
  - 收集所有生成结果组成数组
- 如果不需要：按原有逻辑一次性生成

### 3. 数据流

```
配置阶段：
用户在前端选择 CURRENT_RECORD 模式 → 保存到数据库

生成阶段：
1. 读取 AI 字段规则
2. 检测：needs_per_record_generation() → True
3. 获取编组数据：values["limit"] = [{...}, {...}]
4. 遍历记录：
   for record in records:
     - 构建上下文：current_record = {"impurityName": "杂质A", ...}
     - 调用 AI：generate_ai_text(field_code, rule, values, record)
     - 收集结果：generated_values.append(result)
5. 写入结果数组：field.value = ["结论A", "结论B", ...]
```

### 4. 字段路径处理

上下文变量中的字段路径（如 `limit.impurityName`）自动提取相对键名：

```python
relative_key = field_code.split(".")[-1]  # "limit.impurityName" → "impurityName"
record_value = current_record.get(relative_key)  # 从当前记录读取
```

## 使用示例

### 配置（前端）

**字段**：`limit.conclusion`（AI 生成）

**上下文变量**：
- `limit.impurityName` - 当前记录 ✓
- `limit.detectionLimit` - 当前记录 ✓
- `limit.detectionResults` - 当前记录 ✓

**提示词模板**：
```
杂质：{{limit.impurityName}}
检测限：{{limit.detectionLimit}}
检测结果：{{limit.detectionResults}}

请生成结论。
```

### 数据（生成前）

```json
{
  "limit": [
    {
      "impurityName": "杂质A",
      "detectionLimit": "0.05%",
      "detectionResults": [...]
    },
    {
      "impurityName": "杂质B",
      "detectionLimit": "0.03%",
      "detectionResults": [...]
    }
  ]
}
```

### 结果（生成后）

```json
{
  "limit": [
    {
      "impurityName": "杂质A",
      "detectionLimit": "0.05%",
      "detectionResults": [...],
      "conclusion": "杂质A的检测限结果合格。"
    },
    {
      "impurityName": "杂质B",
      "detectionLimit": "0.03%",
      "detectionResults": [...],
      "conclusion": "杂质B的检测限结果合格。"
    }
  ]
}
```

## 错误处理

### 字段不属于编组
```
AI字段 xxx 使用 CURRENT_RECORD 模式但不属于任何编组
```

### 编组数据不是数组
```
编组 xxx 的数据不是数组，无法按记录生成
```

### 缺少当前记录上下文
标记为缺失字段，或使用默认值

## 测试覆盖

创建了 `backend/tests/test_ai_current_record.py`，覆盖：
- ✅ 检测需要按记录生成
- ✅ 从当前记录读取字段值
- ✅ 处理嵌套数据（序列化为JSON）
- ✅ 缺少当前记录上下文
- ✅ 混合使用不同取值模式
- ✅ context_variables 函数支持

所有测试通过 ✓

## 性能考虑

- **AI 调用次数 = 记录数**：10条记录 = 10次AI调用
- **生成时间**：串行生成，总时间 = 单次时间 × 记录数
- **成本**：按实际调用次数计费

## 向后兼容

- ✅ 原有的 FIRST、JOIN_UNIQUE、COUNT_UNIQUE 模式不受影响
- ✅ 不使用 CURRENT_RECORD 的 AI 字段按原逻辑生成
- ✅ 可以在同一个 AI 规则中混合使用不同模式

## 文档

- `backend/docs/ai-current-record-mode.md` - 完整使用文档
- `backend/tests/test_ai_current_record.py` - 测试用例

## 修改的文件

**前端**：
- `frontend/src/SystemContextVariables.vue` - 添加 CURRENT_RECORD 模式

**后端**：
- `backend/app/services/ai_field_generator.py` - 核心生成逻辑
- `backend/app/services/system_field_resolver.py` - 按记录遍历逻辑

**测试**：
- `backend/tests/test_ai_current_record.py` - 新增测试

**文档**：
- `backend/docs/ai-current-record-mode.md` - 使用文档
- `CURRENT_RECORD_MODE_SUMMARY.md` - 本文档
